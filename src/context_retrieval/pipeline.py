"""Pipeline 组装。

整合各模块完成上下文检索流程。
"""

import logging
import os
import re

from context_retrieval.bulk import (
    DEFAULT_BULK_BATCH_SIZE,
    DEFAULT_COVERAGE_THRESHOLD,
    DEFAULT_MAX_GROUPS,
    DEFAULT_MAX_TARGETS,
    build_capability_options,
    build_spec_lookup,
    group_by_command_compatibility,
    is_bulk_quantifier,
    is_low_confidence,
    select_targets,
    split_into_batches,
)
from context_retrieval.category_gating import filter_by_category, map_type_to_category
from context_retrieval.doc_enrichment import enrich_description
from context_retrieval.models import Candidate, Device, RetrievalResult
from context_retrieval.ir_compiler import LLMClient, compile_ir
from context_retrieval.state import ConversationState
from context_retrieval.logic import apply_scope_filters
from context_retrieval.keyword_search import KeywordSearcher
from context_retrieval.scoring import apply_room_bonus, merge_and_score
from context_retrieval.gating import select_top
from context_retrieval.text import fuzzy_match_score
from context_retrieval.vector_search import VectorSearcher

DEFAULT_KEYWORD_WEIGHT = 1.0
DEFAULT_VECTOR_WEIGHT = 0.3
FALLBACK_KEYWORD_WEIGHT = 1.2
FALLBACK_VECTOR_WEIGHT = 0.2

logger = logging.getLogger(__name__)

