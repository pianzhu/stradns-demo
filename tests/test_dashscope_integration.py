"""dashscope 集成测试。

使用真实的 dashscope API (qwen-flash + text-embedding-v4) 进行端到端验证。

运行条件：
- 需要设置 DASHSCOPE_API_KEY 环境变量
- 需要设置 RUN_DASHSCOPE_IT=1 环境变量启用测试
- 缺失任一条件时测试会被跳过

可配置参数（通过环境变量）：
- DASHSCOPE_TOP_N: embedding 召回 top-N，默认 10
- DASHSCOPE_MAX_QUERIES: 最大测试用例数，默认无限制
- DASHSCOPE_LLM_MODEL: LLM 模型名称，默认 qwen-flash
- DASHSCOPE_EMBEDDING_MODEL: embedding 模型名称，默认 text-embedding-v4

运行示例：
    DASHSCOPE_API_KEY=xxx RUN_DASHSCOPE_IT=1 python -m pytest tests/test_dashscope_integration.py -v
"""

import json
import os
import time
import unittest
from pathlib import Path
from typing import Any

import numpy as np

# 运行开关
SKIP_REASON = None
if not os.getenv("RUN_DASHSCOPE_IT"):
    SKIP_REASON = "需要设置 RUN_DASHSCOPE_IT=1 启用 dashscope 集成测试"
elif not os.getenv("DASHSCOPE_API_KEY"):
    SKIP_REASON = "需要设置 DASHSCOPE_API_KEY 环境变量"

# 可配置参数
TOP_N = int(os.getenv("DASHSCOPE_TOP_N", "10"))
MAX_QUERIES = int(os.getenv("DASHSCOPE_MAX_QUERIES", "0")) or None
LLM_MODEL = os.getenv("DASHSCOPE_LLM_MODEL", "qwen-flash")
EMBEDDING_MODEL = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")


def load_test_queries() -> list[dict[str, Any]]:
    """加载测试用例集。"""
    queries_path = Path(__file__).parent / "dashscope_integration_queries.json"
    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)
    if MAX_QUERIES:
        queries = queries[:MAX_QUERIES]
    return queries


