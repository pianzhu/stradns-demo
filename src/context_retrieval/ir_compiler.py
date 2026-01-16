"""LLM 语义编译器。

负责命令映射与 LLM 适配。
"""

import json
import os
import re
from typing import Any, Protocol

from command_parser import ParsedCommand
from context_retrieval.models import QueryIR


class LLMClient(Protocol):
    """LLM 客户端协议。"""

    def generate_with_prompt(self, text: str, system_prompt: str) -> str:
        """生成文本（带 system prompt）。"""
        ...

    def parse(self, text: str) -> dict[str, Any]:
        """解析文本，返回 JSON 格式的 QueryIR。"""
        ...

    def parse_with_prompt(self, text: str, system_prompt: str) -> dict[str, Any]:
        """解析文本（可覆盖 system prompt）。"""
        ...


class FakeLLM(LLMClient):
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
            preset = self._presets[text]
            if isinstance(preset, dict):
                return preset
        return {"confidence": 0.0}

    def parse_with_prompt(self, text: str, system_prompt: str) -> dict[str, Any]:
        """解析文本（忽略 system prompt，便于测试注入）。"""
        return self.parse(text)

    def generate_with_prompt(self, text: str, system_prompt: str) -> str:
        """返回预设的命令数组文本。"""
        if text in self._presets:
            preset = self._presets[text]
            if isinstance(preset, str):
                return preset
            if isinstance(preset, (list, dict)):
                return json.dumps(preset, ensure_ascii=False)
        return "[]"


class DashScopeLLM(LLMClient):
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
        self._system_prompt = system_prompt or ""

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
        return self.parse_with_prompt(text, self._system_prompt)

    def parse_with_prompt(self, text: str, system_prompt: str) -> dict[str, Any]:
        """调用 dashscope 解析 JSON（可覆盖 system prompt）。"""
        content = self.generate_with_prompt(text, system_prompt)
        data = self._safe_json_loads(content)
        return data

    def generate_with_prompt(self, text: str, system_prompt: str) -> str:
        """调用 dashscope 返回原始文本（可覆盖 system prompt）。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        response = self._generation.call(
            model=self.model,
            messages=messages,  # type: ignore
            result_format="message",  # 使用 message 格式以获取 choices 结构
        )

        return self._extract_content(response)

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
            parsed = json.loads(content)
            # 调试输出：查看实际返回的 JSON 结构
            if os.getenv("DEBUG_LLM_RESPONSE"):
                print(f"[DEBUG] LLM 返回: {json.dumps(parsed, ensure_ascii=False)}")
            return parsed
        except json.JSONDecodeError:
            pass

        # 提取首个 JSON 对象片段
        match = re.search(r"{.*}", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if os.getenv("DEBUG_LLM_RESPONSE"):
                    print(f"[DEBUG] LLM 返回（提取后）: {json.dumps(parsed, ensure_ascii=False)}")
                return parsed
            except json.JSONDecodeError:
                pass

        return FALLBACK_IR


FALLBACK_IR = {"confidence": 0.0}


def compile_ir(command: ParsedCommand, raw_text: str) -> QueryIR:
    """将命令映射为 QueryIR。

    Args:
        command: command_parser 输出的结构化命令
        raw_text: 原始用户输入

    Returns:
        QueryIR 结构化表示
    """
    action = command.action.strip()
    if not action or action == "UNKNOWN":
        action = None

    name_hint = command.target.name.strip()
    references: list[str] = []
    if name_hint == "@last":
        references.append("last-mentioned")
        name_hint = ""

    if not name_hint or name_hint == "*":
        name_hint = None

    scope_include = set(command.scope.include)
    if "*" in scope_include:
        scope_include = set()

    ir = QueryIR(
        raw=raw_text,
        name_hint=name_hint,
        action=action,
        scope_include=scope_include,
        scope_exclude=set(command.scope.exclude),
        quantifier=command.target.quantifier,
        type_hint=command.target.type_hint,
        references=references,
    )

    if command.target.number is not None:
        ir.meta["count"] = command.target.number

    return ir
