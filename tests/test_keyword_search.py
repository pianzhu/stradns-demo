"""测试 Keyword 检索模块。"""

import unittest

from context_retrieval.keyword_search import KeywordSearcher
from context_retrieval.models import (
    ActionIntent,
    CommandSpec,
    Device,
    QueryIR,
)


class TestKeywordSearcher(unittest.TestCase):
    """测试关键词检索器。"""

    def setUp(self):
        """设置测试数据。"""
        self.devices = [
            Device(
                id="lamp-1",
                name="老伙计",
                room="客厅",
                type="smartthings:switch",
                commands=[
                    CommandSpec(id="main-switch-on", description="打开设备"),
                    CommandSpec(id="main-switch-off", description="关闭设备"),
                ],
            ),
            Device(
                id="lamp-2",
                name="台灯",
                room="卧室",
                type="smartthings:light",
                commands=[
                    CommandSpec(id="main-switch-on", description="打开设备"),
                ],
            ),
            Device(
                id="ac-1",
                name="大白",
                room="客厅",
                type="smartthings:airConditioner",
                commands=[
                    CommandSpec(id="main-switch-on", description="打开设备"),
                    CommandSpec(id="main-switch-off", description="关闭设备"),
                ],
            ),
            Device(
                id="sensor-1",
                name="温度传感器",
                room="卧室",
                type="smartthings:temperatureSensor",
                commands=[
                    CommandSpec(id="main-temperature-get", description="获取温度"),
                ],
            ),
        ]
        self.searcher = KeywordSearcher(self.devices)

    def test_name_exact_match(self):
        """测试名称精确匹配优先。"""
        ir = QueryIR(raw="打开老伙计", name_hint="老伙计")
        candidates = self.searcher.search(ir)

        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0].entity_id, "lamp-1")
        self.assertIn("name_exact", candidates[0].reasons)

    def test_name_substring_match(self):
        """测试名称子串匹配。"""
        ir = QueryIR(raw="打开台灯", name_hint="台灯")
        candidates = self.searcher.search(ir)

        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0].entity_id, "lamp-2")

    def test_room_match(self):
        """测试房间匹配。"""
        ir = QueryIR(
            raw="打开客厅的灯",
            scope_include={"客厅"},
            type_hint="light",
        )
        candidates = self.searcher.search(ir)

        # 客厅设备应该有 room_exact
        room_devices = [c for c in candidates if "room_exact" in c.reasons]
        self.assertGreater(len(room_devices), 0)

    def test_room_plus_type_match(self):
        """测试房间 + 类型组合匹配。"""
        ir = QueryIR(
            raw="打开卧室的灯",
            scope_include={"卧室"},
            type_hint="light",
        )
        candidates = self.searcher.search(ir)

        # 卧室灯应该排在最前面
        self.assertEqual(candidates[0].entity_id, "lamp-2")
        self.assertIn("room_exact", candidates[0].reasons)
        self.assertIn("type_hit", candidates[0].reasons)

    def test_action_match(self):
        """测试动作匹配。"""
        ir = QueryIR(
            raw="打开老伙计",
            name_hint="老伙计",
            action=ActionIntent(kind="open"),
        )
        candidates = self.searcher.search(ir)

        self.assertEqual(candidates[0].entity_id, "lamp-1")
        self.assertIn("action_match", candidates[0].reasons)

    def test_entity_mentions(self):
        """测试 entity_mentions 匹配。"""
        ir = QueryIR(raw="打开大白", entity_mentions=["大白"])
        candidates = self.searcher.search(ir)

        self.assertGreater(len(candidates), 0)
        ac_candidate = next(
            (c for c in candidates if c.entity_id == "ac-1"), None
        )
        self.assertIsNotNone(ac_candidate)

    def test_no_match(self):
        """测试无匹配情况。"""
        ir = QueryIR(raw="打开冰箱", name_hint="冰箱")
        candidates = self.searcher.search(ir)

        # 没有精确匹配的设备
        exact_match = [c for c in candidates if "name_exact" in c.reasons]
        self.assertEqual(len(exact_match), 0)

    def test_top_k_limit(self):
        """测试 top_k 限制。"""
        ir = QueryIR(raw="设备", action=ActionIntent(kind="open"))
        candidates = self.searcher.search(ir, top_k=2)

        self.assertLessEqual(len(candidates), 2)

    def test_score_ordering(self):
        """测试分数排序。"""
        ir = QueryIR(
            raw="打开老伙计",
            name_hint="老伙计",
            action=ActionIntent(kind="open"),
        )
        candidates = self.searcher.search(ir)

        # 确保按分数降序排列
        for i in range(len(candidates) - 1):
            self.assertGreaterEqual(
                candidates[i].keyword_score, candidates[i + 1].keyword_score
            )


if __name__ == "__main__":
    unittest.main()
