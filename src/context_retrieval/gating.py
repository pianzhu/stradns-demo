"""候选筛选与排序。

对融合评分后的候选进行排序，返回 top-k 结果及可选提示。
"""

from dataclasses import dataclass

from context_retrieval.models import Candidate

DEFAULT_TOP_K = 5
DEFAULT_CLOSE_THRESHOLD = 0.1


@dataclass
class SelectionResult:
    """筛选结果。"""

    candidates: list[Candidate]
    hint: str | None = None


def select_top(
    candidates: list[Candidate],
    top_k: int = DEFAULT_TOP_K,
    close_threshold: float = DEFAULT_CLOSE_THRESHOLD,
) -> SelectionResult:
    """选择得分最高的 top-k 候选。

    Args:
        candidates: 候选列表
        top_k: 返回数量上限，默认 5
        close_threshold: 判定分数接近的阈值，默认 0.1

    Returns:
        SelectionResult 包含候选列表和可选提示
    """
    if not candidates:
        return SelectionResult(candidates=[])

    sorted_candidates = sorted(candidates, key=lambda c: c.total_score, reverse=True)
    top_candidates = sorted_candidates[:top_k]

    # 判断是否存在多个分数接近的候选
    hint = None
    if len(top_candidates) >= 2:
        score_diff = top_candidates[0].total_score - top_candidates[1].total_score
        if score_diff < close_threshold:
            hint = "multiple_close_matches"

    return SelectionResult(candidates=top_candidates, hint=hint)
