"""测试候选融合与评分模块。"""

import unittest

from context_retrieval.models import Candidate
from context_retrieval.scoring import (
    filter_by_threshold,
    merge_and_score,
    normalize_scores,
)


class TestMergeAndScore(unittest.TestCase):
    """测试候选合并与评分。"""

    def test_merge_disjoint(self):
        """测试不相交的候选合并。"""
        keyword = [
            Candidate(
                entity_id="lamp-1",
                keyword_score=0.8,
                reasons=["name_exact"],
            )
        ]
        vector = [
            Candidate(
                entity_id="lamp-2",
                vector_score=0.6,
                reasons=["semantic_match"],
            )
        ]

        merged = merge_and_score(keyword, vector)

        self.assertEqual(len(merged), 2)
        # lamp-1 分数更高（0.8 * 1.0 = 0.8 vs 0.6 * 0.5 = 0.3）
        self.assertEqual(merged[0].entity_id, "lamp-1")
        self.assertEqual(merged[1].entity_id, "lamp-2")

    def test_merge_overlapping(self):
        """测试重叠候选合并。"""
        keyword = [
            Candidate(
                entity_id="lamp-1",
                keyword_score=0.8,
                reasons=["name_exact"],
            )
        ]
        vector = [
            Candidate(
                entity_id="lamp-1",
                vector_score=0.7,
                reasons=["semantic_match"],
            )
        ]

        merged = merge_and_score(keyword, vector)

        self.assertEqual(len(merged), 1)
        # 合并分数：0.8 * 1.0 + 0.7 * 0.5 = 1.15
        self.assertAlmostEqual(merged[0].total_score, 1.15)
        # 合并 reasons
        self.assertIn("name_exact", merged[0].reasons)
        self.assertIn("semantic_match", merged[0].reasons)

    def test_merge_with_capability_ids_applies_keyword_score(self):
        """Applies keyword score to each capability-level candidate."""
        keyword = [
            Candidate(entity_id="lamp-1", keyword_score=0.8, reasons=["name_exact"])
        ]
        vector = [
            Candidate(
                entity_id="lamp-1",
                capability_id="cap-on",
                vector_score=0.6,
                reasons=["semantic_match"],
            ),
            Candidate(
                entity_id="lamp-1",
                capability_id="cap-off",
                vector_score=0.4,
                reasons=["semantic_match"],
            ),
        ]

        merged = merge_and_score(keyword, vector, w_keyword=1.0, w_vector=0.5)

        self.assertEqual({c.capability_id for c in merged}, {"cap-on", "cap-off"})
        self.assertTrue(all(c.keyword_score == 0.8 for c in merged))
        self.assertTrue(all(c.capability_id is not None for c in merged))

    def test_merge_empty(self):
        """测试空候选合并。"""
        merged = merge_and_score([], [])
        self.assertEqual(len(merged), 0)

    def test_merge_one_empty(self):
        """测试一个为空的合并。"""
        keyword = [
            Candidate(entity_id="lamp-1", keyword_score=0.8)
        ]

        merged = merge_and_score(keyword, [])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].keyword_score, 0.8)

    def test_custom_weights(self):
        """测试自定义权重。"""
        keyword = [
            Candidate(entity_id="lamp-1", keyword_score=0.5)
        ]
        vector = [
            Candidate(entity_id="lamp-1", vector_score=0.5)
        ]

        # 使用不同权重
        merged = merge_and_score(keyword, vector, w_keyword=0.5, w_vector=1.0)

        # 0.5 * 0.5 + 0.5 * 1.0 = 0.75
        self.assertAlmostEqual(merged[0].total_score, 0.75)

    def test_ordering(self):
        """测试按分数排序。"""
        keyword = [
            Candidate(entity_id="lamp-1", keyword_score=0.5),
            Candidate(entity_id="lamp-2", keyword_score=0.9),
        ]

        merged = merge_and_score(keyword, [])

        # lamp-2 应该排第一
        self.assertEqual(merged[0].entity_id, "lamp-2")


class TestNormalizeScores(unittest.TestCase):
    """测试分数归一化。"""

    def test_normalize(self):
        """测试归一化。"""
        candidates = [
            Candidate(entity_id="a", total_score=0.4),
            Candidate(entity_id="b", total_score=0.8),
            Candidate(entity_id="c", total_score=0.6),
        ]

        normalized = normalize_scores(candidates)

        # 最高分应为 1.0，最低分应为 0.0
        scores = {c.entity_id: c.total_score for c in normalized}
        self.assertAlmostEqual(scores["b"], 1.0)
        self.assertAlmostEqual(scores["a"], 0.0)
        self.assertAlmostEqual(scores["c"], 0.5)

    def test_normalize_same_scores(self):
        """测试相同分数归一化。"""
        candidates = [
            Candidate(entity_id="a", total_score=0.5),
            Candidate(entity_id="b", total_score=0.5),
        ]

        normalized = normalize_scores(candidates)

        # 所有分数应为 1.0
        for c in normalized:
            self.assertAlmostEqual(c.total_score, 1.0)

    def test_normalize_empty(self):
        """测试空列表归一化。"""
        normalized = normalize_scores([])
        self.assertEqual(len(normalized), 0)


class TestFilterByThreshold(unittest.TestCase):
    """测试阈值过滤。"""

    def test_filter(self):
        """测试过滤。"""
        candidates = [
            Candidate(entity_id="a", total_score=0.5),
            Candidate(entity_id="b", total_score=0.2),
            Candidate(entity_id="c", total_score=0.8),
        ]

        filtered = filter_by_threshold(candidates, threshold=0.3)

        self.assertEqual(len(filtered), 2)
        ids = {c.entity_id for c in filtered}
        self.assertIn("a", ids)
        self.assertIn("c", ids)
        self.assertNotIn("b", ids)

    def test_filter_all_pass(self):
        """测试全部通过。"""
        candidates = [
            Candidate(entity_id="a", total_score=0.5),
        ]

        filtered = filter_by_threshold(candidates, threshold=0.3)
        self.assertEqual(len(filtered), 1)

    def test_filter_none_pass(self):
        """测试全部过滤。"""
        candidates = [
            Candidate(entity_id="a", total_score=0.1),
        ]

        filtered = filter_by_threshold(candidates, threshold=0.3)
        self.assertEqual(len(filtered), 0)


if __name__ == "__main__":
    unittest.main()
