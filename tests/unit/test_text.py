"""测试文本处理与模糊匹配工具。"""

import unittest

from context_retrieval.text import (
    contains_substring,
    exact_match,
    fuzzy_match_score,
    partial_match_score,
)


class TestFuzzyMatchScore(unittest.TestCase):
    """测试模糊匹配分数。"""

    def test_exact_match(self):
        """测试精确匹配返回 1.0。"""
        self.assertEqual(fuzzy_match_score("老伙计", "老伙计"), 1.0)

    def test_similar_match(self):
        """测试相似文本高分。"""
        score = fuzzy_match_score("客厅灯", "客厅的灯")
        self.assertGreater(score, 0.7)

    def test_no_match(self):
        """测试无关文本低分。"""
        score = fuzzy_match_score("客厅灯", "空调")
        self.assertLess(score, 0.5)

    def test_empty_strings(self):
        """测试空字符串返回 0。"""
        self.assertEqual(fuzzy_match_score("", "test"), 0.0)
        self.assertEqual(fuzzy_match_score("test", ""), 0.0)

    def test_chinese_nickname(self):
        """测试中文昵称匹配。"""
        score = fuzzy_match_score("大白", "大白空调")
        self.assertGreater(score, 0.5)


class TestPartialMatchScore(unittest.TestCase):
    """测试部分匹配分数。"""

    def test_substring(self):
        """测试子串匹配高分。"""
        score = partial_match_score("客厅的灯", "客厅")
        self.assertGreater(score, 0.9)

    def test_exact(self):
        """测试精确匹配返回 1.0。"""
        self.assertEqual(partial_match_score("老伙计", "老伙计"), 1.0)

    def test_no_overlap(self):
        """测试无重叠低分。"""
        score = partial_match_score("客厅灯", "卧室")
        self.assertLess(score, 0.5)

    def test_empty_strings(self):
        """测试空字符串返回 0。"""
        self.assertEqual(partial_match_score("", "test"), 0.0)


class TestContainsSubstring(unittest.TestCase):
    """测试子串包含检查。"""

    def test_contains(self):
        """测试包含关系。"""
        self.assertTrue(contains_substring("客厅灯", "客厅"))
        self.assertTrue(contains_substring("老伙计台灯", "老伙计"))

    def test_not_contains(self):
        """测试不包含关系。"""
        self.assertFalse(contains_substring("客厅灯", "卧室"))

    def test_exact_match(self):
        """测试精确匹配。"""
        self.assertTrue(contains_substring("灯", "灯"))

    def test_empty_strings(self):
        """测试空字符串。"""
        self.assertFalse(contains_substring("", "test"))
        self.assertFalse(contains_substring("test", ""))


class TestExactMatch(unittest.TestCase):
    """测试精确匹配。"""

    def test_exact(self):
        """测试精确匹配。"""
        self.assertTrue(exact_match("老伙计", "老伙计"))

    def test_not_exact(self):
        """测试不精确匹配。"""
        self.assertFalse(exact_match("老伙计", "老伙计灯"))


if __name__ == "__main__":
    unittest.main()
