"""候选筛选与排序测试。"""

import unittest
from context_retrieval.models import Candidate
from context_retrieval.gating import select_top, DEFAULT_TOP_K, DEFAULT_CLOSE_THRESHOLD


class TestSelectTop(unittest.TestCase):
    """测试 select_top 函数。"""

    def test_empty_candidates(self):
        """空候选返回空结果。"""
        result = select_top([])
        self.assertEqual(result.candidates, [])
        self.assertIsNone(result.hint)

    def test_single_candidate(self):
        """单一候选直接返回。"""
        c = Candidate(entity_id="lamp-1", total_score=0.9)
        result = select_top([c])
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].entity_id, "lamp-1")
        self.assertIsNone(result.hint)

    def test_sorted_by_score_descending(self):
        """结果按分数降序排列。"""
        c1 = Candidate(entity_id="lamp-1", total_score=0.5)
        c2 = Candidate(entity_id="lamp-2", total_score=0.9)
        c3 = Candidate(entity_id="lamp-3", total_score=0.7)
        result = select_top([c1, c2, c3])
        self.assertEqual(result.candidates[0].entity_id, "lamp-2")
        self.assertEqual(result.candidates[1].entity_id, "lamp-3")
        self.assertEqual(result.candidates[2].entity_id, "lamp-1")

    def test_top_k_limit(self):
        """top_k 限制生效。"""
        candidates = [Candidate(entity_id=f"lamp-{i}", total_score=0.9 - i * 0.1) for i in range(10)]
        result = select_top(candidates, top_k=3)
        self.assertEqual(len(result.candidates), 3)

    def test_default_top_k(self):
        """默认 top_k 值。"""
        self.assertEqual(DEFAULT_TOP_K, 5)

    def test_clear_winner_no_hint(self):
        """分差足够时无提示。"""
        c1 = Candidate(entity_id="lamp-1", total_score=0.9)
        c2 = Candidate(entity_id="lamp-2", total_score=0.5)
        result = select_top([c1, c2])
        self.assertIsNone(result.hint)

    def test_close_scores_hint(self):
        """分数接近时返回提示。"""
        c1 = Candidate(entity_id="lamp-1", total_score=0.85)
        c2 = Candidate(entity_id="lamp-2", total_score=0.83)
        result = select_top([c1, c2], close_threshold=0.1)
        self.assertEqual(result.hint, "multiple_close_matches")

    def test_custom_close_threshold(self):
        """自定义 close_threshold。"""
        c1 = Candidate(entity_id="lamp-1", total_score=0.9)
        c2 = Candidate(entity_id="lamp-2", total_score=0.85)
        # 分差 0.05，threshold=0.03 无提示，threshold=0.1 有提示
        result_no_hint = select_top([c1, c2], close_threshold=0.03)
        self.assertIsNone(result_no_hint.hint)

        result_with_hint = select_top([c1, c2], close_threshold=0.1)
        self.assertEqual(result_with_hint.hint, "multiple_close_matches")

    def test_default_close_threshold(self):
        """默认 close_threshold 值。"""
        self.assertEqual(DEFAULT_CLOSE_THRESHOLD, 0.1)


if __name__ == "__main__":
    unittest.main()
