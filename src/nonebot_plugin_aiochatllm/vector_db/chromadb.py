import time
import uuid
from collections.abc import Mapping
from typing import Any, cast

import chromadb
import httpx
import nonebot_plugin_localstore as store
import numpy as np
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings, GetResult, QueryResult
from nonebot import logger

from .base import VectorMethod


class OpenAILikeEmbed(EmbeddingFunction):
    """ChromaDB OpenAILike嵌入函数"""

    def __init__(self, api_key: str, base_url: str, model_name: str, dimension: int) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.dimension = dimension

    def __call__(self, input: Documents) -> Embeddings:
        input = [t.replace("\n", " ") for t in input]
        max_retries = 3
        last_exception = None
        for retry_attempt in range(max_retries):
            try:
                payload = {"model": self.model_name, "input": input, "encoding_format": "float"}
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

                response = httpx.post(f"{self.base_url}/embeddings", json=payload, headers=headers)
                response.raise_for_status()

                embeddings = [np.array(item["embedding"], dtype=np.float32) for item in response.json()["data"]]

                if embeddings[0].shape[0] != self.dimension:
                    raise ValueError(f"期望的嵌入维度是 {self.dimension}, 但得到的是 {embeddings[0].shape[0]}")

                return cast(Embeddings, [embeddings[i].tolist() for i in range(len(embeddings))])

            except Exception as e:
                last_exception = e
                logger.warning(f"获取嵌入向量第 {retry_attempt + 1}/{max_retries} 次失败: {e!s}")

        logger.error(f"获取嵌入向量失败,已尝试 {max_retries} 次: {last_exception!s}")
        raise RuntimeError("无法获取嵌入向量") from last_exception


class ChromaDBVector(VectorMethod):
    """ChromaDB操作类"""

    def __init__(self, user_id: str, config: dict[str, Any]) -> None:
        """初始化ChromaDB"""
        self.user_id = user_id
        self.config = config
        self.dimension: int = self.config["embed"]["dimension"]
        self.memory_file = store.get_data_file("nonebot_plugin_aiochatllm", f"memory_{self.user_id}")
        self.chroma_client = chromadb.PersistentClient(path=str(self.memory_file))

    def create_or_get_collection(self, collection_name: str, schema: dict[str, Any]) -> Collection:
        """创建或获取ChromaDB集合"""
        try:
            collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                metadata=schema,
                embedding_function=OpenAILikeEmbed(**self.config["embed"]),
            )
        except Exception as e:
            logger.error(f"创建ChromaDB集合时出现错误: {e!s}")
            raise RuntimeError from e
        return collection

    def drop_collection(self, collection_name: str) -> bool:
        """删除ChromaDB集合"""
        try:
            self.chroma_client.delete_collection(name=collection_name)
            return True
        except Exception as e:
            logger.error(f"删除ChromaDB集合时出现错误: {e!s}")
            return False

    def list_collections(self, limit: int | None = None, offset: int | None = None) -> list[str]:
        """列出ChromaDB中的所有集合"""
        return list(self.chroma_client.list_collections(limit=limit, offset=offset))

    @staticmethod
    def _generate_lists(data: list[str]) -> tuple[list[str], list[Mapping[str, str | int | float | bool]]]:
        """生成UUID列表和更新时间列表"""
        uuid_list = []
        update_time_list: list[Mapping[str, str | int | float | bool]] = []

        for _ in data:
            uuid_list.append(str(uuid.uuid4()))
            update_time_list.append({"update_time": int(round(time.time() * 1000))})

        return uuid_list, update_time_list

    def insert_memories(self, collection: Collection, data: list[str]) -> bool:
        """向ChromaDB集合中插入记忆数据"""
        try:
            uuids, update_times = self._generate_lists(data)
            collection.add(documents=data, metadatas=update_times, ids=uuids)
            return True
        except Exception as e:
            logger.error(f"向ChromaDB集合中插入记忆数据时出现错误: {e!s}")
            return False

    @staticmethod
    def _process_data(data: QueryResult | GetResult) -> list[dict[str, Any]]:
        """处理ChromaDB查询结果"""
        result: list[dict[str, Any]] = []

        if "distances" in data:
            documents = data.get("documents", [])
            distances = data.get("distances", [])

            if documents and distances:
                ids = data["ids"][0]
                docs = documents[0]
                dists = distances[0]  # type: ignore

                result.extend(
                    {
                        "id": id_val,
                        "document": doc_val,
                        "distance": dist_val,
                    }
                    for id_val, doc_val, dist_val in zip(ids, docs, dists, strict=False)
                    if dist_val < 0.9
                )
        else:
            if documents := data.get("documents"):
                ids = data["ids"]

                result.extend(
                    {"id": id_val, "document": doc_val} for id_val, doc_val in zip(ids, documents, strict=False)
                )

        return result

    def query_memories(self, collection: Collection, top_k: int, data: list[str]) -> list[dict[str, Any]]:
        """查询ChromaDB集合中的记忆数据"""
        res = collection.query(query_texts=data, n_results=top_k)
        return self._process_data(res)

    def get_memories(self, collection: Collection, memory_ids: list[str]) -> list[dict[str, Any]]:
        """通过ID获取ChromaDB集合中的记忆数据"""
        res = collection.get(ids=memory_ids)
        return self._process_data(res)

    def update_memories(self, collection: Collection, memory_ids: list[str], data: list[str]) -> bool:
        """更新ChromaDB集合中的记忆数据"""
        try:
            update_time = int(round(time.time() * 1000))
            metadatas: list[dict[str, Any]] = [{"update_time": update_time} for _ in data]
            collection.update(
                ids=memory_ids, documents=data, metadatas=cast(list[Mapping[str, str | int | float | bool]], metadatas)
            )
            return True
        except Exception as e:
            logger.error(f"更新ChromaDB集合时出现错误: {e!s}")
            return False

    def list_memories(self, collection: Collection, limit: int | None, offset: int | None) -> list[dict[str, Any]]:
        """列出ChromaDB集合中的记忆数据"""
        res = collection.get(limit=limit, offset=offset)
        if res:
            return self._process_data(res)
        return []

    def delete_memories(self, collection: Collection, memory_ids: list[str]) -> bool:
        """删除ChromaDB集合中的记忆数据"""
        try:
            collection.delete(ids=memory_ids)
            return True
        except Exception as e:
            logger.error(f"删除ChromaDB集合时出现错误: {e!s}")
            return False

    def trim_collection(self, collection: Collection) -> bool:
        """清理过时记忆数据"""
        try:
            current_count = collection.count()
            if current_count <= 300:
                return True
            excess = current_count - 300

            results = collection.get(include=["metadatas"])  # type: ignore

            if not results:
                logger.error("无法获取元数据")
                return True

            metadatas = results["metadatas"]

            if not metadatas:
                return False

            ids = results["ids"]

            entries = [(ids[i], cast(int, metadatas[i]["update_time"])) for i in range(len(ids))]
            sorted_entries = sorted(entries, key=lambda x: x[1])

            oldest_ids = [entry[0] for entry in sorted_entries[:excess]]

            collection.delete(ids=oldest_ids)
            logger.debug(f"已删除{len(oldest_ids)}条最旧记忆")
            return True

        except Exception as e:
            logger.error(f"清理过时记忆数据时出现错误: {e!s}")
            return False
