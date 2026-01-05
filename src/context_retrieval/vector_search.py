"""向量检索模块。

使用 sentence-transformers 进行语义相似度检索。
"""

from abc import ABC, abstractmethod
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from context_retrieval.models import Candidate, Device


class EmbeddingModel(Protocol):
    """Embedding 模型协议。"""

    def encode(self, texts: list[str]) -> NDArray[np.float32]:
        """将文本编码为向量。

        Args:
            texts: 文本列表

        Returns:
            向量数组，shape=(len(texts), dim)
        """
        ...


class VectorSearcher(ABC):
    """向量检索器抽象基类。"""

    @abstractmethod
    def index(self, devices: list[Device]) -> None:
        """索引设备。

        Args:
            devices: 设备列表
        """
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> list[Candidate]:
        """执行向量检索。

        Args:
            query: 查询文本
            top_k: 返回的最大候选数

        Returns:
            候选列表，按相似度降序排列
        """
        ...


class SentenceTransformerSearcher(VectorSearcher):
    """基于 sentence-transformers 的向量检索器。"""

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """初始化检索器。

        Args:
            model_name: sentence-transformers 模型名称
                默认使用多语言小模型，支持中文
        """
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.devices: list[Device] = []
        self.embeddings: NDArray[np.float32] | None = None
        self.device_texts: list[str] = []

    def _device_to_text(self, device: Device) -> str:
        """将设备转换为文本用于 embedding。

        Args:
            device: 设备

        Returns:
            设备描述文本
        """
        # 组合设备的关键信息
        parts = [device.name, device.room, device.type]

        # 添加命令描述
        for cmd in device.commands:
            if cmd.description:
                parts.append(cmd.description)

        return " ".join(parts)

    def index(self, devices: list[Device]) -> None:
        """索引设备。"""
        self.devices = devices
        self.device_texts = [self._device_to_text(d) for d in devices]

        if self.device_texts:
            self.embeddings = self.model.encode(
                self.device_texts,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        else:
            self.embeddings = None

    def search(self, query: str, top_k: int = 10) -> list[Candidate]:
        """执行向量检索。"""
        if self.embeddings is None or len(self.devices) == 0:
            return []

        # 编码查询
        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]

        # 计算余弦相似度
        similarities = self._cosine_similarity(query_embedding, self.embeddings)

        # 获取 top-k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        candidates = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0:  # 只返回正相似度的结果
                candidates.append(
                    Candidate(
                        entity_id=self.devices[idx].id,
                        entity_kind="device",
                        vector_score=score,
                        total_score=score,
                        reasons=["semantic_match"],
                    )
                )

        return candidates

    def _cosine_similarity(
        self, query: NDArray[np.float32], corpus: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        """计算余弦相似度。"""
        query_norm = query / (np.linalg.norm(query) + 1e-8)
        corpus_norm = corpus / (np.linalg.norm(corpus, axis=1, keepdims=True) + 1e-8)
        return corpus_norm @ query_norm


class InMemoryVectorSearcher(VectorSearcher):
    """内存向量检索器（使用外部 embedding 模型）。

    适用于需要自定义 embedding 模型的场景。
    """

    def __init__(self, embedding_model: EmbeddingModel):
        """初始化检索器。

        Args:
            embedding_model: Embedding 模型
        """
        self.embedding_model = embedding_model
        self.devices: list[Device] = []
        self.embeddings: NDArray[np.float32] | None = None

    def _device_to_text(self, device: Device) -> str:
        """将设备转换为文本。"""
        parts = [device.name, device.room, device.type]
        for cmd in device.commands:
            if cmd.description:
                parts.append(cmd.description)
        return " ".join(parts)

    def index(self, devices: list[Device]) -> None:
        """索引设备。"""
        self.devices = devices
        if devices:
            texts = [self._device_to_text(d) for d in devices]
            self.embeddings = self.embedding_model.encode(texts)
        else:
            self.embeddings = None

    def search(self, query: str, top_k: int = 10) -> list[Candidate]:
        """执行向量检索。"""
        if self.embeddings is None or len(self.devices) == 0:
            return []

        query_embedding = self.embedding_model.encode([query])[0]

        # 余弦相似度
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        corpus_norm = self.embeddings / (
            np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-8
        )
        similarities = corpus_norm @ query_norm

        top_indices = np.argsort(similarities)[::-1][:top_k]

        candidates = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0:
                candidates.append(
                    Candidate(
                        entity_id=self.devices[idx].id,
                        entity_kind="device",
                        vector_score=score,
                        total_score=score,
                        reasons=["semantic_match"],
                    )
                )

        return candidates


class StubVectorSearcher(VectorSearcher):
    """Stub 向量检索器（用于测试）。

    返回预设的结果，不执行实际的向量计算。
    """

    def __init__(self, stub_results: dict[str, list[tuple[str, float]]] | None = None):
        """初始化 Stub 检索器。

        Args:
            stub_results: 预设结果映射 {query: [(device_id, score), ...]}
        """
        self.stub_results = stub_results or {}
        self.devices: list[Device] = []

    def index(self, devices: list[Device]) -> None:
        """索引设备（Stub 实现）。"""
        self.devices = devices

    def search(self, query: str, top_k: int = 10) -> list[Candidate]:
        """执行检索（返回预设结果）。"""
        results = self.stub_results.get(query, [])

        candidates = []
        for device_id, score in results[:top_k]:
            candidates.append(
                Candidate(
                    entity_id=device_id,
                    entity_kind="device",
                    vector_score=score,
                    total_score=score,
                    reasons=["semantic_match"],
                )
            )

        return candidates
