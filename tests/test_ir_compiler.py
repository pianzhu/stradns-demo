"""语义编译 IR 测试（基于 LLM）。"""

import unittest
from context_retrieval.ir_compiler import compile_ir, FakeLLM
from context_retrieval.models import QueryIR


class TestCompileIRWithFakeLLM(unittest.TestCase):
    """测试 compile_ir 函数（使用 FakeLLM）。"""

    def setUp(self):
        """设置 FakeLLM 预设响应。"""
        self.llm = FakeLLM({
            "打开老伙计": {
                "action": {"kind": "open"},
                "name_hint": "老伙计",
            },
            "关闭客厅灯": {
                "action": {"kind": "close"},
                "name_hint": "客厅灯",
            },
            "把亮度设置为50": {
                "action": {"kind": "set", "target_value": "50"},
            },
            "客厅温度是多少": {
                "action": {"kind": "query"},
            },
            "关闭所有灯": {
                "action": {"kind": "close"},
                "quantifier": "all",
                "type_hint": "light",
            },
            "打开除卧室以外的灯": {
                "action": {"kind": "open"},
                "quantifier": "except",
                "scope_exclude": ["卧室"],
            },
            "打开它": {
                "action": {"kind": "open"},
                "references": ["last-mentioned"],
            },
            "打开客厅的灯": {
                "action": {"kind": "open"},
                "scope_include": ["客厅"],
            },
            "如果室温超过26度就打开空调": {
                "action": {"kind": "open"},
                "name_hint": "空调",
                "conditions": [{"kind": "temperature", "operator": "gt", "threshold": 26}],
            },
        })

    def test_simple_open_action(self):
        """测试简单打开动作。"""
        ir = compile_ir("打开老伙计", llm=self.llm)
        self.assertEqual(ir.raw, "打开老伙计")
        self.assertEqual(ir.action.kind, "open")
        self.assertEqual(ir.name_hint, "老伙计")

    def test_simple_close_action(self):
        """测试简单关闭动作。"""
        ir = compile_ir("关闭客厅灯", llm=self.llm)
        self.assertEqual(ir.action.kind, "close")
        self.assertEqual(ir.name_hint, "客厅灯")

    def test_set_action_with_value(self):
        """测试设置动作。"""
        ir = compile_ir("把亮度设置为50", llm=self.llm)
        self.assertEqual(ir.action.kind, "set")
        self.assertEqual(ir.action.target_value, "50")

    def test_query_action(self):
        """测试查询动作。"""
        ir = compile_ir("客厅温度是多少", llm=self.llm)
        self.assertEqual(ir.action.kind, "query")

    def test_quantifier_all(self):
        """测试量词：所有/全部。"""
        ir = compile_ir("关闭所有灯", llm=self.llm)
        self.assertEqual(ir.quantifier, "all")

    def test_exclusion(self):
        """测试排除：除X以外。"""
        ir = compile_ir("打开除卧室以外的灯", llm=self.llm)
        self.assertEqual(ir.quantifier, "except")
        self.assertIn("卧室", ir.scope_exclude)

    def test_reference_it(self):
        """测试指代：它/那个。"""
        ir = compile_ir("打开它", llm=self.llm)
        self.assertIn("last-mentioned", ir.references)

    def test_room_scope(self):
        """测试 room 范围识别。"""
        ir = compile_ir("打开客厅的灯", llm=self.llm)
        self.assertIn("客厅", ir.scope_include)

    def test_condition_temperature(self):
        """测试条件：室温超过。"""
        ir = compile_ir("如果室温超过26度就打开空调", llm=self.llm)
        self.assertEqual(len(ir.conditions), 1)
        cond = ir.conditions[0]
        self.assertEqual(cond.kind, "temperature")
        self.assertEqual(cond.operator, "gt")
        self.assertEqual(cond.threshold, 26)

    def test_returns_query_ir_type(self):
        """测试返回类型。"""
        ir = compile_ir("打开老伙计", llm=self.llm)
        self.assertIsInstance(ir, QueryIR)

    def test_unknown_query_fallback(self):
        """测试未知查询时 FakeLLM 返回默认值。"""
        ir = compile_ir("未知指令", llm=self.llm)
        self.assertEqual(ir.action.kind, "unknown")
        self.assertTrue(ir.needs_fallback)


class TestFakeLLM(unittest.TestCase):
    """测试 FakeLLM。"""

    def test_preset_response(self):
        """测试预设响应。"""
        llm = FakeLLM({"hello": {"action": {"kind": "open"}}})
        result = llm.parse("hello")
        self.assertEqual(result["action"]["kind"], "open")

    def test_unknown_returns_fallback(self):
        """测试未知输入返回 fallback。"""
        llm = FakeLLM({})
        result = llm.parse("unknown")
        self.assertEqual(result["action"]["kind"], "unknown")
        self.assertTrue(result["needs_fallback"])


if __name__ == "__main__":
    unittest.main()
