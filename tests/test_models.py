"""测试核心数据模型。"""

import unittest

from context_retrieval.models import (
    ActionIntent,
    Candidate,
    CommandSpec,
    Condition,
    Device,
    Group,
    QueryIR,
    RetrievalResult,
    ValueOption,
    ValueRange,
)


class TestValueModels(unittest.TestCase):
    """测试值相关模型。"""

    def test_value_option(self):
        """测试 ValueOption 创建。"""
        opt = ValueOption(value="on", description="开启")
        self.assertEqual(opt.value, "on")
        self.assertEqual(opt.description, "开启")

    def test_value_range(self):
        """测试 ValueRange 创建。"""
        range_ = ValueRange(minimum=0, maximum=100, unit="%")
        self.assertEqual(range_.minimum, 0)
        self.assertEqual(range_.maximum, 100)
        self.assertEqual(range_.unit, "%")


class TestCommandSpec(unittest.TestCase):
    """测试命令规格模型。"""

    def test_basic_command(self):
        """测试基本命令创建。"""
        cmd = CommandSpec(id="main-switch-on", description="打开设备")
        self.assertEqual(cmd.id, "main-switch-on")
        self.assertEqual(cmd.description, "打开设备")
        self.assertIsNone(cmd.type)

    def test_command_with_range(self):
        """测试带范围的命令。"""
        cmd = CommandSpec(
            id="main-switchLevel-setLevel",
            description="调亮度",
            type="integer",
            value_range=ValueRange(minimum=0, maximum=100, unit="%"),
        )
        self.assertEqual(cmd.type, "integer")
        self.assertIsNotNone(cmd.value_range)
        self.assertEqual(cmd.value_range.maximum, 100)

    def test_command_with_value_list(self):
        """测试带值列表的命令。"""
        cmd = CommandSpec(
            id="main-mode-setMode",
            description="设置模式",
            type="string",
            value_list=[
                ValueOption(value="auto", description="自动"),
                ValueOption(value="cool", description="制冷"),
            ],
        )
        self.assertEqual(len(cmd.value_list), 2)


class TestDevice(unittest.TestCase):
    """测试设备模型。"""

    def test_device_creation(self):
        """测试设备创建。"""
        device = Device(
            id="lamp-1",
            name="老伙计",
            room="客厅",
            type="smartthings:switch",
            commands=[
                CommandSpec(id="main-switch-on", description="打开设备"),
                CommandSpec(id="main-switch-off", description="关闭设备"),
            ],
        )
        self.assertEqual(device.id, "lamp-1")
        self.assertEqual(device.name, "老伙计")
        self.assertEqual(device.room, "客厅")
        self.assertEqual(len(device.commands), 2)

    def test_device_default_commands(self):
        """测试设备默认命令列表为空。"""
        device = Device(id="d1", name="test", room="room", type="type")
        self.assertEqual(device.commands, [])


class TestGroup(unittest.TestCase):
    """测试分组模型。"""

    def test_group_creation(self):
        """测试分组创建。"""
        group = Group(id="g1", name="客厅灯", device_ids=["lamp-1", "lamp-2"])
        self.assertEqual(group.id, "g1")
        self.assertEqual(len(group.device_ids), 2)


class TestCondition(unittest.TestCase):
    """测试条件模型。"""

    def test_temperature_condition(self):
        """测试温度条件。"""
        cond = Condition(
            kind="temperature", operator="gt", threshold=26, unit="℃", room="卧室"
        )
        self.assertEqual(cond.kind, "temperature")
        self.assertEqual(cond.operator, "gt")
        self.assertEqual(cond.threshold, 26)


class TestActionIntent(unittest.TestCase):
    """测试动作意图模型。"""

    def test_open_action(self):
        """测试打开动作。"""
        action = ActionIntent(kind="open", confidence=0.95)
        self.assertEqual(action.kind, "open")
        self.assertEqual(action.confidence, 0.95)

    def test_set_action_with_value(self):
        """测试设置动作。"""
        action = ActionIntent(kind="set", target_value="50")
        self.assertEqual(action.target_value, "50")


class TestQueryIR(unittest.TestCase):
    """测试查询IR模型。"""

    def test_simple_query(self):
        """测试简单查询IR。"""
        ir = QueryIR(
            raw="打开老伙计",
            name_hint="老伙计",
            action=ActionIntent(kind="open"),
        )
        self.assertEqual(ir.raw, "打开老伙计")
        self.assertEqual(ir.name_hint, "老伙计")
        self.assertEqual(ir.action.kind, "open")

    def test_query_with_scope(self):
        """测试带范围的查询IR。"""
        ir = QueryIR(
            raw="关闭所有卧室的灯",
            action=ActionIntent(kind="close"),
            scope_include={"卧室"},
            quantifier="all",
            type_hint="light",
        )
        self.assertIn("卧室", ir.scope_include)
        self.assertEqual(ir.quantifier, "all")

    def test_query_with_exclusion(self):
        """测试带排除的查询IR。"""
        ir = QueryIR(
            raw="打开除卧室以外的灯",
            action=ActionIntent(kind="open"),
            scope_exclude={"卧室"},
            quantifier="except",
        )
        self.assertIn("卧室", ir.scope_exclude)
        self.assertEqual(ir.quantifier, "except")

    def test_query_with_reference(self):
        """测试带指代的查询IR。"""
        ir = QueryIR(raw="打开那个", references=["last-mentioned"])
        self.assertIn("last-mentioned", ir.references)

    def test_query_with_condition(self):
        """测试带条件的查询IR。"""
        ir = QueryIR(
            raw="如果室温超过26度就打开空调",
            conditions=[
                Condition(kind="temperature", operator="gt", threshold=26)
            ],
        )
        self.assertEqual(len(ir.conditions), 1)

    def test_default_values(self):
        """测试默认值。"""
        ir = QueryIR(raw="test")
        self.assertEqual(ir.entity_mentions, [])
        self.assertEqual(ir.scope_include, set())
        self.assertEqual(ir.quantifier, "one")
        self.assertEqual(ir.confidence, 1.0)


class TestCandidate(unittest.TestCase):
    """测试候选模型。"""

    def test_candidate_creation(self):
        """测试候选创建。"""
        candidate = Candidate(
            entity_id="lamp-1",
            entity_kind="device",
            keyword_score=0.8,
            vector_score=0.3,
            total_score=0.89,
            reasons=["name_hit", "room_hit"],
        )
        self.assertEqual(candidate.entity_id, "lamp-1")
        self.assertEqual(candidate.total_score, 0.89)
        self.assertIn("name_hit", candidate.reasons)


class TestRetrievalResult(unittest.TestCase):
    """测试检索结果模型。"""

    def test_result_with_candidates(self):
        """测试有候选结果。"""
        result = RetrievalResult(
            candidates=[Candidate(entity_id="lamp-1", total_score=0.9)],
        )
        self.assertIsNone(result.hint)
        self.assertEqual(len(result.candidates), 1)

    def test_result_with_hint(self):
        """测试带提示的结果。"""
        result = RetrievalResult(
            candidates=[
                Candidate(entity_id="lamp-1", total_score=0.8),
                Candidate(entity_id="lamp-2", total_score=0.78),
            ],
            hint="multiple_close_matches",
        )
        self.assertEqual(result.hint, "multiple_close_matches")


if __name__ == "__main__":
    unittest.main()
