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
_DELIMITER_SANITIZE_RE = re.compile(r"[#-]+")
_WHITESPACE_RE = re.compile(r"\s+")
_ALLOWED_TYPE_SET = set(ALLOWED_CATEGORIES)


def _is_unknown_command(command: "ParsedCommand") -> bool:
    """判断解析结果是否为 UNKNOWN 兜底命令。"""
    if command.raw == UNKNOWN_COMMAND:
        return True
    action = command.action.strip()
    return action.upper() == "UNKNOWN"


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
        return len(self.commands) == 1 and _is_unknown_command(self.commands[0])


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

    def parse(self, raw_output: object) -> ParseResult:
        """将 LLM 输出解析为结构化命令。"""
        return parse_command_output(
            raw_output,
            config=self.config,
            logger_override=self._logger,
            metrics=self.metrics,
        )


def parse_command_output(
    raw_output: object,
    *,
    config: CommandParserConfig | None = None,
    logger_override: logging.Logger | None = None,
    metrics: ParserMetrics | None = None,
) -> ParseResult:
    """解析 LLM 输出为结构化命令。

    支持 JSON 数组文本或已解析的对象数组。
    """
    config = config or CommandParserConfig()
    metrics = metrics or ParserMetrics()
    active_logger = logger_override or logger

    errors: list[str] = []
    degraded = False
    commands_raw: list[object] | None = None
    raw_text = ""
    raw_text_for_log = repr(raw_output)

    if isinstance(raw_output, list):
        commands_raw = raw_output
        try:
            raw_text = json.dumps(raw_output, ensure_ascii=False)
            raw_text_for_log = raw_text
        except (TypeError, ValueError):
            raw_text = ""
    elif isinstance(raw_output, str):
        raw_text = raw_output
        raw_text_for_log = raw_output
        if not raw_text.strip():
            errors.append("output_empty")
        else:
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, list):
                    commands_raw = parsed
                else:
                    errors.append("json_not_array")
            except json.JSONDecodeError:
                errors.append("json_decode_error")
    else:
        errors.append("output_not_string")

    commands: list[ParsedCommand] = []
    if commands_raw is not None:
        if not commands_raw:
            errors.append("json_array_empty")
            degraded = True
        for entry in commands_raw:
            if not isinstance(entry, dict):
                errors.append("json_item_invalid")
                degraded = True
                continue
            parsed_command, command_errors = _parse_command_object(entry)
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

    has_unknown = any(_is_unknown_command(command) for command in commands)
    if has_unknown:
        degraded = True
        if "fallback_unknown" not in errors:
            errors.append("unknown_action")

    unknown = len(commands) == 1 and _is_unknown_command(commands[0])
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


def _parse_command_object(
    item: dict[str, object],
) -> tuple[ParsedCommand | None, list[str]]:
    """解析单个命令对象并返回解析结果与校验错误。"""
    errors: list[str] = []

    action = _coerce_text(item.get("a"))
    if not action:
        errors.append("object_action_missing")
        action = "UNKNOWN"
    action = _sanitize_text_segment(action)
    if not action:
        errors.append("object_action_empty")
        action = "UNKNOWN"

    scope, scope_errors = _parse_scope_value(item.get("s"))
    errors.extend(scope_errors)

    name = _coerce_text(item.get("n"))
    if not name:
        errors.append("object_name_missing")
        name = "*"
    name = _sanitize_text_segment(name)
    if not name:
        errors.append("object_name_empty")
        name = "*"

    type_raw = _coerce_text(item.get("t"))
    mapped_type = map_type_to_category(type_raw) if type_raw else None
    if mapped_type is None or mapped_type not in _ALLOWED_TYPE_SET:
        mapped_type = "Unknown"
        errors.append("object_type_invalid")

    quantifier_raw = _coerce_text(item.get("q")).lower()
    if not quantifier_raw:
        errors.append("object_quantifier_missing")
        quantifier_raw = "one"
    if quantifier_raw not in VALID_QUANTIFIERS:
        errors.append("object_quantifier_invalid")
        quantifier_raw = "one"

    number = _coerce_positive_int(item.get("c"))
    if number is None and _has_value(item.get("c")):
        errors.append("object_number_invalid")

    raw = _serialize_command_object(item)

    return ParsedCommand(
        action=action,
        scope=scope,
        target=TargetSlot(
            name=name,
            type_hint=mapped_type,
            quantifier=quantifier_raw,
            number=number,
        ),
        raw=raw,
    ), errors


def _sanitize_text_segment(value: str) -> str:
    """清理片段文本的分隔符与多余空白。"""
    cleaned = _DELIMITER_SANITIZE_RE.sub(" ", value)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def _sanitize_scope(scope_raw: str) -> str:
    """规整 scope 文本为紧凑的包含/排除表达。"""
    parts = [part.strip() for part in scope_raw.split(",") if part.strip()]
    if not parts:
        return "*"
    sanitized_parts = []
    for part in parts:
        prefix = "!" if part.startswith("!") else ""
        name = part[1:] if prefix else part
        name = _sanitize_text_segment(name)
        if not name:
            continue
        sanitized_parts.append(f"{prefix}{name}")
    if not sanitized_parts:
        return "*"
    return ",".join(sanitized_parts)


def _coerce_text(value: object) -> str:
    """将值安全转换为去空白字符串。"""
    return value.strip() if isinstance(value, str) else ""


def _coerce_positive_int(value: object) -> int | None:
    """从字符串或整数中提取正整数。"""
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            number = int(raw)
            return number if number > 0 else None
    return None


def _has_value(value: object) -> bool:
    """判断字段是否存在且非空。"""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _parse_scope_value(value: object) -> tuple[ScopeSlot, list[str]]:
    """解析 scope 字段为 ScopeSlot 并返回校验错误。"""
    errors: list[str] = []

    if not _has_value(value):
        errors.append("object_scope_missing")
        scope_raw = "*"
    elif isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        if not parts:
            errors.append("object_scope_empty")
            scope_raw = "*"
        else:
            scope_raw = ",".join(parts)
    elif isinstance(value, str):
        scope_raw = value.strip()
        if not scope_raw:
            errors.append("object_scope_empty")
            scope_raw = "*"
    else:
        errors.append("object_scope_invalid")
        scope_raw = "*"

    scope_raw = _sanitize_scope(scope_raw)
    scope, scope_errors = _parse_scope(scope_raw)
    if scope is None:
        errors.extend(scope_errors)
        return ScopeSlot(include=["*"], exclude=[]), errors
    errors.extend(scope_errors)
    return scope, errors


def _serialize_command_object(item: dict[str, object]) -> str:
    """序列化命令对象用于日志或调试。"""
    try:
        return json.dumps(item, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return repr(item)


def _parse_scope(scope_raw: str) -> tuple[ScopeSlot | None, list[str]]:
    """解析 scope 表达式为包含/排除列表。"""
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


def _build_unknown_command() -> ParsedCommand:
    """构造 UNKNOWN 兜底命令。"""
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
    """记录解析结果、错误与统计指标。"""
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
    """清理日志文本中的控制字符并截断长度。"""
    if not isinstance(value, str):
        value = repr(value)
    cleaned = _CONTROL_CHARS_RE.sub(" ", value)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned
