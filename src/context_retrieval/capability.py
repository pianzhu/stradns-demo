"""命令一致性校验。

使用向量相似度匹配动作意图与设备命令。
"""

from typing import Callable

from context_retrieval.models import Device, QueryIR

# 相似度计算函数类型
SimilarityFunc = Callable[[str, str], float]

# 动作意图到查询文本的映射
ACTION_QUERIES = {
    "open": "打开",
    "close": "关闭",
    "set": "设置",
    "query": "查询",
}

DEFAULT_THRESHOLD = 0.5


def _device_has_capability(
    device: Device,
    action_query: str,
    similarity_func: SimilarityFunc,
    threshold: float,
) -> bool:
    """检查设备是否有与动作匹配的命令。"""
    for cmd in device.commands:
        score = similarity_func(action_query, cmd.description)
        if score >= threshold:
            return True
    return False


def capability_filter(
    devices: list[Device],
    ir: QueryIR,
    similarity_func: SimilarityFunc | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Device]:
    """根据动作意图过滤设备。

    Args:
        devices: 设备列表
        ir: 查询 IR
        similarity_func: 相似度计算函数，None 时不过滤
        threshold: 相似度阈值

    Returns:
        过滤后的设备列表
    """
    # 无相似度函数时不过滤
    if similarity_func is None:
        return devices

    action_kind = ir.action.kind
    action_query = ACTION_QUERIES.get(action_kind)

    # 非操作类动作不过滤
    if not action_query:
        return devices

    return [
        d for d in devices
        if _device_has_capability(d, action_query, similarity_func, threshold)
    ]
