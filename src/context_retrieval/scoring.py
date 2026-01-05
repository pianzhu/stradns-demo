"""候选融合与统一评分模块。

合并 Keyword 和 Vector 检索的结果，计算综合分数。
"""

from dataclasses import replace

from context_retrieval.models import Candidate


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
    vector_map: dict[str, Candidate] = {c.entity_id: c for c in vector_candidates}

    # 所有设备 ID
    all_ids = set(keyword_map.keys()) | set(vector_map.keys())

    merged: list[Candidate] = []

    for entity_id in all_ids:
        kw_cand = keyword_map.get(entity_id)
        vec_cand = vector_map.get(entity_id)

        # 计算分数
        keyword_score = kw_cand.keyword_score if kw_cand else 0.0
        vector_score = vec_cand.vector_score if vec_cand else 0.0

        total_score = keyword_score * w_keyword + vector_score * w_vector

        # 合并 reasons
        reasons: list[str] = []
        if kw_cand:
            reasons.extend(kw_cand.reasons)
        if vec_cand:
            for r in vec_cand.reasons:
                if r not in reasons:
                    reasons.append(r)

        # 确定 entity_kind（优先使用 keyword 的结果）
        entity_kind = (kw_cand or vec_cand).entity_kind

        merged.append(
            Candidate(
                entity_id=entity_id,
                entity_kind=entity_kind,
                keyword_score=keyword_score,
                vector_score=vector_score,
                total_score=total_score,
                reasons=reasons,
            )
        )

    # 按综合分数降序排列
    merged.sort(key=lambda c: c.total_score, reverse=True)

    return merged


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
