"""复杂语义求值测试。"""

import unittest
from context_retrieval.logic import apply_scope_filters
from context_retrieval.models import Device, QueryIR


class TestApplyScopeFilters(unittest.TestCase):
    """测试 scope 过滤。"""

    def setUp(self):
        """设置测试设备。"""
        self.living_room_lamp = Device(
            id="lamp-1", name="客厅灯", room="客厅", type="light"
        )
        self.bedroom_lamp = Device(
            id="lamp-2", name="卧室灯", room="卧室", type="light"
        )
        self.kitchen_lamp = Device(
            id="lamp-3", name="厨房灯", room="厨房", type="light"
        )
        self.all_devices = [self.living_room_lamp, self.bedroom_lamp, self.kitchen_lamp]

    def test_exclude_single_room(self):
        """排除单个房间。"""
        ir = QueryIR(
            raw="打开除卧室以外的灯",
            scope_exclude={"卧室"},
            quantifier="except",
        )
        result = apply_scope_filters(self.all_devices, ir)
        result_ids = {d.id for d in result}
        self.assertIn("lamp-1", result_ids)
        self.assertIn("lamp-3", result_ids)
        self.assertNotIn("lamp-2", result_ids)

    def test_include_single_room(self):
        """仅包含指定房间。"""
        ir = QueryIR(
            raw="打开客厅的灯",
            scope_include={"客厅"},
        )
        result = apply_scope_filters(self.all_devices, ir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "lamp-1")

    def test_all_quantifier_no_scope(self):
        """量词"所有"无 scope 返回全部。"""
        ir = QueryIR(
            raw="关闭所有灯",
            quantifier="all",
        )
        result = apply_scope_filters(self.all_devices, ir)
        self.assertEqual(len(result), 3)

    def test_exclude_multiple_rooms(self):
        """排除多个房间。"""
        ir = QueryIR(
            raw="打开除卧室和厨房以外的灯",
            scope_exclude={"卧室", "厨房"},
            quantifier="except",
        )
        result = apply_scope_filters(self.all_devices, ir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "lamp-1")

    def test_empty_scope_returns_all(self):
        """无 scope 限制返回全部。"""
        ir = QueryIR(raw="打开灯")
        result = apply_scope_filters(self.all_devices, ir)
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
