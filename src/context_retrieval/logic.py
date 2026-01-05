"""复杂语义求值。

处理 scope 过滤（包含/排除）。条件依赖扩展待后续优化。
"""

from context_retrieval.models import Device, QueryIR


def apply_scope_filters(devices: list[Device], ir: QueryIR) -> list[Device]:
    """根据 IR 的 scope 过滤设备。

    Args:
        devices: 设备列表
        ir: 查询 IR

    Returns:
        过滤后的设备列表
    """
    result = devices

    # 排除指定房间
    if ir.scope_exclude:
        result = [d for d in result if d.room not in ir.scope_exclude]

    # 仅包含指定房间
    if ir.scope_include:
        result = [d for d in result if d.room in ir.scope_include]

    return result
