from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class VectorMethod(ABC, Generic[T]):
    """
    向量数据操作基类,定义向量数据库的标准操作接口。
    """

    @abstractmethod
    def create_or_get_collection(self, collection_name: str, schema: dict[str, Any]) -> T:
        """
        创建新的向量集合,如果集合已存在则返回现有集合。

        参数:
            collection_name (str): 集合名称。
            schema (dict[str, Any]): 定义集合结构的字典,包含字段、索引类型等配置。

        返回:
            T: 存在则返回集合实例,否则创建并返回集合实例。
        """
        pass

    @abstractmethod
    def drop_collection(self, collection_name: str) -> bool:
        """
        删除指定集合及其所有数据。

        参数:
            collection_name (str): 要删除的集合名称。

        返回:
            bool: 删除成功返回True,集合不存在或失败返回False。
        """
        pass

    @abstractmethod
    def list_collections(self, limit: int | None, offset: int | None) -> list[str]:
        """
        获取当前数据库中的所有集合名称。

        参数:
            limit (int | None): 每页返回的最大记录数。
            offset (int | None): 分页偏移量。

        返回:
            list[str]: 包含所有集合名称的列表。
        """
        pass

    @abstractmethod
    def insert_memories(self, collection: T, data: list[str]) -> bool:
        """
        插入记忆数据(自动附加时间戳)到指定集合。

        参数:
            collection (T): 目标集合实例。
            data (list[str]): 待插入的文本数据列表。

        返回:
            bool: 插入成功返回True,否则返回False。
        """
        pass

    @abstractmethod
    def query_memories(self, collection: T, top_k: int, data: list[str]) -> list[dict[str, Any]]:
        """
        在指定集合中查询与输入数据最相似的记忆。

        参数:
            collection (T): 目标集合实例。
            top_k (int): 需要返回的最相似结果数量。
            data (list[str]): 用于相似度匹配的查询文本列表。

        返回:
            list[dict[str, Any]]: 包含查询结果的字典列表,每个字典包含记忆内容、相似度等信息。
        """
        pass

    @abstractmethod
    def get_memories(self, collection: T, memory_ids: list[str]) -> list[dict[str, Any]]:
        """
        在指定集合中查询指定ID的记忆。

        参数:
            collection (T): 目标集合实例。
            memory_ids (list[str]): 要获取的记忆ID列表。

        返回:
            list[dict[str, Any]]: 包含查询结果的字典列表,每个字典包含记忆内容、相似度等信息。
        """
        pass

    @abstractmethod
    def update_memories(self, collection: T, memory_ids: list[str], data: list[str]) -> bool:
        """
        更新指定ID的记忆数据。

        参数:
            collection (T): 目标集合实例。
            memory_ids (list[str]): 要更新的记忆ID列表。
            data (list[str]): 新的文本数据列表(与ID顺序对应)。

        返回:
            bool: 更新成功返回True,否则返回False。
        """
        pass

    @abstractmethod
    def list_memories(self, collection: T, limit: int | None, offset: int | None) -> list[dict[str, Any]]:
        """
        获取指定集合中的记忆数据,支持分页查询。

        参数:
            collection (T): 目标集合实例。
            limit (int | None): 每页返回的最大记录数。
            offset (int | None): 分页偏移量。

        返回:
            list[dict[str, Any]]: 包含记忆数据的字典列表,每个字典包含记忆内容、相似度等信息。
        """
        pass

    @abstractmethod
    def delete_memories(self, collection: T, memory_ids: list[str]) -> bool:
        """
        根据ID删除指定集合中的特定记忆。

        参数:
            collection (T): 目标集合实例。
            memory_ids (list[str]): 要删除的记忆ID列表。

        返回:
            bool: 删除成功返回True,记忆不存在或失败返回False。
        """
        pass

    @abstractmethod
    def trim_collection(self, collection: T) -> bool:
        """
        清理过时记忆数据。

        参数:
            collection (T): 目标集合实例。

        返回:
            bool: 清理成功或无需清理返回True,失败返回False。
        """
        pass
