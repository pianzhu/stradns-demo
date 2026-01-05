"""LLM 语义编译器。

调用大模型将自然语言解析为 QueryIR（JSON）。
"""

from typing import Any, Protocol

from context_retrieval.models import ActionIntent, Condition, QueryIR


class LLMClient(Protocol):
    """LLM 客户端协议。"""

    def parse(self, text: str) -> dict[str, Any]:
        """解析文本，返回 JSON 格式的 QueryIR。"""
        ...


class FakeLLM:
    """用于测试和离线 demo 的假 LLM。"""

    def __init__(self, preset_responses: dict[str, dict[str, Any]] | None = None):
        """初始化。

        Args:
            preset_responses: 预设响应映射，key 是输入文本，value 是解析结果
        """
        self._presets = preset_responses or {}

    def parse(self, text: str) -> dict[str, Any]:
        """解析文本，返回预设响应或 fallback。"""
        if text in self._presets:
            return self._presets[text]
        return {
            "action": {"kind": "unknown"},
            "needs_fallback": True,
        }


# JSON schema 供真实 LLM 使用（参考）
QUERY_IR_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["open", "close", "set", "query", "unknown"]},
                "target_value": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["kind"],
        },
        "name_hint": {"type": "string"},
        "entity_mentions": {"type": "array", "items": {"type": "string"}},
        "scope_include": {"type": "array", "items": {"type": "string"}},
        "scope_exclude": {"type": "array", "items": {"type": "string"}},
        "quantifier": {"type": "string", "enum": ["one", "all", "any", "except"]},
        "type_hint": {"type": "string"},
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "operator": {"type": "string"},
                    "threshold": {"type": "number"},
                    "unit": {"type": "string"},
                    "room": {"type": "string"},
                },
            },
        },
        "references": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "needs_fallback": {"type": "boolean"},
    },
}


def _parse_action(data: dict[str, Any] | None) -> ActionIntent:
    """解析动作意图。"""
    if not data:
        return ActionIntent(kind="unknown")
    return ActionIntent(
        kind=data.get("kind", "unknown"),
        target_value=data.get("target_value"),
        confidence=data.get("confidence", 1.0),
    )


def _parse_conditions(data: list[dict[str, Any]] | None) -> list[Condition]:
    """解析条件列表。"""
    if not data:
        return []
    conditions = []
    for item in data:
        conditions.append(
            Condition(
                kind=item.get("kind", "other"),
                operator=item.get("operator", "eq"),
                threshold=item.get("threshold", 0),
                unit=item.get("unit", ""),
                room=item.get("room"),
            )
        )
    return conditions


def compile_ir(text: str, llm: LLMClient) -> QueryIR:
    """将自然语言编译为 QueryIR。

    Args:
        text: 用户输入文本
        llm: LLM 客户端，实现 parse 方法

    Returns:
        QueryIR 结构化表示
    """
    data = llm.parse(text)

    return QueryIR(
        raw=text,
        entity_mentions=data.get("entity_mentions", []),
        name_hint=data.get("name_hint"),
        action=_parse_action(data.get("action")),
        scope_include=set(data.get("scope_include", [])),
        scope_exclude=set(data.get("scope_exclude", [])),
        quantifier=data.get("quantifier", "one"),
        type_hint=data.get("type_hint"),
        conditions=_parse_conditions(data.get("conditions")),
        references=data.get("references", []),
        confidence=data.get("confidence", 1.0),
        needs_fallback=data.get("needs_fallback", False),
    )