_LATIN_LETTERS_RE = re.compile(r"[A-Za-z]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_DIGIT_RE = re.compile(r"\d")
_CANCEL_TOKEN = "\u53d6\u6d88"
_BULK_ARBITRATION_ENV = "ENABLE_BULK_ARBITRATION_LLM"

_BULK_ARBITRATION_SYSTEM_PROMPT = """你是智能家居助手的批量命令选择器。

你将得到用户的原始请求和一组闭集候选 capability 选项。你的任务是在这些候选中选择最匹配的一项，或提出一个澄清问题。

只返回一个 JSON 对象，且必须且只能满足以下两种之一：
- {"choice_index": <0-based integer>}  # 选择某个候选
- {"question": "<string>"}            # 如果无法确定，提出 1 个澄清问题

约束：
- choice_index 必须是整数，且必须在 [0, N-1] 范围内。
- 禁止输出除 JSON 以外的任何文本。
"""


def _vector_search_text(ir) -> str:
    action_text = (ir.action or "").strip()
    if action_text and _LATIN_LETTERS_RE.search(action_text):
        logger.info(
            "action_invalid_fallback reason=latin_letters action=%s",
            action_text,
        )
        return ir.raw
    return action_text or ir.raw


def _should_force_capability_guess(query: str) -> bool:
    if not isinstance(query, str) or not query.strip():
        return False
    if not _CJK_RE.search(query):
        return False
    return bool(_DIGIT_RE.search(query) or "%" in query or _CANCEL_TOKEN in query)


def _device_profile_id(device: Device) -> str | None:
    profile_id = getattr(device, "profile_id", None) or getattr(device, "profileId", None)
    if isinstance(profile_id, str) and profile_id.strip():
        return profile_id.strip()
    return None


def _infer_name_hint(query: str, devices: list[Device]) -> str | None:
    if not isinstance(query, str) or not query.strip() or not devices:
        return None

    matches: set[str] = set()
    for device in devices:
        name = getattr(device, "name", None)
        if isinstance(name, str) and name and name in query:
            matches.add(name)

    if not matches:
        return None

    max_len = max(len(item) for item in matches)
    longest = [item for item in matches if len(item) == max_len]
    if len(longest) != 1:
        return None
    return longest[0]


def _infer_category_from_name_hint(
    name_hint: str | None,
    devices: list[Device],
) -> str | None:
    if not isinstance(name_hint, str) or not name_hint.strip() or not devices:
        return None

    categories: set[str] = set()
    for device in devices:
        if device.name != name_hint:
            continue
        mapped = map_type_to_category(device.category)
        if mapped and mapped != "Unknown":
            categories.add(mapped)

    if len(categories) != 1:
        return None
    return next(iter(categories))


def _guess_capability_id(
    *,
    query: str,
    device: Device,
    spec_lookup,
) -> str | None:
    profile_id = _device_profile_id(device)
    if not profile_id:
        return None

    profile_docs = spec_lookup.get(profile_id)
    if not profile_docs:
        return None

    best_id: str | None = None
    best_score = -1.0

    for cap_id, doc in profile_docs.items():
        if not isinstance(cap_id, str) or not cap_id:
            continue

        parts: list[str] = []
        enriched_desc = enrich_description(getattr(doc, "description", "") or "")
        if enriched_desc:
            parts.append(enriched_desc)

        for value_desc in getattr(doc, "value_descriptions", []) or []:
            if not isinstance(value_desc, str):
                continue
            cleaned = value_desc.strip()
            if cleaned:
                parts.append(cleaned)

        target_text = " ".join(parts)
        if not target_text:
            continue

        score = fuzzy_match_score(target_text, query)
        if getattr(doc, "value_range", None) is not None:
            unit = getattr(doc.value_range, "unit", "") or ""
            if isinstance(unit, str) and unit and unit in query:
                score += 0.05

        if score > best_score:
            best_score = score
            best_id = cap_id

    return best_id


def _fill_missing_capability_ids(
    candidates: list[Candidate],
    *,
    query: str,
    device_by_id: dict[str, Device],
    spec_lookup,
) -> list[Candidate]:
    if not candidates:
        return candidates

    filled: list[Candidate] = []
    for cand in candidates:
        if cand.entity_kind != "device" or cand.capability_id:
            filled.append(cand)
            continue

        device = device_by_id.get(cand.entity_id)
        if device is None:
            filled.append(cand)
            continue

        cap_id = _guess_capability_id(query=query, device=device, spec_lookup=spec_lookup)
        if not cap_id:
            filled.append(cand)
            continue

        filled.append(
            Candidate(
                entity_id=cand.entity_id,
                entity_kind=cand.entity_kind,
                capability_id=cap_id,
                keyword_score=cand.keyword_score,
                vector_score=cand.vector_score,
                total_score=cand.total_score,
                reasons=list(cand.reasons),
            )
        )

    return filled


def _dedupe_device_candidates(candidates: list[Candidate]) -> list[Candidate]:
    if not candidates:
        return candidates

    best: dict[str, Candidate] = {}
    for cand in candidates:
        if cand.entity_kind != "device":
            continue
        current = best.get(cand.entity_id)
        if current is None or cand.total_score > current.total_score:
            best[cand.entity_id] = cand

    return list(best.values())


def _apply_capability_guess(
    candidates: list[Candidate],
    *,
    query: str,
    device_by_id: dict[str, Device],
    spec_lookup,
) -> list[Candidate]:
    if not candidates:
        return candidates

    updated: list[Candidate] = []
    for cand in candidates:
        if cand.entity_kind != "device":
            updated.append(cand)
            continue

        device = device_by_id.get(cand.entity_id)
        if device is None:
            updated.append(cand)
            continue

        cap_id = _guess_capability_id(query=query, device=device, spec_lookup=spec_lookup)
        if not cap_id or cap_id == cand.capability_id:
            updated.append(cand)
            continue

        reasons = list(cand.reasons)
        if "capability_guess" not in reasons:
            reasons.append("capability_guess")

        updated.append(
            Candidate(
                entity_id=cand.entity_id,
                entity_kind=cand.entity_kind,
                capability_id=cap_id,
                keyword_score=cand.keyword_score,
                vector_score=cand.vector_score,
                total_score=cand.total_score,
                reasons=reasons,
            )
        )

    return updated


def _is_supported_candidate(
    candidate: Candidate,
    device_by_id: dict[str, Device],
    spec_lookup,
) -> bool:
    if candidate.entity_kind != "device":
        return False

    capability_id = candidate.capability_id
    if not isinstance(capability_id, str) or not capability_id:
        return False

    device = device_by_id.get(candidate.entity_id)
    if device is None:
        return False

    profile_id = _device_profile_id(device)
    if not profile_id:
        return False

    profile_docs = spec_lookup.get(profile_id)
    if not profile_docs:
        return False

    return capability_id in profile_docs


def _bulk_arbitrate_choice(
    llm: LLMClient,
    *,
    query: str,
    options,
) -> tuple[int | None, str | None]:
    lines = [
        f"用户请求: {query}",
        "",
        "候选选项（闭集选择）：",
    ]
    for idx, opt in enumerate(options):
        examples = ", ".join(opt.examples[:3]) if opt.examples else ""
        lines.append(
            f"{idx}. capability_id={opt.capability_id} "
            f"description={opt.description} "
            f"support={opt.support_count}/{opt.total_devices} "
            f"examples={examples}"
        )
    user_text = "\n".join(lines)

    parse_with_prompt = getattr(llm, "parse_with_prompt", None)
    if callable(parse_with_prompt):
        payload = parse_with_prompt(user_text, _BULK_ARBITRATION_SYSTEM_PROMPT)
    else:
        payload = llm.parse(user_text)

    if isinstance(payload, dict):
        choice_index = payload.get("choice_index")
        if isinstance(choice_index, int):
            return choice_index, None
        question = payload.get("question")
        if isinstance(question, str) and question.strip():
            return None, question.strip()

    return None, None


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
    logger.info(
        "query=%s action=%s type_hint=%s quantifier=%s scope_include=%s scope_exclude=%s",
        ir.raw,
        ir.action,
        ir.type_hint,
        ir.quantifier,
        sorted(ir.scope_include),
        sorted(ir.scope_exclude),
    )

    # 2. Scope 预过滤
    filtered_devices = apply_scope_filters(devices, ir)

    if not ir.name_hint:
        inferred = _infer_name_hint(ir.raw, filtered_devices)
        if inferred:
            ir.name_hint = inferred

    mapped_category = map_type_to_category(ir.type_hint)
    if not mapped_category or mapped_category == "Unknown":
        inferred_category = _infer_category_from_name_hint(ir.name_hint, filtered_devices)
        if inferred_category:
            mapped_category = inferred_category
    apply_gating = bool(mapped_category and mapped_category != "Unknown")
    if apply_gating:
        gated_devices = filter_by_category(filtered_devices, mapped_category)
    else:
        gated_devices = filtered_devices

    logger.info(
        "mapped_category=%s type_hint=%s apply_gating=%s",
        mapped_category,
        ir.type_hint,
        apply_gating,
    )
    logger.info(
        "gating_before=%s gating_after=%s",
        len(filtered_devices),
        len(gated_devices),
    )

    if is_bulk_quantifier(ir.quantifier):
        if not vector_searcher:
            return RetrievalResult(hint="bulk_requires_vector")

        vector_searcher.index(devices)
        spec_index = getattr(vector_searcher, "spec_index", None)
        if not isinstance(spec_index, dict) or not spec_index:
            return RetrievalResult(hint="bulk_requires_spec_index")

        search_text = _vector_search_text(ir)
        if ir.name_hint and ir.name_hint not in search_text:
            search_text = f"{ir.name_hint} {search_text}"
        options, confidence = build_capability_options(
            query_text=search_text,
            devices=gated_devices,
            vector_searcher=vector_searcher,
            spec_index=spec_index,
        )
        top1_ratio = float(confidence.get("top1_ratio", 0.0))
        margin = float(confidence.get("margin", 0.0))
        logger.info(
            "bulk_options top1_ratio=%.3f margin=%.3f options=%s",
            top1_ratio,
            margin,
            ",".join(
                f"{opt.capability_id}:{opt.probability:.3f}"
                for opt in options[:5]
            ),
        )

        if not options:
            return RetrievalResult(
                hint="no_capability_options",
                meta={"top1_ratio": top1_ratio, "margin": margin},
            )

        if is_low_confidence(top1_ratio, margin):
            if os.getenv(_BULK_ARBITRATION_ENV) == "1":
                choice_index, question = _bulk_arbitrate_choice(
                    llm,
                    query=ir.raw,
                    options=options[:5],
                )
                if choice_index is not None and 0 <= choice_index < len(options[:5]):
                    selected_cap_id = options[choice_index].capability_id
                else:
                    return RetrievalResult(
                        hint="need_clarification",
                        options=options[:3],
                        question=question,
                        meta={"top1_ratio": top1_ratio, "margin": margin},
                    )
            else:
                return RetrievalResult(
                    hint="need_clarification",
                    options=options[:3],
                    meta={"top1_ratio": top1_ratio, "margin": margin},
                )
        else:
            selected_cap_id = options[0].capability_id

        spec_lookup = build_spec_lookup(spec_index)
        targets = select_targets(gated_devices, selected_cap_id, spec_lookup)

        support_count = len(targets)
        total_devices = len(gated_devices)
        coverage = support_count / total_devices if total_devices else 0.0

        if support_count == 0:
            return RetrievalResult(
                hint="no_targets",
                options=options[:3],
                selected_capability_id=selected_cap_id,
                meta={
                    "support_count": support_count,
                    "total_devices": total_devices,
                    "coverage": coverage,
                },
            )

        if support_count > DEFAULT_MAX_TARGETS:
            return RetrievalResult(
                hint="too_many_targets",
                options=options[:3],
                selected_capability_id=selected_cap_id,
                meta={
                    "support_count": support_count,
                    "total_devices": total_devices,
                    "coverage": coverage,
                    "max_targets": DEFAULT_MAX_TARGETS,
                },
            )

        groups = group_by_command_compatibility(targets, selected_cap_id, spec_lookup)
        logger.info(
            "bulk_selected capability_id=%s targets=%s groups=%s coverage=%.3f",
            selected_cap_id,
            support_count,
            len(groups),
            coverage,
        )
        if len(groups) > DEFAULT_MAX_GROUPS:
            return RetrievalResult(
                hint="too_many_targets",
                options=options[:3],
                selected_capability_id=selected_cap_id,
                meta={
                    "support_count": support_count,
                    "total_devices": total_devices,
                    "coverage": coverage,
                    "groups": len(groups),
                    "max_groups": DEFAULT_MAX_GROUPS,
                },
            )

        hint = None
        if coverage < DEFAULT_COVERAGE_THRESHOLD:
            hint = "partial_coverage"

        if len(groups) > top_k:
            hint = hint or "too_many_targets"
            groups = groups[:top_k]

        batches = {
            group.id: split_into_batches(group.device_ids, DEFAULT_BULK_BATCH_SIZE)
            for group in groups
        }
        candidates = [
            Candidate(
                entity_id=group.id,
                entity_kind="group",
                capability_id=selected_cap_id,
                total_score=float(len(group.device_ids)),
                reasons=["bulk_group"],
            )
            for group in groups
        ]

        return RetrievalResult(
            candidates=candidates,
            hint=hint,
            groups=groups,
            batches=batches,
            options=options[:3],
            selected_capability_id=selected_cap_id,
            meta={
                "top1_ratio": top1_ratio,
                "margin": margin,
                "support_count": support_count,
                "total_devices": total_devices,
                "coverage": coverage,
            },
        )

    w_keyword = DEFAULT_KEYWORD_WEIGHT
    w_vector = DEFAULT_VECTOR_WEIGHT
    if not apply_gating:
        w_keyword = FALLBACK_KEYWORD_WEIGHT
        w_vector = FALLBACK_VECTOR_WEIGHT

    # 3. Keyword 召回
    searcher = KeywordSearcher(gated_devices)
    keyword_candidates = searcher.search(ir)

    # 4. Vector 召回（可选）
    vector_candidates = []
    if vector_searcher:
        # 索引全量设备以便复用 embedding；检索时按 device_ids 过滤避免额外设备干扰。
        vector_searcher.index(devices)
        device_ids = {d.id for d in gated_devices}
        search_text = _vector_search_text(ir)
        vector_candidates = vector_searcher.search(
            search_text,
            top_k=max(top_k * 10, 50),
            device_ids=device_ids,
        )

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

    spec_lookup = None
    device_by_id = None
    if vector_searcher:
        spec_index = getattr(vector_searcher, "spec_index", None)
        if isinstance(spec_index, dict) and spec_index:
            spec_lookup = build_spec_lookup(spec_index)
            device_by_id = {device.id: device for device in devices}
            merged = _fill_missing_capability_ids(
                merged,
                query=ir.raw,
                device_by_id=device_by_id,
                spec_lookup=spec_lookup,
            )
            merged = [
                candidate
                for candidate in merged
                if _is_supported_candidate(candidate, device_by_id, spec_lookup)
            ]

    merged = _dedupe_device_candidates(merged)
    if (
        spec_lookup
        and device_by_id
        and _should_force_capability_guess(ir.raw)
    ):
        merged = _apply_capability_guess(
            merged,
            query=ir.raw,
            device_by_id=device_by_id,
            spec_lookup=spec_lookup,
        )
    merged.sort(key=lambda c: c.total_score, reverse=True)

    if merged:
        top_preview = [
            f"{cand.entity_id}:{cand.capability_id}:{cand.total_score:.3f}"
            for cand in merged[:5]
        ]
        logger.info("top_candidates=%s", ",".join(top_preview))

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
