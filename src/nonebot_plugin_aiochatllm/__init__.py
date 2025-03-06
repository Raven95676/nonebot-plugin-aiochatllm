from typing import Any

from nonebot import get_plugin_config, on_message, require

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_localstore")
require("nonebot_plugin_apscheduler")

from arclet.alconna import config as alc_config
from nonebot.adapters import Event
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.rule import to_me
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Match,
    Namespace,
    Option,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_uninfo import Uninfo

from .chat_mgr import ChatManager
from .config import Config
from .tools.censor import AliyunCensor

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-aiochatllm",
    description="多合一LLM聊天插件",
    usage="根据example中的配置项目进行配置后即可使用",
    type="application",
    config=Config,
    homepage="https://github.com/Raven95676/nonebot-plugin-aiochatllm",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_uninfo", "nonebot_plugin_alconna"),
)

config = get_plugin_config(Config)

config_dict: dict[str, Any] = {
    "chat": {
        "presets": config.chat.presets,
        "default_preset": config.chat.default_preset,
        "model_name": config.chat.model_name,
        "api_key": config.chat.api_key,
        "base_url": config.chat.base_url,
    }
}

if config.summary.model_name and config.summary.api_key and config.summary.base_url:
    config_dict["summary"] = {
        "model_name": config.summary.model_name,
        "api_key": config.summary.api_key,
        "base_url": config.summary.base_url,
    }

if config.embed.dimension and config.embed.model_name and config.embed.api_key and config.embed.base_url:
    config_dict["embed"] = {
        "dimension": config.embed.dimension,
        "model_name": config.embed.model_name,
        "api_key": config.embed.api_key,
        "base_url": config.embed.base_url,
    }

censor = None

if config.censor.access_key_id and config.censor.access_key_secret:
    config_dict["censor"] = {
        "key_id": config.censor.access_key_id,
        "key_secret": config.censor.access_key_secret,
    }
    censor = AliyunCensor(config_dict["censor"])

chat_mgr = ChatManager(config_dict)
chat = on_message(rule=to_me(), priority=35, block=True)
message_store = on_message(priority=30, block=False)


async def get_session_info(unisession: Uninfo) -> tuple[str, str, str]:
    user_id = f"{unisession.scope}_{unisession.user.id}"
    source_id = f"{unisession.scope}_{unisession.scene.type.name}_{unisession.scene.id}"
    user_name = unisession.user.name if unisession.user.name else "用户"
    return user_id, source_id, user_name


@chat.handle()
async def handle_chat_message(event: Event, unisession: Uninfo) -> None:
    user_id, source_id, user_name = await get_session_info(unisession)
    input_text = event.get_plaintext()

    chat_session = chat_mgr.create_or_get_session(user_id=user_id, source_id=source_id, user_name=user_name)

    out = await chat_session.add_message(input_text)
    if not out:
        return

    if censor and not await censor.check_text(out):
        await UniMessage.text("模型输出不合规").send()
        return

    should_reply = unisession.scene.type.name != "PRIVATE"
    await UniMessage.text(out).send(reply_to=should_reply)


@message_store.handle()
async def handle_message_store(event: Event, unisession: Uninfo) -> None:
    user_id, source_id, user_name = await get_session_info(unisession)
    input_text = event.get_plaintext()
    chat_session = chat_mgr.create_or_get_session(user_id=user_id, source_id=source_id, user_name=user_name)
    chat_session.add_global_context(f"User named {user_name}(ID:{user_id})said: {input_text}")


ns = Namespace("aiochatllm", disable_builtin_options=set())
alc_config.namespaces["aiochatllm"] = ns

aiochatllm = on_alconna(
    Alconna(
        "aiochatllm",
        Subcommand(
            "preset",
            Option("list", help_text="列出所有预设"),
            Option("set", Args["preset_name#预设名称", str], help_text="切换预设"),
            help_text="预设管理",
        ),
        Option("clear-context", help_text="清空上下文"),
        namespace=alc_config.namespaces["aiochatllm"],
        meta=CommandMeta(description="aiochatllm插件管理"),
    ),
    aliases={"llm"},
    use_cmd_start=True,
    skip_for_unmatch=False,
    priority=25,
    block=True,
)


@aiochatllm.assign("preset.list")
async def list_presets() -> None:
    presets = "\n".join(preset for preset in config.chat.presets.keys())
    await UniMessage.text(f"当前预设列表：\n{presets}").send()
    return


@aiochatllm.assign("preset.set")
async def set_preset(preset_name: Match[str], unisession: Uninfo) -> None:
    if not preset_name.available:
        await UniMessage.text("请输入预设名称").send()
        return
    source_id = f"{unisession.scope}_{unisession.scene.type.name}_{unisession.scene.id}"
    chat_session = chat_mgr.get_session(source_id=source_id)
    if chat_session:
        if chat_session.set_preset(preset_name.result):
            await UniMessage.text(f"已切换至预设: {preset_name.result}").send()
            return
        await UniMessage.text(f"预设: {preset_name.result} 不存在").send()
        return
    await UniMessage.text("会话不存在，请先与Bot对话以创建会话").send()
    return


@aiochatllm.assign("clear-context")
async def clear_context(unisession: Uninfo) -> None:
    source_id = f"{unisession.scope}_{unisession.scene.type.name}_{unisession.scene.id}"
    chat_session = chat_mgr.get_session(source_id=source_id)
    if chat_session:
        chat_session.clear_context()
        await UniMessage.text("已清空上下文").send()
        return
    await UniMessage.text("会话不存在，无需清空").send()
    return
