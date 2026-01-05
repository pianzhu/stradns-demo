"""核心数据模型定义。

包含设备、命令、查询IR、候选、澄清请求等数据结构。
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ValueOption:
    """命令参数的可选值。"""

    value: str
    description: str = ""


@dataclass
class ValueRange:
    """命令参数的取值范围。"""

    minimum: float
    maximum: float
    unit: str = ""


@dataclass
class CommandSpec:
    """设备命令规格。"""

    id: str
    description: str = ""
    type: str | None = None
    value_range: ValueRange | None = None
    value_list: list[ValueOption] | None = None


@dataclass
class Device:
    """智能家居设备。"""

    id: str
    name: str
    room: str
    type: str
    commands: list[CommandSpec] = field(default_factory=list)


@dataclass
class Group:
    """设备分组。"""

    id: str
    name: str
    device_ids: list[str] = field(default_factory=list)


@dataclass
class ActionIntent:
    """动作意图。"""

    text: str | None = None  # 原始/简短意图文本，用于语义相似度
    confidence: float = 1.0


@dataclass
class QueryIR:
    """查询中间表示（Intermediate Representation）。"""

    raw: str
    name_hint: str | None = None
    action: ActionIntent = field(default_factory=ActionIntent)
    scope_include: set[str] = field(default_factory=set)
    scope_exclude: set[str] = field(default_factory=set)
    quantifier: Literal["one", "all", "any", "except"] = "one"
    type_hint: str | None = None
    references: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class Candidate:
    """检索候选。"""

    entity_id: str
    entity_kind: Literal["device", "group"] = "device"
    keyword_score: float = 0.0
    vector_score: float = 0.0
    total_score: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """检索结果。"""

    candidates: list[Candidate] = field(default_factory=list)
    hint: str | None = None
