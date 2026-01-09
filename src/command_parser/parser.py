"""Strict command parser for LLM outputs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

from context_retrieval.category_gating import ALLOWED_CATEGORIES, map_type_to_category

logger = logging.getLogger(__name__)

UNKNOWN_COMMAND = "UNKNOWN-*-*#Unknown#one"
VALID_QUANTIFIERS = {"one", "all", "any", "except"}
_CONTROL_CHARS_RE = re.compile(r"[\r\n\t]")
_ALLOWED_TYPE_SET = set(ALLOWED_CATEGORIES)


@dataclass
class TargetSlot:
    name: str
    type_hint: str
    quantifier: str
    number: int | None = None


@dataclass
class ScopeSlot:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class ParsedCommand:
    action: str
    scope: ScopeSlot
    target: TargetSlot
    raw: str


@dataclass
class ParseResult:
    commands: list[ParsedCommand]
    raw_output: str
    errors: list[str]
    degraded: bool = False

    @property
    def is_unknown(self) -> bool:
        return len(self.commands) == 1 and self.commands[0].raw == UNKNOWN_COMMAND


@dataclass
class ParserMetrics:
    total_outputs: int = 0
    degraded_outputs: int = 0
    unknown_outputs: int = 0

    @property
    def unknown_ratio(self) -> float:
        if self.total_outputs == 0:
            return 0.0
        return self.unknown_outputs / self.total_outputs

    def record(self, *, degraded: bool, unknown: bool) -> None:
        self.total_outputs += 1
        if degraded:
            self.degraded_outputs += 1
        if unknown:
            self.unknown_outputs += 1


@dataclass
class CommandParserConfig:
    allow_legacy_input: bool = False
    only_take_first: bool = False
    max_log_chars: int = 400


class CommandParser:
    """Parse LLM outputs into structured commands."""

    def __init__(
        self,
        config: CommandParserConfig | None = None,
        logger_override: logging.Logger | None = None,
    ) -> None:
        self.config = config or CommandParserConfig()
        self.metrics = ParserMetrics()
        self._logger = logger_override or logger

    def parse(self, raw_output: str) -> ParseResult:
        return parse_command_output(
            raw_output,
            config=self.config,
            logger_override=self._logger,
            metrics=self.metrics,
        )


def parse_command_output(
    raw_output: str,
    *,
    config: CommandParserConfig | None = None,
    logger_override: logging.Logger | None = None,
    metrics: ParserMetrics | None = None,
) -> ParseResult:
    """Parse raw LLM output into validated commands."""
    config = config or CommandParserConfig()
    metrics = metrics or ParserMetrics()
    active_logger = logger_override or logger

    errors: list[str] = []
    degraded = False
    raw_text = raw_output if isinstance(raw_output, str) else ""
    raw_text_for_log = raw_output if isinstance(raw_output, str) else repr(raw_output)

    if not isinstance(raw_output, str):
        errors.append("output_not_string")
    if not raw_text.strip():
        errors.append("output_empty")

    commands_raw: list[str] | None = None
    json_failed = False
    if raw_text.strip():
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                commands_raw = parsed
            else:
                errors.append("json_not_array_of_strings")
        except json.JSONDecodeError:
            errors.append("json_decode_error")
            json_failed = True

    if commands_raw is None and config.allow_legacy_input and json_failed and raw_text.strip():
        commands_raw = [raw_text.strip()]
        errors.append("legacy_input_used")
        degraded = True

    commands: list[ParsedCommand] = []
    if commands_raw:
        for entry in commands_raw:
            parsed_command, command_errors = _parse_command_string(entry)
            if parsed_command is None:
                errors.extend(command_errors)
                degraded = True
                continue
            if command_errors:
                errors.extend(command_errors)
                degraded = True
            commands.append(parsed_command)

    if config.only_take_first and len(commands) > 1:
        commands = commands[:1]
        degraded = True
        errors.append("only_take_first")

    if not commands:
        degraded = True
        errors.append("fallback_unknown")
        commands = [_build_unknown_command()]

    unknown = len(commands) == 1 and commands[0].raw == UNKNOWN_COMMAND
    metrics.record(degraded=degraded, unknown=unknown)

    _log_parse_result(
        active_logger,
        raw_text_for_log,
        errors,
        degraded,
        metrics,
        config.max_log_chars,
        parsed_count=len(commands),
    )

    return ParseResult(
        commands=commands,
        raw_output=raw_text,
        errors=errors,
        degraded=degraded,
    )


def _parse_command_string(raw_command: str) -> tuple[ParsedCommand | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw_command, str):
        return None, ["command_not_string"]
    raw_command = raw_command.strip()
    if not raw_command:
        return None, ["command_empty"]

    parts = raw_command.split("-", 2)
    if len(parts) != 3:
        return None, ["command_not_three_segments"]

    action, scope_raw, target_raw = (part.strip() for part in parts)
    if not action or "-" in action:
        return None, ["action_invalid"]

    scope, scope_errors = _parse_scope(scope_raw)
    if scope is None:
        return None, scope_errors

    target, target_errors = _parse_target(target_raw)
    if target is None:
        return None, target_errors

    errors.extend(scope_errors)
    errors.extend(target_errors)

    return ParsedCommand(
        action=action,
        scope=scope,
        target=target,
        raw=raw_command,
    ), errors


def _parse_scope(scope_raw: str) -> tuple[ScopeSlot | None, list[str]]:
    errors: list[str] = []
    if not scope_raw or not scope_raw.strip():
        return None, ["scope_empty"]

    items = [item.strip() for item in scope_raw.split(",") if item.strip()]
    if not items:
        return None, ["scope_empty"]

    include: list[str] = []
    exclude: list[str] = []
    for item in items:
        if item.startswith("!"):
            name = item[1:].strip()
            if not name:
                return None, ["scope_exclude_empty"]
            exclude.append(name)
        else:
            include.append(item)

    if not include and exclude:
        include = ["*"]

    return ScopeSlot(include=include, exclude=exclude), errors


def _parse_target(target_raw: str) -> tuple[TargetSlot | None, list[str]]:
    errors: list[str] = []
    if not target_raw or not target_raw.strip():
        return None, ["target_empty"]

    parts = [part.strip() for part in target_raw.split("#")]
    if len(parts) not in (3, 4):
        return None, ["target_segment_count"]

    name = parts[0].strip()
    if not name:
        return None, ["target_name_empty"]

    type_raw = parts[1].strip()
    mapped_type = map_type_to_category(type_raw) if type_raw else None
    if mapped_type is None or mapped_type not in _ALLOWED_TYPE_SET:
        mapped_type = "Unknown"
        errors.append("target_type_invalid")

    quantifier_raw = parts[2].strip().lower()
    if quantifier_raw not in VALID_QUANTIFIERS:
        quantifier_raw = "one"
        errors.append("target_quantifier_invalid")

    number: int | None = None
    if len(parts) == 4:
        number_raw = parts[3].strip()
        if number_raw:
            try:
                number = int(number_raw)
                if number <= 0:
                    errors.append("target_number_invalid")
                    number = None
            except ValueError:
                errors.append("target_number_invalid")

    return TargetSlot(
        name=name,
        type_hint=mapped_type,
        quantifier=quantifier_raw,
        number=number,
    ), errors


def _build_unknown_command() -> ParsedCommand:
    parsed, _ = _parse_command_string(UNKNOWN_COMMAND)
    if parsed:
        return parsed
    return ParsedCommand(
        action="UNKNOWN",
        scope=ScopeSlot(include=["*"], exclude=[]),
        target=TargetSlot(name="*", type_hint="Unknown", quantifier="one"),
        raw=UNKNOWN_COMMAND,
    )


def _log_parse_result(
    active_logger: logging.Logger,
    raw_output: str,
    errors: Iterable[str],
    degraded: bool,
    metrics: ParserMetrics,
    max_log_chars: int,
    *,
    parsed_count: int,
) -> None:
    error_text = ",".join(errors) if errors else "-"
    active_logger.info(
        "command_parser parsed=%d degraded=%s errors=%s degraded_count=%d unknown_ratio=%.3f raw=%s",
        parsed_count,
        degraded,
        _sanitize_log_value(error_text, max_log_chars),
        metrics.degraded_outputs,
        metrics.unknown_ratio,
        _sanitize_log_value(raw_output, max_log_chars),
    )


def _sanitize_log_value(value: str, max_len: int) -> str:
    if not isinstance(value, str):
        value = repr(value)
    cleaned = _CONTROL_CHARS_RE.sub(" ", value)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned
