"""dashscope 适配层测试。"""

import unittest
from http import HTTPStatus

import numpy as np

from context_retrieval.ir_compiler import DashScopeLLM
from context_retrieval.vector_search import DashScopeEmbeddingModel


class MockGeneration:
    """模拟 dashscope Generation 客户端。"""

    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls: list[dict] = []

    def call(self, model: str, messages: list[dict], **kwargs):
        """记录调用并返回带 output_text 的响应。"""
        self.calls.append({"model": model, "messages": messages, "kwargs": kwargs})
        return type("Resp", (), {"output_text": self.output_text})


class MockEmbeddingClient:
    """模拟 dashscope embedding 客户端。"""

    def __init__(self, embeddings: list[list[float]], status: HTTPStatus = HTTPStatus.OK):
        self.embeddings = embeddings
        self.status = status
        self.calls: list[dict] = []

    def call(self, model: str, input: list[str], **kwargs):
        """返回带 embedding 的响应。"""
        self.calls.append({"model": model, "input": input, "kwargs": kwargs})
        return type(
            "Resp",
            (),
            {
                "status_code": self.status,
                "output": {"embeddings": [{"embedding": e} for e in self.embeddings]},
                "message": "",
            },
        )


class TestDashScopeLLM(unittest.TestCase):
    """测试 DashScopeLLM。"""

    def test_parse_json_response(self):
        """能解析标准 JSON 文本。"""
        mock_gen = MockGeneration(
            output_text='{"action":{"text":"打开"},"name_hint":"老伙计"}'
        )
        llm = DashScopeLLM(generation_client=mock_gen, system_prompt="prompt")

        result = llm.parse("打开老伙计")

        self.assertEqual(result["action"]["text"], "打开")
        self.assertEqual(result["name_hint"], "老伙计")
        # 确认 prompt 与用户消息都传递出去了
        self.assertEqual(mock_gen.calls[0]["messages"][0]["content"], "prompt")
        self.assertEqual(mock_gen.calls[0]["messages"][1]["content"], "打开老伙计")

    def test_parse_handles_non_json(self):
        """包含非 JSON 文本时使用 fallback。"""
        mock_gen = MockGeneration(output_text="无法解析")
        llm = DashScopeLLM(generation_client=mock_gen)

        result = llm.parse("test")

        self.assertEqual(result.get("confidence"), 0)
        self.assertNotIn("action", result)


class TestDashScopeEmbeddingModel(unittest.TestCase):
    """测试 DashScopeEmbeddingModel。"""

    def test_encode_returns_numpy_array(self):
        """正常返回 embedding。"""
        mock_embeddings = [[0.1, 0.2], [0.3, 0.4]]
        client = MockEmbeddingClient(embeddings=mock_embeddings)
        model = DashScopeEmbeddingModel(embedding_client=client, model="text-embedding-v4")

        arr = model.encode(["a", "b"])

        self.assertIsInstance(arr, np.ndarray)
        self.assertEqual(arr.shape, (2, 2))
        self.assertAlmostEqual(float(arr[0][0]), 0.1, places=5)
        self.assertEqual(client.calls[0]["model"], "text-embedding-v4")

    def test_encode_raises_on_error_status(self):
        """错误状态码时抛出异常。"""
        client = MockEmbeddingClient(embeddings=[[0.1]], status=HTTPStatus.BAD_REQUEST)
        model = DashScopeEmbeddingModel(embedding_client=client)

        with self.assertRaises(RuntimeError):
            model.encode(["a"])


if __name__ == "__main__":
    unittest.main()