def load_capabilities() -> list[dict[str, Any]]:
    """从 spec.jsonl 加载命令能力描述。"""
    spec_path = Path(__file__).parent.parent / "src" / "spec.jsonl"
    with open(spec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    capabilities = []
    for profile in data:
        profile_id = profile.get("profileId", "")
        for cap in profile.get("capabilities", []):
            cap_id = cap.get("id", "")
            description = cap.get("description", "")
            capabilities.append({
                "id": cap_id,
                "description": description,
                "profile_id": profile_id,
                "text": f"{cap_id} {description}",
            })
    return capabilities


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopeLLMIntegration(unittest.TestCase):
    """dashscope LLM 解析集成测试。"""

    @classmethod
    def setUpClass(cls):
        """初始化 LLM 客户端。"""
        from context_retrieval.ir_compiler import DashScopeLLM

        cls.llm = DashScopeLLM(model=LLM_MODEL)
        cls.queries = load_test_queries()

    def test_llm_parse_action_text_coverage(self):
        """测试 LLM 解析 action.text 的覆盖率。

        action.kind 已移除，action.text 作为 embedding 检索的主查询文本。
        action.text 为空时允许 fallback 到原始 query，但会降低召回质量，因此需要监控覆盖率。
        """
        total = 0
        has_text = 0
        results = []

        for case in self.queries:
            query = case["query"]
            expected_cap_ids = case.get("expected_capability_ids", [])
            if not expected_cap_ids:
                continue

            total += 1
            try:
                result = self.llm.parse(query)
                action_text = (result.get("action") or {}).get("text", "")
                ok = isinstance(action_text, str) and bool(action_text.strip())
                if ok:
                    has_text += 1
                    results.append((query, "PASS", action_text))
                else:
                    results.append((query, "FAIL", action_text))

                time.sleep(0.1)

            except Exception as e:
                results.append((query, "ERROR", str(e)))

        coverage = has_text / total if total > 0 else 0

        print(f"\n=== LLM action.text 覆盖率 ===")
        print(f"总用例数: {total}")
        print(f"非空 action.text: {has_text}")
        print(f"覆盖率: {coverage:.2%}")

        failed = [r for r in results if r[1] != "PASS"]
        if failed:
            print("\n失败用例:")
            for query, status, actual in failed[:10]:
                print(f"  [{status}] {query}: action.text={actual!r}")

        # 断言覆盖率 >= 60%（允许一定误差与波动）
        self.assertGreaterEqual(
            coverage, 0.6, f"action.text 覆盖率应 >= 60%，实际 {coverage:.2%}"
        )

    def test_llm_parse_scope_include(self):
        """测试 LLM 解析 scope_include 的准确率。"""
        total = 0
        correct = 0
        results = []

        for case in self.queries:
            query = case["query"]
            expected = case.get("expected_fields", {})
            expected_scope = expected.get("scope_include", [])

            if not expected_scope:
                continue

            total += 1
            try:
                result = self.llm.parse(query)
                actual_scope = result.get("scope_include", [])

                # 检查期望的 scope 是否在实际结果中
                expected_set = set(expected_scope)
                actual_set = set(actual_scope)

                # 只要包含期望的房间即可
                if expected_set <= actual_set or expected_set == actual_set:
                    correct += 1
                    results.append((query, "PASS", expected_scope, actual_scope))
                else:
                    results.append((query, "FAIL", expected_scope, actual_scope))

                time.sleep(0.1)

            except Exception as e:
                results.append((query, "ERROR", expected_scope, str(e)))

        accuracy = correct / total if total > 0 else 0

        print(f"\n=== LLM scope_include 解析结果 ===")
        print(f"总用例数: {total}")
        print(f"正确数: {correct}")
        print(f"准确率: {accuracy:.2%}")

        failed = [r for r in results if r[1] != "PASS"]
        if failed:
            print("失败用例:")
            for query, status, expected, actual in failed[:10]:
                print(f"  [{status}] {query}: 期望 {expected}, 实际 {actual}")

        self.assertGreaterEqual(accuracy, 0.6, f"scope_include 准确率应 >= 60%，实际 {accuracy:.2%}")


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopeEmbeddingIntegration(unittest.TestCase):
    """dashscope embedding 召回集成测试。"""

    @classmethod
    def setUpClass(cls):
        """初始化 embedding 模型和索引。"""
        from context_retrieval.ir_compiler import DashScopeLLM
        from context_retrieval.vector_search import DashScopeEmbeddingModel

        cls.llm = DashScopeLLM(model=LLM_MODEL)
        cls.embedding_model = DashScopeEmbeddingModel(model=EMBEDDING_MODEL)
        cls.queries = load_test_queries()
        cls.capabilities = load_capabilities()

        # 构建命令 embedding 索引
        cls.cap_texts = [cap["text"] for cap in cls.capabilities]
        cls.cap_ids = [cap["id"] for cap in cls.capabilities]

        print(f"\n正在构建 embedding 索引，共 {len(cls.capabilities)} 个命令...")
        cls.cap_embeddings = cls.embedding_model.encode(cls.cap_texts)
        print(f"索引构建完成，向量维度: {cls.cap_embeddings.shape}")

    def _search_top_n(self, query_text: str, top_n: int = TOP_N) -> list[tuple[str, float]]:
        """执行 top-N 检索。"""
        query_embedding = self.embedding_model.encode([query_text])[0]

        # 余弦相似度
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        corpus_norm = self.cap_embeddings / (
            np.linalg.norm(self.cap_embeddings, axis=1, keepdims=True) + 1e-8
        )
        similarities = corpus_norm @ query_norm

        top_indices = np.argsort(similarities)[::-1][:top_n]

        results = []
        for idx in top_indices:
            cap_id = self.cap_ids[idx]
            score = float(similarities[idx])
            results.append((cap_id, score))

        return results

    def test_embedding_recall_with_action_text(self):
        """测试使用 QueryIR.action.text 进行 embedding 召回。"""
        total = 0
        hits = 0
        results = []

        for case in self.queries:
            query = case["query"]
            expected_cap_ids = case.get("expected_capability_ids", [])

            if not expected_cap_ids:
                continue

            total += 1
            try:
                # 先调用 LLM 得到 QueryIR
                ir = self.llm.parse(query)
                action_text = ir.get("action", {}).get("text", "")

                # 使用 action.text，为空则 fallback 到原始 query
                search_text = action_text if action_text else query

                # 执行 embedding 检索
                top_results = self._search_top_n(search_text, TOP_N)
                top_cap_ids = [cap_id for cap_id, _ in top_results]

                # 检查期望的 capability_id 是否在 top-N 中
                hit = any(cap_id in top_cap_ids for cap_id in expected_cap_ids)

                if hit:
                    hits += 1
                    results.append((query, "HIT", expected_cap_ids, top_cap_ids[:3], search_text))
                else:
                    results.append((query, "MISS", expected_cap_ids, top_cap_ids[:3], search_text))

                time.sleep(0.1)

            except Exception as e:
                results.append((query, "ERROR", expected_cap_ids, [], str(e)))

        hit_rate = hits / total if total > 0 else 0

        print(f"\n=== Embedding 召回结果 (action.text -> top-{TOP_N}) ===")
        print(f"总用例数: {total}")
        print(f"命中数: {hits}")
        print(f"top-{TOP_N} 命中率: {hit_rate:.2%}")

        # 输出未命中用例
        missed = [r for r in results if r[1] == "MISS"]
        if missed:
            print(f"\n未命中用例 (共 {len(missed)} 个):")
            for query, status, expected, actual_top3, search_text in missed[:10]:
                print(f"  query: {query}")
                print(f"    search_text: {search_text}")
                print(f"    期望: {expected}")
                print(f"    top-3: {actual_top3}")

        # 断言 top-N 命中率 >= 60%
        self.assertGreaterEqual(hit_rate, 0.6, f"top-{TOP_N} 命中率应 >= 60%，实际 {hit_rate:.2%}")

    def test_embedding_recall_with_raw_query(self):
        """测试使用原始 query 进行 embedding 召回（对照组）。"""
        total = 0
        hits = 0
        results = []

        for case in self.queries:
            query = case["query"]
            expected_cap_ids = case.get("expected_capability_ids", [])

            if not expected_cap_ids:
                continue

            total += 1
            try:
                # 直接使用原始 query 进行检索
                top_results = self._search_top_n(query, TOP_N)
                top_cap_ids = [cap_id for cap_id, _ in top_results]

                hit = any(cap_id in top_cap_ids for cap_id in expected_cap_ids)

                if hit:
                    hits += 1
                    results.append((query, "HIT", expected_cap_ids, top_cap_ids[:3]))
                else:
                    results.append((query, "MISS", expected_cap_ids, top_cap_ids[:3]))

            except Exception as e:
                results.append((query, "ERROR", expected_cap_ids, []))

        hit_rate = hits / total if total > 0 else 0

        print(f"\n=== Embedding 召回结果 (raw query -> top-{TOP_N}) ===")
        print(f"总用例数: {total}")
        print(f"命中数: {hits}")
        print(f"top-{TOP_N} 命中率: {hit_rate:.2%}")

        # 仅输出统计，不做断言（对照组）


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopePipelineIntegration(unittest.TestCase):
    """dashscope 端到端 pipeline 集成测试。"""

    @classmethod
    def setUpClass(cls):
        """初始化完整 pipeline。"""
        from context_retrieval.ir_compiler import DashScopeLLM
        from context_retrieval.vector_search import DashScopeEmbeddingModel

        cls.llm = DashScopeLLM(model=LLM_MODEL)
        cls.embedding_model = DashScopeEmbeddingModel(model=EMBEDDING_MODEL)
        cls.queries = load_test_queries()
        cls.capabilities = load_capabilities()

        # 构建索引
        cls.cap_texts = [cap["text"] for cap in cls.capabilities]
        cls.cap_ids = [cap["id"] for cap in cls.capabilities]
        cls.cap_embeddings = cls.embedding_model.encode(cls.cap_texts)

    def test_end_to_end_pipeline(self):
        """端到端 pipeline 测试：LLM 解析 + embedding 召回。"""
        total = 0
        action_text_present = 0
        action_text_fallback = 0
        recall_hits = 0
        both_ok = 0

        for case in self.queries[:10]:  # 仅测试前 10 个用例以节省配额
            query = case["query"]
            expected_cap_ids = case.get("expected_capability_ids", [])

            total += 1
            try:
                # Step 1: LLM 解析
                ir = self.llm.parse(query)
                action_text = (ir.get("action") or {}).get("text", "")
                if isinstance(action_text, str) and action_text.strip():
                    action_text_present += 1
                    search_text = action_text
                else:
                    action_text_fallback += 1
                    search_text = query

                # Step 2: Embedding 召回
                query_embedding = self.embedding_model.encode([search_text])[0]

                query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
                corpus_norm = self.cap_embeddings / (
                    np.linalg.norm(self.cap_embeddings, axis=1, keepdims=True) + 1e-8
                )
                similarities = corpus_norm @ query_norm

                top_indices = np.argsort(similarities)[::-1][:TOP_N]
                top_cap_ids = [self.cap_ids[idx] for idx in top_indices]

                recall_hit = any(cap_id in top_cap_ids for cap_id in expected_cap_ids) if expected_cap_ids else True
                if recall_hit and expected_cap_ids:
                    recall_hits += 1

                if recall_hit and isinstance(action_text, str) and action_text.strip():
                    both_ok += 1

                time.sleep(0.1)

            except Exception as e:
                print(f"ERROR: {query} - {e}")

        print(f"\n=== 端到端 Pipeline 结果 ===")
        print(f"总用例数: {total}")
        if total > 0:
            print(f"action.text 覆盖率: {action_text_present / total:.2%}")
            print(f"action.text fallback 率: {action_text_fallback / total:.2%}")
            print(f"top-{TOP_N} 召回命中率: {recall_hits / total:.2%}")
            print(f"action.text 非空且召回命中率: {both_ok / total:.2%}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
