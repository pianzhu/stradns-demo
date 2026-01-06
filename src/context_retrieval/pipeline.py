"""Pipeline 组装。

整合各模块完成上下文检索流程。
"""

import logging

from context_retrieval.category_gating import filter_by_category, map_type_to_category
from context_retrieval.models import Device, RetrievalResult
from context_retrieval.ir_compiler import LLMClient, compile_ir
from context_retrieval.state import ConversationState
from context_retrieval.logic import apply_scope_filters
from context_retrieval.keyword_search import KeywordSearcher
from context_retrieval.scoring import apply_room_bonus, merge_and_score
from context_retrieval.gating import select_top
from context_retrieval.vector_search import VectorSearcher

DEFAULT_KEYWORD_WEIGHT = 1.0
DEFAULT_VECTOR_WEIGHT = 0.3
FALLBACK_KEYWORD_WEIGHT = 1.2
FALLBACK_VECTOR_WEIGHT = 0.2

logger = logging.getLogger(__name__)


def retrieve(
    text: str,
    devices: list[Device],
    llm: LLMClient,
    state: ConversationState,
    top_k: int = 5,
    vector_searcher: VectorSearcher | None = None,
) -> RetrievalResult:
    """执行上下文检索。

    Pipeline 流程：
    1. IR 编译（LLM）
    2. Scope 预过滤
    3. Keyword 召回
    4. Vector 召回（可选）
    5. 融合评分
    6. Top-K 筛选
    7. 更新会话状态

    Args:
        text: 用户输入文本
        devices: 设备列表
        llm: LLM 客户端
        state: 会话状态
        top_k: 返回数量上限
        vector_searcher: 可选向量检索器，若提供会参与融合

    Returns:
        RetrievalResult
    """
    # 1. IR 编译
    ir = compile_ir(text, llm)

    # 2. Scope 预过滤
    filtered_devices = apply_scope_filters(devices, ir)

    mapped_category = map_type_to_category(ir.type_hint)
    if mapped_category:
        gated_devices = filter_by_category(filtered_devices, mapped_category)
    else:
        gated_devices = filtered_devices

    w_keyword = DEFAULT_KEYWORD_WEIGHT
    w_vector = DEFAULT_VECTOR_WEIGHT
    if not mapped_category:
        w_keyword = FALLBACK_KEYWORD_WEIGHT
        w_vector = FALLBACK_VECTOR_WEIGHT

    # 3. Keyword 召回
    searcher = KeywordSearcher(gated_devices)
    keyword_candidates = searcher.search(ir)

    # 4. Vector 召回（可选）
    vector_candidates = []
    if vector_searcher:
        # 重新索引当前过滤后的设备，避免额外设备干扰
        vector_searcher.index(gated_devices)
        search_text = (ir.action or "").strip() or ir.raw
        vector_candidates = vector_searcher.search(search_text, top_k=top_k)

    # 5. 融合评分
    merged = merge_and_score(
        keyword_candidates,
        vector_candidates=vector_candidates,
        w_keyword=w_keyword,
        w_vector=w_vector,
    )
    merged = apply_room_bonus(
        merged,
        {d.id: d for d in filtered_devices},
        ir.scope_include,
    )

    # 6. Top-K 筛选
    selection = select_top(merged, top_k=top_k)

    # 7. 更新会话状态
    if selection.candidates:
        top_candidate = selection.candidates[0]
        # 找到对应设备并更新状态
        for device in devices:
            if device.id == top_candidate.entity_id:
                state.update_mentioned(device)
                break

    return RetrievalResult(
        candidates=selection.candidates,
        hint=selection.hint,
    )
