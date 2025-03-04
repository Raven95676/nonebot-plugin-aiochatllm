import asyncio
from typing import Any

import httpx
from nonebot import logger

from .vector_db.chromadb import ChromaDBVector


class MemoryManager:
    """记忆管理器"""

    def __init__(self, user_id: str, config: dict[str, Any]) -> None:
        """初始化记忆管理器"""
        self.user_id = user_id
        self.config = config
        self.chromadb = ChromaDBVector(user_id=user_id, config=config)
        self.collection = self.chromadb.create_or_get_collection(
            collection_name=f"{user_id}_memories", schema={"description": f"Memories for {user_id}"}
        )

    async def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        max_retries = 3
        last_exception = None

        for retry_attempt in range(max_retries):
            try:
                messages = [{"role": "user", "content": prompt}]
                pd = {
                    "model": self.config["summary"]["model_name"],
                    "messages": messages,
                    "stream": False,
                    "temperature": 0,
                    "top_p": 0,
                }
                hd = {
                    "Authorization": f"Bearer {self.config['summary']['api_key']}",
                    "Content-Type": "application/json",
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.config['summary']['base_url']}/chat/completions", json=pd, headers=hd
                    )
                    response.raise_for_status()

                resp = str(response.json()["choices"][0]["message"]["content"])

                return resp

            except Exception as e:
                last_exception = e
                logger.warning(f"调用LLM第 {retry_attempt + 1}/{max_retries} 次失败: {e!s}")
                if retry_attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2**retry_attempt))

        logger.error(f"调用LLM失败,已尝试 {max_retries} 次: {last_exception!s}")
        return ""

    async def _decide_memory_action(self, new_memory: str, similar_memories: list[dict]) -> str:
        """使用模型决策记忆操作"""

        memory_list = "\n".join(
            [f"Memory {m['id']} (similarity: {m.get('distance', 0):.4f}): {m['document']}" for m in similar_memories]
        )

        prompt = f"""
        I have a new piece of information and some existing similar memories.
        Please decide which action I should take:

        1. MERGE_id - Combine the new information with an existing memory
        2. UPDATE_id - Replace an existing memory with this new information
        3. DELETE_id - The existing memory is outdated and should be replaced
        4. KEEP_SEPARATE - Keep as a new separate memory

        Guidelines:
            - Eliminate duplicate memories and merge related memories to ensure a concise and updated list.
            - If a memory is directly contradicted by new information, critically evaluate both pieces of information:
            - If the new memory provides a more recent or accurate update, replace the old memory with new one.
            - If the new memory seems inaccurate or less detailed, retain the original and discard the old one.
            - Maintain a consistent and clear style throughout all memories, ensuring each entry is concise yet informative.
            - If the new memory is a variation or extension of an existing memory, update the existing memory to reflect the new information.

        New information: {new_memory}

        Similar existing memories:
        {memory_list}

        Your response should be one of: MERGE_id, UPDATE_id, DELETE_id, or KEEP_SEPARATE where 'id' is the memory ID to merge with, update, or delete.
        """  # noqa: E501

        decision = await self._call_llm(prompt)
        decision = decision.strip()

        if not decision:
            return "KEEP_SEPARATE"

        valid_formats = ["MERGE_", "UPDATE_", "DELETE_", "KEEP_SEPARATE"]

        if not any(decision.startswith(format) for format in valid_formats):
            return "KEEP_SEPARATE"

        return decision

    async def _merge_memories(self, memory1: str, memory2: str) -> str:
        """使用模型合并记忆"""
        prompt = f"""
        Please merge these two related pieces of information into a single,
        coherent and comprehensive memory:

        Memory 1: {memory1}
        Memory 2: {memory2}

        Prohibit the addition of any explanatory notes and retain only the merged memorized text.
        """

        merged_content = await self._call_llm(prompt)
        merged_content = merged_content.strip()

        return merged_content if merged_content else f"{memory1}\n{memory2}"

    async def analysis(self, user_input: str) -> None:
        """分析用户输入"""
        prompt = f"""
        Analyze the following user input and extract any important information that should be remembered for future reference. If there's nothing worth remembering, respond with "NOTHING_TO_REMEMBER". Otherwise, provide the information that should be remembered in a concise format.Output only what needs to be remembered, without any modifiers.You need to detect the language of the user input and record the facts in the same language.

        Types of information to focus on:

        Store personal preferences: record likes, dislikes, and specific preferences in various categories such as food, products, activities, and entertainment.

        Maintaining important personal information: remembering salient personal information such as names, relationships, and important dates.

        Remember activity and service preferences: remember user preferences for meals, trips, hobbies, and other services.

        Monitor health and wellness preferences: record users' dietary restrictions, fitness habits, and other health-related information.

        Store career-related information: remember job titles, work habits, career goals, and other career-related information.

        Manage other information: remember users' favorite books, movies, brands, and other information shared by users.

        User input: {user_input}
        """  # noqa: E501

        analysis_result = await self._call_llm(prompt)

        if not analysis_result or "NOTHING_TO_REMEMBER" in analysis_result:
            return

        await self.update(analysis_result)
        return

    async def update(self, content: str) -> None:
        """更新记忆"""

        similar_memories = self.chromadb.query_memories(collection=self.collection, top_k=15, data=[content])

        if not similar_memories:
            self.chromadb.insert_memories(collection=self.collection, data=[content])
            return

        decision = await self._decide_memory_action(content, similar_memories)

        def extract_target_id(prefix: str) -> str | None:
            if not decision.startswith(prefix):
                return None
            parts = decision.split("_", 1)
            if len(parts) < 2:
                logger.error(f"错误的决策格式: {decision}")
                return None
            return parts[1]

        logger.debug(f"决策为{decision}")

        if decision.startswith("MERGE_"):
            target_id = extract_target_id("MERGE_")
            if not target_id:
                self.chromadb.insert_memories(collection=self.collection, data=[content])
                return

            target_memories = self.chromadb.get_memories(collection=self.collection, memory_ids=[target_id])
            if not target_memories:
                logger.warning(f"合并目标 {target_id} 未找到,插入新记忆")
                self.chromadb.insert_memories(collection=self.collection, data=[content])
                return

            target_doc = target_memories[0].get("document")
            if not target_doc:
                logger.warning(f"合并目标 {target_id} 没有内容,插入新记忆")
                self.chromadb.insert_memories(collection=self.collection, data=[content])
                return

            merged_content = await self._merge_memories(str(target_doc), content)
            if not self.chromadb.update_memories(
                collection=self.collection, memory_ids=[target_id], data=[merged_content]
            ):
                logger.error(f"未能合并 {target_id} ,插入新记忆")
                self.chromadb.insert_memories(collection=self.collection, data=[content])
                return

        elif decision.startswith("UPDATE_"):
            target_id = extract_target_id("UPDATE_")
            if not target_id:
                self.chromadb.insert_memories(collection=self.collection, data=[content])
                return

            if not self.chromadb.update_memories(collection=self.collection, memory_ids=[target_id], data=[content]):
                logger.warning(f"更新 {target_id} 错误,插入新记忆")
                self.chromadb.insert_memories(collection=self.collection, data=[content])
                return

        elif decision.startswith("DELETE_"):
            target_id = extract_target_id("DELETE_")
            if not target_id:
                return

            if not self.chromadb.delete_memories(collection=self.collection, memory_ids=[target_id]):
                logger.error(f"未能删除 {target_id}")

        else:
            self.chromadb.insert_memories(collection=self.collection, data=[content])

    async def get(self, user_input: str) -> list[str]:
        """获取记忆"""
        similar_memories = self.chromadb.query_memories(collection=self.collection, top_k=15, data=[user_input])
        memory_list = [
            f"Memory {m['id']} (similarity: {m.get('distance', 0):.4f}): {m['document']}" for m in similar_memories
        ]
        return memory_list
