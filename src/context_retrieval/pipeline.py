"""Pipeline 组装。

整合各模块完成上下文检索流程。
"""

from context_retrieval.models import Device, RetrievalResult
from context_retrieval.ir_compiler import LLMClient, compile_ir
from context_retrieval.state import ConversationState
from context_retrieval.logic import apply_scope_filters
from context_retrieval.keyword_search import KeywordSearcher
from context_retrieval.scoring import merge_and_score
from context_retrieval.gating import select_top
from context_retrieval.vector_search import VectorSearcher


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

    # 3. Keyword 召回
    searcher = KeywordSearcher(filtered_devices)
    keyword_candidates = searcher.search(ir)

    # 4. Vector 召回（可选）
    vector_candidates = []
    if vector_searcher:
        # 重新索引当前过滤后的设备，避免额外设备干扰
        vector_searcher.index(filtered_devices)
        vector_candidates = vector_searcher.search(ir.raw, top_k=top_k)

    # 5. 融合评分
    merged = merge_and_score(
        keyword_candidates,
        vector_candidates=vector_candidates,
        w_keyword=1.0,
        w_vector=0.3,
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
