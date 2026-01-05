"""测试向量检索模块。"""

import unittest

import numpy as np

from context_retrieval.models import CommandSpec, Device
from context_retrieval.vector_search import (
    InMemoryVectorSearcher,
    StubVectorSearcher,
)


class MockEmbeddingModel:
    """Mock Embedding 模型用于测试。"""

    def __init__(self, dim: int = 8):
        self.dim = dim
        self._cache: dict[str, np.ndarray] = {}

    def encode(self, texts: list[str]) -> np.ndarray:
        """生成伪随机但确定性的向量。"""
        embeddings = []
        for text in texts:
            if text not in self._cache:
                # 基于文本哈希生成确定性向量
                np.random.seed(hash(text) % (2**31))
                self._cache[text] = np.random.randn(self.dim).astype(np.float32)
            embeddings.append(self._cache[text])
        return np.array(embeddings)


class TestStubVectorSearcher(unittest.TestCase):
    """测试 Stub 向量检索器。"""

    def setUp(self):
        """设置测试数据。"""
        self.devices = [
            Device(id="lamp-1", name="老伙计", room="客厅", type="switch"),
            Device(id="lamp-2", name="台灯", room="卧室", type="light"),
        ]

    def test_stub_returns_preset_results(self):
        """测试 Stub 返回预设结果。"""
        stub_results = {
            "打开灯": [("lamp-1", 0.9), ("lamp-2", 0.8)],
        }
        searcher = StubVectorSearcher(stub_results)
        searcher.index(self.devices)

        candidates = searcher.search("打开灯")

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].entity_id, "lamp-1")
        self.assertEqual(candidates[0].vector_score, 0.9)

    def test_stub_empty_query(self):
        """测试 Stub 对未知查询返回空。"""
        searcher = StubVectorSearcher({})
        searcher.index(self.devices)

        candidates = searcher.search("未知查询")
        self.assertEqual(len(candidates), 0)

    def test_stub_top_k(self):
        """测试 Stub 的 top_k 限制。"""
        stub_results = {
            "查询": [("lamp-1", 0.9), ("lamp-2", 0.8)],
        }
        searcher = StubVectorSearcher(stub_results)
        searcher.index(self.devices)

        candidates = searcher.search("查询", top_k=1)
        self.assertEqual(len(candidates), 1)


class TestInMemoryVectorSearcher(unittest.TestCase):
    """测试内存向量检索器。"""

    def setUp(self):
        """设置测试数据。"""
        self.devices = [
            Device(
                id="lamp-1",
                name="客厅灯",
                room="客厅",
                type="light",
                commands=[CommandSpec(id="on", description="打开")],
            ),
            Device(
                id="lamp-2",
                name="卧室灯",
                room="卧室",
                type="light",
                commands=[CommandSpec(id="on", description="打开")],
            ),
            Device(
                id="ac-1",
                name="空调",
                room="客厅",
                type="airConditioner",
                commands=[CommandSpec(id="on", description="打开")],
            ),
        ]
        self.model = MockEmbeddingModel(dim=8)
        self.searcher = InMemoryVectorSearcher(self.model)

    def test_index_and_search(self):
        """测试索引和搜索。"""
        self.searcher.index(self.devices)

        candidates = self.searcher.search("客厅的灯")

        self.assertGreater(len(candidates), 0)
        # 检查返回的是有效的设备 ID
        for c in candidates:
            self.assertIn(c.entity_id, ["lamp-1", "lamp-2", "ac-1"])
            self.assertIn("semantic_match", c.reasons)

    def test_empty_index(self):
        """测试空索引。"""
        self.searcher.index([])
        candidates = self.searcher.search("任意查询")
        self.assertEqual(len(candidates), 0)

    def test_top_k_limit(self):
        """测试 top_k 限制。"""
        self.searcher.index(self.devices)
        candidates = self.searcher.search("灯", top_k=2)
        self.assertLessEqual(len(candidates), 2)

    def test_score_in_range(self):
        """测试分数在合理范围内。"""
        self.searcher.index(self.devices)
        candidates = self.searcher.search("灯")

        for c in candidates:
            self.assertGreaterEqual(c.vector_score, -1.0)
            self.assertLessEqual(c.vector_score, 1.0)


class TestSentenceTransformerSearcher(unittest.TestCase):
    """测试 sentence-transformers 检索器。

    这些测试需要安装 sentence-transformers，
    在 CI 环境中可能被跳过。
    """

    @classmethod
    def setUpClass(cls):
        """检查 sentence-transformers 是否可用。"""
        try:
            from sentence_transformers import SentenceTransformer

            cls.has_sentence_transformers = True
        except ImportError:
            cls.has_sentence_transformers = False

    def setUp(self):
        """设置测试数据。"""
        if not self.has_sentence_transformers:
            self.skipTest("sentence-transformers not installed")

        from context_retrieval.vector_search import SentenceTransformerSearcher

        self.devices = [
            Device(
                id="lamp-1",
                name="客厅的台灯",
                room="客厅",
                type="light",
                commands=[CommandSpec(id="on", description="打开灯")],
            ),
            Device(
                id="ac-1",
                name="客厅空调",
                room="客厅",
                type="airConditioner",
                commands=[CommandSpec(id="on", description="打开空调")],
            ),
        ]
        # 使用小模型加快测试
        self.searcher = SentenceTransformerSearcher(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )

    def test_semantic_search(self):
        """测试语义搜索。"""
        self.searcher.index(self.devices)

        # 查询"灯"应该返回灯相关设备
        candidates = self.searcher.search("打开灯")

        self.assertGreater(len(candidates), 0)
        # 灯应该比空调更相关
        lamp_candidate = next(
            (c for c in candidates if c.entity_id == "lamp-1"), None
        )
        self.assertIsNotNone(lamp_candidate)


if __name__ == "__main__":
    unittest.main()
