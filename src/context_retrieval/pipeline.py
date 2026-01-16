"""Pipeline 组装。

整合各模块完成上下文检索流程。
"""

import logging
import os
import re

from command_parser import CommandParserConfig, parse_command_output
from command_parser.prompt import DEFAULT_SYSTEM_PROMPT
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
from context_retrieval.models import (
    Candidate,
    CommandRetrieval,
    Device,
    MultiRetrievalResult,
    RetrievalResult,
)
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

_BULK_QUERY_TOKENS = ("所有", "全部", "全体", "所有的", "全部的")
_BULK_QUERY_PREFIXES = ("把", "将", "请")

_BULK_ARBITRATION_SYSTEM_PROMPT = """你是智能家居助手的批量命令选择器。

你将得到用户的原始请求和一组闭集候选 capability 选项。你的任务是在这些候选中选择最匹配的一项，或提出一个澄清问题。

只返回一个 JSON 对象，且必须且只能满足以下两种之一：
- {"choice_index": <0-based integer>}  # 选择某个候选
- {"question": "<string>"}            # 如果无法确定，提出 1 个澄清问题

约束：
- choice_index 必须是整数，且必须在 [0, N-1] 范围内。
- 禁止输出除 JSON 以外的任何文本。
"""


def _strip_bulk_query(raw: str, name_hint: str | None) -> str:
    """移除批量量词与设备名，提取向量检索用文本。"""
    cleaned = raw
    if name_hint:
        cleaned = cleaned.replace(name_hint, " ")
    for token in _BULK_QUERY_TOKENS:
        cleaned = cleaned.replace(token, " ")
    cleaned = cleaned.strip()
    for prefix in _BULK_QUERY_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _vector_search_text(ir) -> str:
    """基于 QueryIR 生成向量检索的查询文本。"""
    raw = (ir.raw or "").strip()
    action_text = (ir.action or "").strip()
    if action_text and _LATIN_LETTERS_RE.search(action_text):
        logger.info(
            "action_invalid_fallback reason=latin_letters action=%s",
            action_text,
        )
        return raw
    if is_bulk_quantifier(ir.quantifier) and raw:
        cleaned = _strip_bulk_query(raw, ir.name_hint)
        if cleaned:
            return cleaned
    return action_text or raw


def _should_force_capability_guess(query: str) -> bool:
    """判断是否需要强制做 capability 猜测。"""
    if not isinstance(query, str) or not query.strip():
        return False
    if not _CJK_RE.search(query):
        return False
    return bool(_DIGIT_RE.search(query) or "%" in query or _CANCEL_TOKEN in query)


def _device_profile_id(device: Device) -> str | None:
    """解析设备的 profile_id（兼容旧字段）。"""
    profile_id = getattr(device, "profile_id", None) or getattr(device, "profileId", None)
    if isinstance(profile_id, str) and profile_id.strip():
        return profile_id.strip()
    return None


def _infer_name_hint(query: str, devices: list[Device]) -> str | None:
    """从原始请求中推断明确的设备名提示。"""
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
    """根据明确设备名推断唯一类别。"""
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


def _is_explicit_device_name(name_hint: str | None, devices: list[Device]) -> bool:
    """判断 name_hint 是否为设备清单中的明确名称。"""
    if not isinstance(name_hint, str) or not name_hint.strip():
        return False
    for device in devices:
        name = getattr(device, "name", None)
        if isinstance(name, str) and name == name_hint:
            return True
    return False


def _guess_capability_id(
    *,
    query: str,
    device: Device,
    spec_lookup,
) -> str | None:
    """从能力文档中猜测最匹配的 capability_id。"""
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
    """为缺失 capability_id 的候选补全能力标识。"""
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
    """同一设备只保留最高分候选。"""
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
    """在满足条件时为候选补充能力猜测标记。"""
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
    """判断候选的 capability 是否在设备规格中存在。"""
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
    """低置信度时使用 LLM 在候选中仲裁或给出澄清问题。"""
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


def _can_bulk_retrieve(ir, vector_searcher: VectorSearcher | None) -> bool:
    """判断当前 QueryIR 是否满足批量检索条件。"""
    if not is_bulk_quantifier(ir.quantifier):
        return False
    if vector_searcher is None:
        logger.info("bulk_disabled reason=no_vector_searcher")
        return False
    spec_index = getattr(vector_searcher, "spec_index", None)
    if not isinstance(spec_index, dict) or not spec_index:
        logger.info("bulk_disabled reason=missing_spec_index")
        return False
    return True


def _generate_command_output(text: str, llm: LLMClient) -> str:
    """调用 LLM 生成命令解析输出文本。"""
    try:
        return llm.generate_with_prompt(text, DEFAULT_SYSTEM_PROMPT)
    except Exception as exc:  # pragma: no cover - 保护主流程
        logger.warning("command_output_failed error=%s", exc)
        return "[]"


def _retrieve_with_ir(
    ir,
    devices: list[Device],
    llm: LLMClient,
    state: ConversationState,
    top_k: int = 5,
    vector_searcher: VectorSearcher | None = None,
) -> RetrievalResult:
    """执行单条 QueryIR 的检索。

    Pipeline 流程：
    1. Scope 预过滤
    2. Keyword 召回
    3. Vector 召回（可选）
    4. 融合评分
    5. Top-K 筛选
    6. 更新会话状态
    """
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

    if _can_bulk_retrieve(ir, vector_searcher):
        vector_searcher.index(devices)
        spec_index = getattr(vector_searcher, "spec_index", {})
        if not isinstance(spec_index, dict) or not spec_index:
            spec_index = {}

        search_text = _vector_search_text(ir)
        if _is_explicit_device_name(ir.name_hint, gated_devices) and ir.name_hint not in search_text:
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


def retrieve(
    text: str,
    devices: list[Device],
    llm: LLMClient,
    state: ConversationState,
    top_k: int = 5,
    vector_searcher: VectorSearcher | None = None,
) -> MultiRetrievalResult:
    """执行上下文检索（多命令）。"""
    raw_output = _generate_command_output(text, llm)
    parsed = parse_command_output(
        raw_output,
        config=CommandParserConfig(),
    )

    results: list[CommandRetrieval] = []
    for command in parsed.commands:
        ir = compile_ir(command, raw_text=text)
        result = _retrieve_with_ir(
            ir,
            devices=devices,
            llm=llm,
            state=state,
            top_k=top_k,
            vector_searcher=vector_searcher,
        )
        results.append(CommandRetrieval(command=command, ir=ir, result=result))

    return MultiRetrievalResult(
        commands=results,
        errors=list(parsed.errors),
        degraded=parsed.degraded,
    )


def retrieve_single(
    text: str,
    devices: list[Device],
    llm: LLMClient,
    state: ConversationState,
    top_k: int = 5,
    vector_searcher: VectorSearcher | None = None,
) -> RetrievalResult:
    """执行单命令检索（兼容入口）。"""
    multi = retrieve(
        text=text,
        devices=devices,
        llm=llm,
        state=state,
        top_k=top_k,
        vector_searcher=vector_searcher,
    )

    if not multi.commands:
        return RetrievalResult(
            hint="no_command",
            meta={
                "parser_errors": list(multi.errors),
                "parser_degraded": multi.degraded,
            },
        )

    if len(multi.commands) > 1:
        logger.info("multi_command_result total=%d use_first", len(multi.commands))

    result = multi.commands[0].result
    if multi.errors or multi.degraded:
        result.meta.setdefault("parser_errors", list(multi.errors))
        result.meta.setdefault("parser_degraded", multi.degraded)
    return result
