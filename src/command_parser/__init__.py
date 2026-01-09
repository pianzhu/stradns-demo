"""Command parser package."""

from command_parser.parser import (
    CommandParser,
    CommandParserConfig,
    ParseResult,
    ParsedCommand,
    ParserMetrics,
    ScopeSlot,
    TargetSlot,
    UNKNOWN_COMMAND,
    parse_command_output,
)
from command_parser.prompt import DEFAULT_SYSTEM_PROMPT, PROMPT_REGRESSION_CASES

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "PROMPT_REGRESSION_CASES",
    "CommandParser",
    "CommandParserConfig",
    "ParseResult",
    "ParsedCommand",
    "ParserMetrics",
    "ScopeSlot",
    "TargetSlot",
    "UNKNOWN_COMMAND",
    "parse_command_output",
]
