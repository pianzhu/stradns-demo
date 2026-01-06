"""向量检索模块。

使用 sentence-transformers 或 dashscope embedding 进行语义相似度检索。
"""

import os
from abc import ABC, abstractmethod
from http import HTTPStatus
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from context_retrieval.doc_enrichment import CapabilityDoc, build_enriched_doc
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

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        spec_index: dict[str, list[CapabilityDoc]] | None = None,
    ):
        """初始化检索器。

        Args:
            embedding_model: Embedding 模型
            spec_index: spec.jsonl index
        """
        self.embedding_model = embedding_model
        self.spec_index = spec_index or {}
        self.devices: list[Device] = []
        self.embeddings: NDArray[np.float32] | None = None
        self._entries: list[tuple[str, str | None]] = []
        self._texts: list[str] = []

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
            self._entries, self._texts = self._build_corpus(devices)
            self.embeddings = self.embedding_model.encode(self._texts)
        else:
            self.embeddings = None
            self._entries = []
            self._texts = []

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
            device_id, capability_id = self._entries[idx]
            candidates.append(
                Candidate(
                    entity_id=device_id,
                    entity_kind="device",
                    capability_id=capability_id,
                    vector_score=score,
                    total_score=score,
                    reasons=["semantic_match"],
                )
            )

        return candidates

    def _build_corpus(
        self, devices: list[Device]
    ) -> tuple[list[tuple[str, str | None]], list[str]]:
        entries: list[tuple[str, str | None]] = []
        texts: list[str] = []

        for device in devices:
            profile_id = getattr(device, "profile_id", None) or getattr(
                device, "profileId", None
            )
            spec_docs = self.spec_index.get(profile_id) if profile_id else None
            docs = build_enriched_doc(device, self.spec_index)

            if spec_docs and len(docs) == len(spec_docs):
                for doc, spec_doc in zip(docs, spec_docs):
                    entries.append((device.id, spec_doc.id))
                    texts.append(doc)
                continue

            for doc in docs:
                entries.append((device.id, None))
                texts.append(doc)

        return entries, texts


class DashScopeEmbeddingModel:
    """基于 dashscope 的 embedding 模型实现。"""

    def __init__(
        self,
        model: str = "text-embedding-v4",
        api_key: str | None = None,
        embedding_client: Any | None = None,
    ):
        """初始化。

        Args:
            model: 模型名称，默认 text-embedding-v4
            api_key: API Key，未提供时从 `DASHSCOPE_API_KEY` 读取
            embedding_client: 可注入的 embedding 客户端，便于测试
        """
        self.model = model

        if embedding_client is not None:
            self._embedding = embedding_client
            self._dashscope = None
            return

        try:
            import dashscope
        except ImportError as exc:  # pragma: no cover - 依赖缺失提示
            raise ImportError("需要安装 dashscope 才能使用 DashScopeEmbeddingModel") from exc

        api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            dashscope.api_key = api_key

        embedding_class = getattr(dashscope, "TextEmbedding", None)
        if embedding_class is None:
            try:
                from dashscope import embeddings as embedding_mod

                embedding_class = getattr(embedding_mod, "Embedding")
            except Exception as exc:  # pragma: no cover - 避免依赖差异导致崩溃
                raise ImportError("未找到 dashscope TextEmbedding/Embedding 接口") from exc

        self._embedding = embedding_class
        self._dashscope = dashscope

    def encode(self, texts: list[str], batch_size: int = 10) -> NDArray[np.float32]:
        """编码文本列表为向量数组。

        Args:
            texts: 文本列表
            batch_size: 每批处理的文本数量，dashscope 限制最大 10

        Returns:
            向量数组，shape=(len(texts), dim)
        """
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        all_vectors = []

        # 分批处理以避免 batch size 限制
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            response = self._embedding.call(
                model=self.model,
                input=batch,
            )
            self._ensure_success(response)

            output = getattr(response, "output", None)
            if output is None and hasattr(response, "get"):
                output = response.get("output", {})
            if output is None:
                output = {}

            embeddings = None
            if hasattr(output, "get"):
                embeddings = output.get("embeddings")
            elif isinstance(output, dict):
                embeddings = output.get("embeddings")

            if not embeddings:
                raise ValueError(f"dashscope 未返回 embeddings 结果 (batch {i // batch_size})")

            for item in embeddings:
                if not isinstance(item, dict):
                    continue
                vector = item.get("embedding")
                if vector is not None:
                    all_vectors.append(np.asarray(vector, dtype=np.float32))

        if not all_vectors:
            raise ValueError("dashscope 返回的 embedding 为空")

        return np.vstack(all_vectors)

    def encode_enriched_docs(
        self,
        devices: list[Device],
        spec_index: dict[str, list[CapabilityDoc]] | None = None,
    ) -> tuple[list[tuple[str, str | None]], NDArray[np.float32]]:
        """Encode enriched documents with device/capability mapping."""
        corpus_entries, texts = self._build_command_corpus(devices, spec_index or {})
        embeddings = self.encode(texts)
        return corpus_entries, embeddings

    def _ensure_success(self, response: Any) -> None:
        """校验 dashscope 响应状态。"""
        status = getattr(response, "status_code", None)
        if status is not None and status != HTTPStatus.OK:
            message = getattr(response, "message", "") or getattr(
                response, "error", ""
            )
            raise RuntimeError(f"dashscope 调用失败: {status} {message}")

    def _build_command_corpus(
        self,
        devices: list[Device],
        spec_index: dict[str, list[CapabilityDoc]],
    ) -> tuple[list[tuple[str, str | None]], list[str]]:
        entries: list[tuple[str, str | None]] = []
        texts: list[str] = []

        for device in devices:
            profile_id = getattr(device, "profile_id", None) or getattr(
                device, "profileId", None
            )
            spec_docs = spec_index.get(profile_id) if profile_id else None
            docs = build_enriched_doc(device, spec_index)

            if spec_docs and len(docs) == len(spec_docs):
                for doc, spec_doc in zip(docs, spec_docs):
                    entries.append((device.id, spec_doc.id))
                    texts.append(doc)
                continue

            for doc in docs:
                entries.append((device.id, None))
                texts.append(doc)

        return entries, texts

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
