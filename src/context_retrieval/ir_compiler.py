"""LLM 语义编译器。

调用大模型将自然语言解析为 QueryIR（JSON）。
"""

import json
import os
import re
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


class DashScopeLLM:
    """基于 dashscope 的 LLM 解析器。

    通过 qwen 模型返回符合 QueryIR schema 的 JSON。
    """

    def __init__(
        self,
        model: str = "qwen-flash",
        api_key: str | None = None,
        generation_client: Any | None = None,
        system_prompt: str | None = None,
    ):
        """初始化。

        Args:
            model: dashscope 模型名称
            api_key: API Key，未提供时从环境变量 `DASHSCOPE_API_KEY` 读取
            generation_client: 可注入的 Generation 客户端，便于测试
            system_prompt: 可选自定义 system prompt
        """
        self.model = model
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        if generation_client is not None:
            self._generation = generation_client
            self._dashscope = None
            return

        try:
            import dashscope
            from dashscope import Generation
        except ImportError as exc:  # pragma: no cover - 依赖缺失时提示
            raise ImportError("需要安装 dashscope 才能使用 DashScopeLLM") from exc

        api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            dashscope.api_key = api_key

        self._generation = Generation
        self._dashscope = dashscope

    def parse(self, text: str) -> dict[str, Any]:
        """调用 dashscope 解析 QueryIR。"""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": text},
        ]

        response = self._generation.call(
            model=self.model,
            messages=messages, # type: ignore
        )

        content = self._extract_content(response)
        data = self._safe_json_loads(content)
        return data

    def _extract_content(self, response: Any) -> str:
        """从 dashscope 响应中提取文本内容。"""
        # 常见属性：output_text
        if hasattr(response, "output_text"):
            return getattr(response, "output_text") or ""

        output = getattr(response, "output", None)
        if isinstance(output, dict):
            if "text" in output:
                return output.get("text") or ""

            choices = output.get("choices")
            if choices:
                first = choices[0] or {}
                message = first.get("message", {})
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # 兼容 content 分片结构
                    parts = [
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    ]
                    return "".join(parts)

        # 兜底字符串化
        return str(response)

    def _safe_json_loads(self, content: str) -> dict[str, Any]:
        """解析 JSON，失败时返回 fallback。"""
        if not content:
            return FALLBACK_IR

        # 直接尝试解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 提取首个 JSON 对象片段
        match = re.search(r"{.*}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return FALLBACK_IR


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

# TODO optimize prompt
DEFAULT_SYSTEM_PROMPT = """你是智能家居助手的语义解析器，请仅返回一个 JSON 对象。
字段要求：
- action.kind: open/close/set/query/unknown
- action.target_value: 可选，字符串
- name_hint: 可选，字符串
- entity_mentions: 字符串数组
- scope_include: 字符串数组
- scope_exclude: 字符串数组
- quantifier: one/all/any/except
- type_hint: 可选，字符串
- conditions: 对象数组，字段包括 kind/operator/threshold/unit/room
- references: 字符串数组
- confidence: 数值
- needs_fallback: 布尔
如果无法解析，请返回 {"action":{"kind":"unknown"},"needs_fallback":true}。"""

FALLBACK_IR = {
    "action": {"kind": "unknown"},
    "needs_fallback": True,
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
