"""Tests for command parser."""

import unittest

from command_parser import (
    CommandParser,
    CommandParserConfig,
    UNKNOWN_COMMAND,
)
from command_parser.prompt import PROMPT_REGRESSION_CASES


class TestCommandParser(unittest.TestCase):
    """Unit tests for command parser."""

    def test_parse_valid_single_command(self):
        parser = CommandParser()
        result = parser.parse('["打开-卧室-顶灯#Light#one"]')

        self.assertFalse(result.degraded)
        self.assertEqual(len(result.commands), 1)
        cmd = result.commands[0]
        self.assertEqual(cmd.action, "打开")
        self.assertEqual(cmd.scope.include, ["卧室"])
        self.assertEqual(cmd.scope.exclude, [])
        self.assertEqual(cmd.target.name, "顶灯")
        self.assertEqual(cmd.target.type_hint, "Light")
        self.assertEqual(cmd.target.quantifier, "one")
        self.assertIsNone(cmd.target.number)

    def test_parse_multi_command(self):
        parser = CommandParser()
        result = parser.parse(
            '["打开-卧室-顶灯#Light#one","关闭-客厅-*#Light#all"]'
        )

        self.assertEqual([cmd.action for cmd in result.commands], ["打开", "关闭"])

    def test_reject_non_array_json(self):
        parser = CommandParser()
        result = parser.parse('{"action":"打开"}')

        self.assertTrue(result.degraded)
        self.assertEqual(result.commands[0].raw, UNKNOWN_COMMAND)

    def test_drop_invalid_commands_keep_valid(self):
        parser = CommandParser()
        result = parser.parse(
            '["打开-卧室-顶灯#Light#one","无效指令"]'
        )

        self.assertTrue(result.degraded)
        self.assertEqual(len(result.commands), 1)
        self.assertEqual(result.commands[0].action, "打开")

    def test_fallback_when_all_invalid(self):
        parser = CommandParser()
        result = parser.parse('["无效指令"]')

        self.assertTrue(result.degraded)
        self.assertEqual(result.commands[0].raw, UNKNOWN_COMMAND)

    def test_scope_exclude_only(self):
        parser = CommandParser()
        result = parser.parse('["打开-!卧室-*#Light#except"]')

        self.assertEqual(result.commands[0].scope.include, ["*"])
        self.assertEqual(result.commands[0].scope.exclude, ["卧室"])

    def test_target_normalization(self):
        parser = CommandParser()
        result = parser.parse('["打开-客厅-顶灯#BadType#maybe#x"]')

        self.assertTrue(result.degraded)
        cmd = result.commands[0]
        self.assertEqual(cmd.target.type_hint, "Unknown")
        self.assertEqual(cmd.target.quantifier, "one")
        self.assertIsNone(cmd.target.number)

    def test_legacy_input(self):
        parser = CommandParser(CommandParserConfig(allow_legacy_input=True))
        result = parser.parse("打开-卧室-顶灯#Light#one")

        self.assertTrue(result.degraded)
        self.assertEqual(result.commands[0].action, "打开")

    def test_only_take_first(self):
        parser = CommandParser(CommandParserConfig(only_take_first=True))
        result = parser.parse(
            '["打开-卧室-顶灯#Light#one","关闭-客厅-*#Light#all"]'
        )

        self.assertTrue(result.degraded)
        self.assertEqual(len(result.commands), 1)
        self.assertEqual(result.commands[0].action, "打开")


class TestPromptRegressionCases(unittest.TestCase):
    """Ensure prompt regression cases cover required tags."""

    def test_cases_cover_required_tags(self):
        required = {
            "single",
            "multi_action",
            "multi_target",
            "except",
            "any_n",
            "reference_last",
            "unknown",
        }
        tags: set[str] = set()
        for case in PROMPT_REGRESSION_CASES:
            tags.update(case.get("tags", []))

        self.assertTrue(required.issubset(tags))

    def test_cases_are_list_of_strings(self):
        for case in PROMPT_REGRESSION_CASES:
            expected = case["expected"]
            self.assertIsInstance(expected, list)
            self.assertTrue(all(isinstance(item, str) for item in expected))


if __name__ == "__main__":
    unittest.main()
