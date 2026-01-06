"""候选融合与统一评分模块。

合并 Keyword 和 Vector 检索的结果，计算综合分数。
"""

from dataclasses import replace

from context_retrieval.models import Candidate, Device

ROOM_MATCH_BONUS = 0.2


def merge_and_score(
    keyword_candidates: list[Candidate],
    vector_candidates: list[Candidate],
    w_keyword: float = 1.0,
    w_vector: float = 0.5,
) -> list[Candidate]:
    """合并 keyword 和 vector 检索结果并计算综合分数。

    使用并集合并策略：
    - 若设备同时出现在两个结果中，合并分数和 reasons
    - 若仅出现在一个结果中，使用该来源的分数

    Args:
        keyword_candidates: Keyword 检索候选
        vector_candidates: Vector 检索候选
        w_keyword: Keyword 分数权重
        w_vector: Vector 分数权重

    Returns:
        合并后的候选列表，按综合分数降序排列
    """
    # 构建映射
    keyword_map: dict[str, Candidate] = {c.entity_id: c for c in keyword_candidates}
    vector_map: dict[tuple[str, str | None], Candidate] = {
        (c.entity_id, c.capability_id): c for c in vector_candidates
    }

    merged: list[Candidate] = []
    seen_entities: set[str] = set()

    for (entity_id, capability_id), vec_cand in vector_map.items():
        kw_cand = keyword_map.get(entity_id)

        keyword_score = kw_cand.keyword_score if kw_cand else 0.0
        vector_score = vec_cand.vector_score
        total_score = keyword_score * w_keyword + vector_score * w_vector

        reasons: list[str] = []
        if kw_cand:
            reasons.extend(kw_cand.reasons)
        for r in vec_cand.reasons:
            if r not in reasons:
                reasons.append(r)

        merged.append(
            Candidate(
                entity_id=entity_id,
                entity_kind=vec_cand.entity_kind,
                capability_id=capability_id,
                keyword_score=keyword_score,
                vector_score=vector_score,
                total_score=total_score,
                reasons=reasons,
            )
        )
        seen_entities.add(entity_id)

    for entity_id, kw_cand in keyword_map.items():
        if entity_id in seen_entities:
            continue
        merged.append(
            Candidate(
                entity_id=entity_id,
                entity_kind=kw_cand.entity_kind,
                capability_id=None,
                keyword_score=kw_cand.keyword_score,
                vector_score=0.0,
                total_score=kw_cand.keyword_score * w_keyword,
                reasons=list(kw_cand.reasons),
            )
        )

    # 按综合分数降序排列
    merged.sort(key=lambda c: c.total_score, reverse=True)

    return merged


def apply_room_bonus(
    candidates: list[Candidate],
    devices: dict[str, Device],
    scope_include: set[str],
    bonus: float = ROOM_MATCH_BONUS,
) -> list[Candidate]:
    """Apply a room match bonus to candidates."""
    if not candidates or not scope_include:
        return candidates

    boosted: list[Candidate] = []
    for cand in candidates:
        device = devices.get(cand.entity_id)
        if device and device.room in scope_include:
            reasons = list(cand.reasons)
            if "room_bonus" not in reasons:
                reasons.append("room_bonus")
            boosted.append(
                Candidate(
                    entity_id=cand.entity_id,
                    entity_kind=cand.entity_kind,
                    capability_id=cand.capability_id,
                    keyword_score=cand.keyword_score,
                    vector_score=cand.vector_score,
                    total_score=cand.total_score + bonus,
                    reasons=reasons,
                )
            )
        else:
            boosted.append(cand)
    return boosted


def normalize_scores(candidates: list[Candidate]) -> list[Candidate]:
    """归一化候选分数到 [0, 1] 范围。

    使用 min-max 归一化。

    Args:
        candidates: 候选列表

    Returns:
        分数归一化后的候选列表
    """
    if not candidates:
        return []

    max_score = max(c.total_score for c in candidates)
    min_score = min(c.total_score for c in candidates)

    score_range = max_score - min_score
    if score_range == 0:
        # 所有分数相同，归一化为 1.0
        return [replace(c, total_score=1.0) for c in candidates]

    return [
        replace(c, total_score=(c.total_score - min_score) / score_range)
        for c in candidates
    ]


def filter_by_threshold(
    candidates: list[Candidate], threshold: float = 0.3
) -> list[Candidate]:
    """按分数阈值过滤候选。

    Args:
        candidates: 候选列表
        threshold: 最低分数阈值

    Returns:
        过滤后的候选列表
    """
    return [c for c in candidates if c.total_score >= threshold]
