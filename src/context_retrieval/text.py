"""文本处理与模糊匹配工具。

使用 rapidfuzz 进行高效的中文模糊匹配。
"""

from rapidfuzz import fuzz


def fuzzy_match_score(text: str, query: str) -> float:
    """计算模糊匹配分数。

    使用 rapidfuzz 的 token_set_ratio 进行模糊匹配，
    适合中文文本匹配。

    Args:
        text: 目标文本
        query: 查询串

    Returns:
        匹配分数 [0, 1]
    """
    if not text or not query:
        return 0.0

    # 使用 token_set_ratio，对词序不敏感，适合中文
    score = fuzz.token_set_ratio(text, query) / 100.0
    return score


def partial_match_score(text: str, query: str) -> float:
    """计算部分匹配分数。

    使用 rapidfuzz 的 partial_ratio，
    当查询是目标的子串时给出高分。

    Args:
        text: 目标文本
        query: 查询串

    Returns:
        匹配分数 [0, 1]
    """
    if not text or not query:
        return 0.0

    score = fuzz.partial_ratio(text, query) / 100.0
    return score


def contains_substring(text: str, query: str) -> bool:
    """检查文本是否包含查询串。

    Args:
        text: 目标文本
        query: 查询串

    Returns:
        是否包含
    """
    if not text or not query:
        return False
    return query in text


def exact_match(text: str, query: str) -> bool:
    """检查是否精确匹配。

    Args:
        text: 目标文本
        query: 查询串

    Returns:
        是否精确匹配
    """
    return text == query
