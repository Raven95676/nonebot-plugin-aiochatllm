from math import ceil
from typing import Any

from nonebot import get_plugin_config, on_message, require

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_localstore")
require("nonebot_plugin_apscheduler")

from arclet.alconna import config as alc_config
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot.permission import SuperUser
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
from .vector_db.chromadb import ChromaDBVector

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

if config_dict.get("summary") and config_dict.get("embed"):
    chromadb = ChromaDBVector(config=config_dict)

chat_mgr = ChatManager(config_dict)
chat = on_message(rule=to_me(), priority=30, block=False)
message_store = on_message(priority=35, block=False)


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
            Option(
                "set",
                Args["preset_name#预设名称", str],
                help_text="切换预设",
            ),
            help_text="预设管理",
        ),
        Subcommand(
            "memory",
            Option("list", Args["page?#页码", str], help_text="列出所有记忆"),
            Option(
                "add",
                Args["mem_content#记忆内容"],
                help_text="添加记忆",
            ),
            Option("del", Args["mem_id#记忆ID", str], help_text="删除记忆"),
            Option("clear", help_text="记忆清除"),
            help_text="记忆管理",
        ),
        Subcommand(
            "session",
            Option("list", help_text="列出当前活跃会话"),
            Option(
                "del",
                Args["session_id#会话ID", str],
                help_text="删除指定会话",
            ),
        ),
        Option("clear-context", help_text="清空上下文"),
        Option("uid", help_text="查看当前UID"),
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
    await aiochatllm.finish(f"当前预设列表：\n{presets}")


@aiochatllm.assign("preset.set")
async def set_preset(preset_name: Match[str], unisession: Uninfo) -> None:
    if not preset_name.available:
        await aiochatllm.finish("请输入预设名称")

    source_id = f"{unisession.scope}_{unisession.scene.type.name}_{unisession.scene.id}"
    chat_session = chat_mgr.get_session(source_id=source_id)

    if chat_session:
        if chat_session.set_preset(preset_name.result):
            await aiochatllm.finish(f"已切换至预设: {preset_name.result}")

        await aiochatllm.finish("预设: {preset_name.result} 不存在")

    await aiochatllm.finish("会话不存在，请先与Bot对话以创建会话")


@aiochatllm.assign("memory.list")
async def list_memories(unisession: Uninfo, page: Match[str]) -> None:
    if not chromadb:
        await aiochatllm.finish("记忆系统未开启")

    user_id = f"{unisession.scope}_{unisession.user.id}"
    collection = chromadb.get_collection(collection_name=f"{user_id}_memories")

    if not collection:
        await aiochatllm.finish("未获取到记忆库")

    current_count = collection.count()
    if current_count == 0:
        await aiochatllm.finish("没有记忆")

    page_num = int(page.result) if page.available else 1
    total_pages = ceil(current_count / 10)

    if page_num > total_pages:
        await aiochatllm.finish(f"页码超出范围，总页数: {total_pages}")

    offset = (page_num - 1) * 10
    memories = chromadb.list_memories(collection=collection, limit=10, offset=offset)

    if not memories:
        await aiochatllm.finish("没有记忆")

    memory_list = [f"ID {m['id']}: {m['document']}" for m in memories]
    mem = "\n".join(memory_list)

    await aiochatllm.finish(f"当前记忆：\n{mem}\n\n第 {page_num}/{total_pages} 页\n使用list [页码]查看更多记忆")


@aiochatllm.assign("memory.add")
async def add_memory(mem_content: Match[str], unisession: Uninfo) -> None:
    if not chromadb:
        await aiochatllm.finish("记忆系统未开启")

    user_id = f"{unisession.scope}_{unisession.user.id}"
    collection = chromadb.get_collection(collection_name=f"{user_id}_memories")

    if not collection:
        await aiochatllm.finish("未获取到记忆库")

    if not mem_content.available:
        await aiochatllm.finish("请输入记忆内容")

    if chromadb.insert_memories(collection=collection, data=[mem_content.result]):
        await aiochatllm.finish("已添加记忆")

    await aiochatllm.finish("添加记忆时出现错误")


@aiochatllm.assign("memory.del")
async def del_memory(mem_id: Match[str], unisession: Uninfo) -> None:
    if not chromadb:
        await aiochatllm.finish("记忆系统未开启")

    user_id = f"{unisession.scope}_{unisession.user.id}"
    collection = chromadb.get_collection(collection_name=f"{user_id}_memories")

    if not collection:
        await aiochatllm.finish("未获取到记忆库")

    if not mem_id.available:
        await aiochatllm.finish("请输入记忆ID")

    if chromadb.delete_memories(collection=collection, memory_ids=[mem_id.result]):
        await aiochatllm.finish("已删除记忆")

    await aiochatllm.finish("删除记忆时出现错误")


@aiochatllm.assign("memory.clear")
async def clear_memory(unisession: Uninfo) -> None:
    if not chromadb:
        await aiochatllm.finish("记忆系统未开启")

    user_id = f"{unisession.scope}_{unisession.user.id}"

    if chromadb.drop_collection(collection_name=f"{user_id}_memories"):
        await aiochatllm.finish("已清空记忆")

    await aiochatllm.finish("清空记忆时出现错误")


@aiochatllm.assign("session.list")
async def list_session() -> None:
    sessions = chat_mgr.list_sessions()
    if not sessions:
        await aiochatllm.finish("没有活跃会话")
    sessions_str = "\n".join(session for session in sessions)
    await aiochatllm.finish(f"当前活跃会话：\n{sessions_str}")


@aiochatllm.assign("session.del")
async def del_session(session_id: Match[str], is_superuser: bool = Depends(SuperUser())) -> None:
    if not is_superuser:
        await aiochatllm.finish("权限不足")

    if not session_id.available:
        await aiochatllm.finish("请输入会话ID")

    if await chat_mgr.delete_session(source_id=session_id.result):
        await aiochatllm.finish("已删除会话")

    await aiochatllm.finish("删除会话时出现错误")


@aiochatllm.assign("uid")
async def get_uid(event: Event) -> None:
    await aiochatllm.finish(event.get_user_id())


@aiochatllm.assign("clear-context")
async def clear_context(unisession: Uninfo) -> None:
    source_id = f"{unisession.scope}_{unisession.scene.type.name}_{unisession.scene.id}"
    chat_session = chat_mgr.get_session(source_id=source_id)

    if not chat_session:
        await aiochatllm.finish("会话不存在，无需清空")

    chat_session.clear_context()
    await aiochatllm.finish("已清空上下文")


@aiochatllm.handle()
async def help_text() -> None:
    await aiochatllm.finish("未知命令，请输入 /aiochatllm -h 或 /llm -h 查看帮助")
