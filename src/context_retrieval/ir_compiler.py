"""LLM 语义编译器。

调用大模型将自然语言解析为 QueryIR（JSON）。
"""

import json
import os
import re
from typing import Any, Protocol

from context_retrieval.models import ActionIntent, QueryIR


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
        return {"confidence": 0.0}


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
        """从 dashscope 响应中提取文本内容。

        dashscope 响应结构：response.output.choices[0].message.content
        """
        # 检查 HTTP 状态码
        if response.status_code != 200:
            raise RuntimeError(
                f"dashscope 调用失败: code={response.code}, message={response.message}"
            )

        # 按官方文档解析：response.output.choices[0].message.content
        return response.output.choices[0].message.content

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
                "text": {"type": "string"},
                "confidence": {"type": "number"},
            },
        },
        "name_hint": {"type": "string"},
        "scope_include": {"type": "array", "items": {"type": "string"}},
        "scope_exclude": {"type": "array", "items": {"type": "string"}},
        "quantifier": {"type": "string", "enum": ["one", "all", "any", "except"]},
        "type_hint": {"type": "string"},
        "references": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
}

# TODO optimize prompt
DEFAULT_SYSTEM_PROMPT = """你是智能家居助手的语义解析器，请仅返回一个 JSON 对象。
字段要求（只输出有把握且非空的键，避免空数组/空字符串）：
- action.text: 简短动词/意图短语，用于语义相似度
- name_hint: 可选
- scope_include: 可选字符串数组
- scope_exclude: 可选字符串数组
- quantifier: one/all/any/except
- type_hint: 可选
- references: 可选字符串数组
- confidence: 数值，0-1
无法解析，请输出 {"confidence":0}。"""

FALLBACK_IR = {"confidence": 0.0}

def _parse_action(data: dict[str, Any] | None) -> ActionIntent:
    """解析动作意图。"""
    if not data:
        return ActionIntent(confidence=0.0)
    return ActionIntent(
        text=data.get("text"),
        confidence=data.get("confidence", 1.0),
    )


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
        name_hint=data.get("name_hint"),
        action=_parse_action(data.get("action")),
        scope_include=set(data.get("scope_include", [])),
        scope_exclude=set(data.get("scope_exclude", [])),
        quantifier=data.get("quantifier", "one"),
        type_hint=data.get("type_hint"),
        references=data.get("references", []),
        confidence=data.get("confidence", 1.0),
    )
