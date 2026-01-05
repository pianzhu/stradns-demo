"""Keyword 检索模块。

基于 QueryIR 和设备元数据（name/room/type）进行检索。
"""

from context_retrieval.models import Candidate, Device, QueryIR
from context_retrieval.text import (
    contains_substring,
    exact_match,
    fuzzy_match_score,
)


class KeywordSearcher:
    """关键词检索器。

    基于 QueryIR 解析结果和设备元数据进行匹配。
    主要负责精确匹配和基于 rapidfuzz 的模糊匹配。
    语义相似度匹配由 VectorSearcher 负责。
    """

    # 评分权重
    WEIGHT_NAME_EXACT = 1.0
    WEIGHT_NAME_SUBSTRING = 0.85
    WEIGHT_NAME_FUZZY = 0.7
    WEIGHT_ROOM_EXACT = 0.6
    WEIGHT_ROOM_FUZZY = 0.4
    WEIGHT_TYPE = 0.5
    WEIGHT_ACTION = 0.3

    def __init__(self, devices: list[Device]):
        """初始化检索器。

        Args:
            devices: 设备列表
        """
        self.devices = devices
        self._device_map = {d.id: d for d in devices}

    def search(self, ir: QueryIR, top_k: int = 10) -> list[Candidate]:
        """执行关键词检索。

        Args:
            ir: 查询 IR（由 LLM 解析得到）
            top_k: 返回的最大候选数

        Returns:
            候选列表，按分数降序排列
        """
        candidates: list[Candidate] = []

        for device in self.devices:
            score, reasons = self._score_device(device, ir)
            if score > 0:
                candidates.append(
                    Candidate(
                        entity_id=device.id,
                        entity_kind="device",
                        keyword_score=score,
                        total_score=score,
                        reasons=reasons,
                    )
                )

        candidates.sort(key=lambda c: c.keyword_score, reverse=True)
        return candidates[:top_k]

    def _score_device(self, device: Device, ir: QueryIR) -> tuple[float, list[str]]:
        """计算设备的匹配分数。"""
        scores: list[float] = []
        reasons: list[str] = []

        # 1. 名称匹配（基于 name_hint）
        name_score = self._score_name(device, ir)
        if name_score > 0:
            scores.append(name_score)
            if name_score >= self.WEIGHT_NAME_EXACT:
                reasons.append("name_exact")
            elif name_score >= self.WEIGHT_NAME_SUBSTRING:
                reasons.append("name_substring")
            else:
                reasons.append("name_fuzzy")

        # 2. 房间匹配（基于 scope_include）
        room_score = self._score_room(device, ir)
        if room_score > 0:
            scores.append(room_score)
            if room_score >= self.WEIGHT_ROOM_EXACT:
                reasons.append("room_exact")
            else:
                reasons.append("room_fuzzy")

        # 3. 类型匹配（基于 type_hint）
        type_score = self._score_type(device, ir)
        if type_score > 0:
            scores.append(type_score)
            reasons.append("type_hit")

        # 4. 动作-命令匹配
        action_score = self._score_action(device, ir)
        if action_score > 0:
            scores.append(action_score)
            reasons.append("action_match")

        # 综合分数：取最高分 + 其他分数的加权和
        if not scores:
            return 0.0, []

        scores.sort(reverse=True)
        total = scores[0]
        for s in scores[1:]:
            total += s * 0.3  # 其他信号作为增强
        total = min(total, 1.5)  # 上限

        return total, reasons

    def _score_name(self, device: Device, ir: QueryIR) -> float:
        """计算名称匹配分数。"""
        if not ir.name_hint:
            return 0.0

        queries = [ir.name_hint]

        best_score = 0.0
        for q in queries:
            if exact_match(device.name, q):
                return self.WEIGHT_NAME_EXACT
            if contains_substring(device.name, q) or contains_substring(q, device.name):
                best_score = max(best_score, self.WEIGHT_NAME_SUBSTRING)
            else:
                fuzzy = fuzzy_match_score(device.name, q)
                if fuzzy > 0.6:
                    best_score = max(best_score, fuzzy * self.WEIGHT_NAME_FUZZY)

        return best_score

    def _score_room(self, device: Device, ir: QueryIR) -> float:
        """计算房间匹配分数。"""
        if not ir.scope_include:
            return 0.0

        for room in ir.scope_include:
            if exact_match(device.room, room):
                return self.WEIGHT_ROOM_EXACT
            if contains_substring(device.room, room):
                return self.WEIGHT_ROOM_EXACT * 0.9
            fuzzy = fuzzy_match_score(device.room, room)
            if fuzzy > 0.7:
                return fuzzy * self.WEIGHT_ROOM_FUZZY

        return 0.0

    def _score_type(self, device: Device, ir: QueryIR) -> float:
        """计算类型匹配分数。"""
        if not ir.type_hint:
            return 0.0

        type_hint = ir.type_hint.lower()
        device_type = device.type.lower()

        # 直接包含检查
        if type_hint in device_type or device_type in type_hint:
            return self.WEIGHT_TYPE

        # 类型别名映射（用于常见类型）
        type_aliases = {
            "light": ["light", "lamp", "switch", "灯"],
            "灯": ["light", "lamp", "switch", "灯"],
            "ac": ["air", "airconditioner", "空调", "climate"],
            "空调": ["air", "airconditioner", "空调", "climate"],
            "curtain": ["curtain", "shade", "blind", "窗帘"],
            "窗帘": ["curtain", "shade", "blind", "窗帘"],
            "sensor": ["sensor", "传感器"],
            "传感器": ["sensor", "传感器"],
        }

        aliases = type_aliases.get(type_hint, [])
        for alias in aliases:
            if alias in device_type:
                return self.WEIGHT_TYPE

        return 0.0

    def _score_action(self, device: Device, ir: QueryIR) -> float:
        """计算动作-命令匹配分数。"""
        action_text = (ir.action.text or "").strip()
        if not action_text:
            return 0.0

        action_lower = action_text.lower()
        for cmd in device.commands:
            cmd_text = f"{cmd.id} {cmd.description}".lower()
            if action_lower in cmd_text:
                return self.WEIGHT_ACTION
            if fuzzy_match_score(cmd.description, action_text) > 0.7:
                return self.WEIGHT_ACTION

        return 0.0
