"""命令一致性校验测试。"""

import unittest
from context_retrieval.capability import capability_filter, SimilarityFunc
from context_retrieval.models import Device, CommandSpec, QueryIR, ActionIntent


def mock_similarity(text1: str, text2: str) -> float:
    """模拟相似度计算：简单的关键词匹配。"""
    # 用于测试的简化实现
    if "打开" in text1 and "打开" in text2:
        return 0.9
    if "关闭" in text1 and "关闭" in text2:
        return 0.9
    if "open" in text1.lower() and "打开" in text2:
        return 0.85
    if "close" in text1.lower() and "关闭" in text2:
        return 0.85
    return 0.1


class TestCapabilityFilter(unittest.TestCase):
    """测试 capability_filter 函数。"""

    def setUp(self):
        """设置测试设备。"""
        self.lamp = Device(
            id="lamp-1",
            name="客厅灯",
            room="客厅",
            type="light",
            commands=[
                CommandSpec(id="on", description="打开设备"),
                CommandSpec(id="off", description="关闭设备"),
            ],
        )
        self.sensor = Device(
            id="sensor-1",
            name="温度传感器",
            room="客厅",
            type="sensor",
            commands=[
                CommandSpec(id="read", description="读取温度"),
            ],
        )
        self.curtain = Device(
            id="curtain-1",
            name="窗帘",
            room="客厅",
            type="curtain",
            commands=[
                CommandSpec(id="open", description="打开窗帘"),
                CommandSpec(id="close", description="关闭窗帘"),
            ],
        )
        self.all_devices = [self.lamp, self.sensor, self.curtain]

    def test_open_action_filters_sensor(self):
        """open 动作过滤无匹配命令的设备。"""
        ir = QueryIR(
            raw="打开设备",
            action=ActionIntent(text="打开", confidence=0.9),
        )
        result = capability_filter(
            self.all_devices, ir, similarity_func=mock_similarity, threshold=0.5
        )
        result_ids = {d.id for d in result}
        self.assertIn("lamp-1", result_ids)
        self.assertIn("curtain-1", result_ids)
        self.assertNotIn("sensor-1", result_ids)

    def test_close_action_filters_sensor(self):
        """close 动作过滤无匹配命令的设备。"""
        ir = QueryIR(
            raw="关闭设备",
            action=ActionIntent(text="关闭", confidence=0.9),
        )
        result = capability_filter(
            self.all_devices, ir, similarity_func=mock_similarity, threshold=0.5
        )
        result_ids = {d.id for d in result}
        self.assertIn("lamp-1", result_ids)
        self.assertIn("curtain-1", result_ids)
        self.assertNotIn("sensor-1", result_ids)

    def test_no_similarity_func_returns_all(self):
        """无相似度函数时返回所有设备。"""
        ir = QueryIR(
            raw="打开设备",
            action=ActionIntent(text="打开", confidence=0.9),
        )
        result = capability_filter(self.all_devices, ir, similarity_func=None)
        self.assertEqual(len(result), 3)

    def test_unknown_action_no_filter(self):
        """无动作文本时不过滤。"""
        ir = QueryIR(
            raw="测试",
            action=ActionIntent(text=None),
        )
        result = capability_filter(
            self.all_devices, ir, similarity_func=mock_similarity
        )
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
