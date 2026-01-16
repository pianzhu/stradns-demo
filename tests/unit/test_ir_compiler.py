"""语义编译 IR 测试（基于命令映射）。"""

import unittest
from command_parser import ParsedCommand, ScopeSlot, TargetSlot
from context_retrieval.ir_compiler import compile_ir, FakeLLM
from context_retrieval.models import QueryIR


class TestCompileIRFromCommand(unittest.TestCase):
    """测试 compile_ir 命令映射。"""

    def test_simple_open_action(self):
        """测试简单打开动作映射。"""
        cmd = ParsedCommand(
            action="打开",
            scope=ScopeSlot(include=["客厅"], exclude=[]),
            target=TargetSlot(name="老伙计", type_hint="Light", quantifier="one"),
            raw='{"a":"打开"}',
        )
        ir = compile_ir(cmd, raw_text="打开老伙计")
        self.assertEqual(ir.raw, "打开老伙计")
        self.assertEqual(ir.action, "打开")
        self.assertEqual(ir.name_hint, "老伙计")

    def test_scope_exclusion(self):
        """测试排除映射。"""
        cmd = ParsedCommand(
            action="打开",
            scope=ScopeSlot(include=["*"], exclude=["卧室"]),
            target=TargetSlot(name="灯", type_hint="Light", quantifier="except"),
            raw="{}",
        )
        ir = compile_ir(cmd, raw_text="打开除卧室以外的灯")
        self.assertEqual(ir.quantifier, "except")
        self.assertEqual(ir.scope_include, set())
        self.assertIn("卧室", ir.scope_exclude)

    def test_reference_last(self):
        """测试 @last 指代映射。"""
        cmd = ParsedCommand(
            action="打开",
            scope=ScopeSlot(include=["*"], exclude=[]),
            target=TargetSlot(name="@last", type_hint="Light", quantifier="one"),
            raw="{}",
        )
        ir = compile_ir(cmd, raw_text="打开它")
        self.assertIsNone(ir.name_hint)
        self.assertIn("last-mentioned", ir.references)

    def test_name_wildcard(self):
        """测试 name 通配映射为空。"""
        cmd = ParsedCommand(
            action="打开",
            scope=ScopeSlot(include=["客厅"], exclude=[]),
            target=TargetSlot(name="*", type_hint="Light", quantifier="all"),
            raw="{}",
        )
        ir = compile_ir(cmd, raw_text="打开客厅的灯")
        self.assertIsNone(ir.name_hint)

    def test_quantifier_and_count(self):
        """测试量词与数量映射。"""
        cmd = ParsedCommand(
            action="打开",
            scope=ScopeSlot(include=["*"], exclude=[]),
            target=TargetSlot(
                name="灯",
                type_hint="Light",
                quantifier="any",
                number=3,
            ),
            raw="{}",
        )
        ir = compile_ir(cmd, raw_text="打开三盏灯")
        self.assertEqual(ir.quantifier, "any")
        self.assertEqual(ir.meta.get("count"), 3)

    def test_unknown_action(self):
        """测试 UNKNOWN action 降级为空。"""
        cmd = ParsedCommand(
            action="UNKNOWN",
            scope=ScopeSlot(include=["*"], exclude=[]),
            target=TargetSlot(name="*", type_hint="Unknown", quantifier="one"),
            raw="{}",
        )
        ir = compile_ir(cmd, raw_text="无法解析")
        self.assertIsNone(ir.action)

    def test_returns_query_ir_type(self):
        """测试返回类型。"""
        cmd = ParsedCommand(
            action="打开",
            scope=ScopeSlot(include=["*"], exclude=[]),
            target=TargetSlot(name="老伙计", type_hint="Light", quantifier="one"),
            raw="{}",
        )
        ir = compile_ir(cmd, raw_text="打开老伙计")
        self.assertIsInstance(ir, QueryIR)

class TestFakeLLM(unittest.TestCase):
    """测试 FakeLLM。"""

    def test_preset_response(self):
        """测试预设响应。"""
        llm = FakeLLM({"hello": {"action": "打开"}})
        result = llm.parse("hello")
        self.assertEqual(result["action"], "打开")

    def test_unknown_returns_fallback(self):
        """测试未知输入返回 fallback。"""
        llm = FakeLLM({})
        result = llm.parse("unknown")
        self.assertNotIn("action", result)
        self.assertEqual(result["confidence"], 0.0)

    def test_generate_with_prompt_serializes_output(self):
        """测试命令数组输出序列化。"""
        llm = FakeLLM({"hello": [{"a": "打开", "s": "*", "n": "灯", "t": "Light", "q": "all"}]})
        output = llm.generate_with_prompt("hello", "prompt")
        self.assertIn('"a": "打开"', output)


if __name__ == "__main__":
    unittest.main()
