import asyncio
import time
from collections import deque
from contextlib import suppress
from datetime import datetime
from typing import Any

import httpx
from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from .mem_mgr import MemoryManager


class ChatSession:
    """聊天会话类"""

    def __init__(self, user_id: str, source_id: str, user_name: str, config: dict[str, Any]) -> None:
        self.user_id = user_id
        self.source_id = source_id
        self.user_name = user_name
        self.config = config
        self.system_prompts = config["chat"]["presets"]
        self.current_persona = config["chat"].get("default_preset", "default")
        self.message_queue: asyncio.Queue[tuple[str, asyncio.Future]] = asyncio.Queue()
        self.processing_lock = asyncio.Lock()
        self.processing_task: asyncio.Task | None = None
        self.max_context_rounds = 15
        self.global_context: deque[str] = deque(maxlen=20)
        self.context: deque[dict[str, str]] = deque(maxlen=self.max_context_rounds * 2)
        if self.config.get("summary"):
            self.mem_mgr: MemoryManager | None = MemoryManager(self.user_id, self.config)
        else:
            self.mem_mgr = None
        try:
            self.nickname = next(iter(get_driver().config.nickname))
        except StopIteration:
            self.nickname = "Bot"
        self.last_activity = int(time.time() * 1000)
        logger.debug(f"为来自于 {source_id} 的 {user_id} 初始化 ChatSession")

    def _get_system_prompt(self) -> str:
        """获取当前角色的系统提示"""
        prompt = str(self.system_prompts.get(self.current_persona, "I'm a helpful AI assistant"))
        logger.debug(f"使用人格 '{self.current_persona}'")
        return prompt

    async def _call_llm(self, prompt: str, mode: str = "chat") -> str | None:
        """调用LLM"""
        max_retries = 3
        logger.debug(
            f"在 {mode} 模式下调用 LLM，输入长度为 {len(prompt)} 字符，模型为 {self.config[mode]['model_name']}"
        )

        messages = []
        if mode == "chat":
            messages.append(
                {
                    "role": "system",
                    "content": f"Now it's {datetime.now().strftime('%Y-%m-%dT%H:%MZ')}. You're talking with users now. They normally address you as {self.nickname}. Here are your settings. If the setting mentions asking you to play as someone, or if the setting mentions a name, the name in the setting is preferred:\n {self._get_system_prompt()} ",  # noqa: E501
                }
            )
            messages.extend(self.context)
            messages.append(
                {"role": "user", "content": f"User named {self.user_name}(ID:{self.user_id})said: {prompt}"}
            )
        else:
            messages.append({"role": "user", "content": prompt})

        logger.debug(messages)

        payload = {"model": self.config[mode]["model_name"], "messages": messages, "stream": False}
        headers = {
            "Authorization": f"Bearer {self.config[mode]['api_key']}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(300)) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.post(
                        f"{self.config[mode]['base_url']}/chat/completions", json=payload, headers=headers
                    )
                    response.raise_for_status()

                    resp = str(response.json()["choices"][0]["message"]["content"])

                    if resp:
                        return str(resp)
                    return None

                except httpx.HTTPError as e:
                    logger.warning(f"LLM调用失败 ({attempt + 1}/{max_retries}): {e!s}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5 * (2**attempt))
                except Exception as e:
                    logger.error(f"LLM调用时发生错误: {e!s}")
                    break
        return None

    async def add_message(self, message: str) -> str | None:
        """添加消息到处理队列并返回LLM响应"""
        logger.debug(f"{message[:50]} 加入消息队列")
        future: asyncio.Future[str | None] = asyncio.get_event_loop().create_future()

        await self.message_queue.put((message, future))

        await self._ensure_processing_task()

        try:
            return await future
        except Exception as e:
            logger.error(f"获取消息响应时出错: {e!s}")
            return None

    async def _ensure_processing_task(self) -> None:
        """确保存在一个消息处理任务"""
        if not self.processing_task or self.processing_task.done():
            self.processing_task = asyncio.create_task(self._process_messages())
            self.processing_task.add_done_callback(
                lambda t: logger.debug("消息处理任务结束") if not t.cancelled() else None
            )

    async def _process_messages(self) -> None:
        """处理消息队列"""
        logger.debug(f"开始处理消息，当前队列长度为 {self.message_queue.qsize()}")
        async with self.processing_lock:
            while not self.message_queue.empty():
                try:
                    message, future = await self.message_queue.get()
                except asyncio.QueueEmpty:
                    break

                try:
                    self.last_activity = int(time.time() * 1000)

                    similar_memories: list[str] = []
                    if self.mem_mgr:
                        await self.mem_mgr.analysis(message)
                        mem_results = await self.mem_mgr.get(message)
                        if mem_results:
                            similar_memories = mem_results
                            logger.debug(f"检索到 {len(similar_memories)} 条相关记忆")

                    context_parts = []
                    if self.global_context:
                        context_parts.append("全局上下文:\n" + "\n".join(f"- {ctx}" for ctx in self.global_context))
                    if similar_memories:
                        context_parts.append("相关记忆:\n" + "\n".join(f"- {m}" for m in similar_memories))
                    full_prompt = "\n\n".join(filter(None, [message, *context_parts]))
                    logger.debug(full_prompt)

                    response = await self._call_llm(full_prompt)

                    if response:
                        self.context.append({"role": "user", "content": message})
                        self.context.append({"role": "assistant", "content": response})

                        if len(self.context) >= self.max_context_rounds * 2 and self.config.get("summary"):
                            summary = await self._summarize_context()
                            if summary:
                                self.context = deque(
                                    [
                                        {"role": "user", "content": "Summarize our previous conversation."},
                                        {"role": "assistant", "content": summary},
                                    ],
                                    maxlen=self.max_context_rounds * 2,
                                )

                        future.set_result(response)
                    else:
                        future.set_result(None)

                except Exception as e:
                    logger.error(f"处理消息时发生错误: {e!s}")
                    if not future.done():
                        future.set_exception(e)
                finally:
                    self.message_queue.task_done()
                    logger.debug(f"消息处理完毕，现队列长度为: {self.message_queue.qsize()}")

    async def _summarize_context(self) -> str | None:
        """生成上下文总结"""
        context_text = "\n".join(
            f"{msg['role'].capitalize()}: {msg['content']}" for msg in self.context if msg["role"] != "system"
        )
        return await self._call_llm(
            f"Summarize the following conversation in concise terms:\n{context_text}", mode="summary"
        )

    def set_preset(self, preset_name: str) -> bool:
        """更改当前预设"""
        if preset_name == "default" or preset_name in self.system_prompts:
            self.current_persona = preset_name
            self.context.clear()
            return True
        else:
            logger.error(f"无效预设名称: {preset_name}")
            return False

    def clear_context(self) -> None:
        """清除当前上下文"""
        self.context.clear()
        self.global_context.clear()

    def add_global_context(self, message: str) -> None:
        """添加全局上下文"""
        if not message:
            return
        logger.debug(f"添加全局上下文: {message}")
        self.global_context.append(f"{message}")

    def update_user_info(self, user_name: str, user_id: str) -> None:
        self.user_name = user_name
        self.user_id = user_id

    async def cleanup_resources(self) -> None:
        """清理会话所有资源"""
        if self.processing_task and not self.processing_task.done():
            self.processing_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.processing_task

        while True:
            try:
                _, future = self.message_queue.get_nowait()
                if not future.done():
                    future.cancel()
            except asyncio.QueueEmpty:
                break

        self.mem_mgr = None
        self.context.clear()
        self.global_context.clear()

        logger.debug(f"会话 {self.source_id} 的资源已清理完毕")


class ChatManager:
    """会话管理类"""

    _instance = None

    def __new__(cls, config: dict[str, Any]) -> "ChatManager":
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        if not hasattr(self, "sessions"):
            self.sessions: dict[str, ChatSession] = {}

    def create_or_get_session(self, user_id: str, source_id: str, user_name: str) -> ChatSession:
        """创建或获取现有会话"""
        if source_id in self.sessions:
            existing_session = self.sessions[source_id]
            if existing_session.user_id != user_id:
                existing_session.update_user_info(user_id, user_name)
            return self.sessions[source_id]
        else:
            self.sessions[source_id] = ChatSession(
                user_id=user_id, source_id=source_id, config=self.config, user_name=user_name
            )
            return self.sessions[source_id]

    def get_session(self, source_id: str) -> ChatSession | None:
        """获取现有会话(不创建新会话,不更新用户信息)"""
        return self.sessions.get(source_id)

    def list_sessions(self) -> list[str]:
        """列出所有活跃会话ID"""
        session_ids = list(self.sessions.keys())
        return session_ids

    async def delete_session(self, source_id: str) -> bool:
        """删除会话,返回是否成功删除"""
        if source_id in self.sessions:
            session = self.sessions[source_id]
            await session.cleanup_resources()
            del self.sessions[source_id]
            return True
        return False

    def clear_sessions(self) -> None:
        """清除所有会话"""
        self.sessions.clear()


@scheduler.scheduled_job("cron", hour="*/2", id="chat_cleanup_job")
async def cleanup_sessions() -> None:
    """清理不活跃会话"""
    chat_manager = ChatManager._instance
    if not chat_manager:
        logger.warning("尝试清理会话但ChatManager实例不存在")
        return

    now = int(time.time() * 1000)
    inactive_threshold = 6 * 60 * 60 * 1000  # 6小时

    expired_sessions = [
        sid for sid, session in chat_manager.sessions.items() if now - session.last_activity > inactive_threshold
    ]

    for sid in expired_sessions:
        try:
            await chat_manager.delete_session(sid)
        except Exception as e:
            logger.error(f"清理会话 {sid} 时出错: {e}")

    logger.info(f"定时会话清理完成，当前活跃会话数: {len(chat_manager.sessions)}")
