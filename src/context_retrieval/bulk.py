"""Bulk mode helpers for quantifier semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from context_retrieval.doc_enrichment import CapabilityDoc
from context_retrieval.models import (
    CapabilityOption,
    Device,
    Group,
)
from context_retrieval.vector_search import VectorSearcher


DEFAULT_OPTIONS_TOP_N = 5
DEFAULT_OPTIONS_SEARCH_K = 80
DEFAULT_EVIDENCE_PER_CAPABILITY = 3

DEFAULT_BULK_BATCH_SIZE = 20

DEFAULT_CONFIDENCE_TOP1_RATIO_THRESHOLD = 0.55
DEFAULT_CONFIDENCE_MARGIN_THRESHOLD = 0.15

DEFAULT_COVERAGE_THRESHOLD = 0.8

DEFAULT_MAX_TARGETS = 200
DEFAULT_MAX_GROUPS = 20


@dataclass(frozen=True)
class BulkSelectionStats:
    top1_ratio: float
    margin: float
    coverage: float
    support_count: int
    total_devices: int


def is_bulk_quantifier(quantifier: str | None) -> bool:
    """判断量词是否表示批量选择。"""
    return quantifier in {"all", "except"}


def device_profile_id(device: Device) -> str | None:
    """从设备信息中解析 profile_id（兼容旧字段）。"""
    profile_id = getattr(device, "profile_id", None) or getattr(device, "profileId", None)
    if isinstance(profile_id, str) and profile_id.strip():
        return profile_id.strip()
    return None


def build_spec_lookup(
    spec_index: dict[str, list[CapabilityDoc]],
) -> dict[str, dict[str, CapabilityDoc]]:
    """构建 profile_id 到 capability 文档的索引。"""
    lookup: dict[str, dict[str, CapabilityDoc]] = {}
    for profile_id, docs in spec_index.items():
        inner: dict[str, CapabilityDoc] = {}
        for doc in docs:
            if doc.id:
                inner[doc.id] = doc
        lookup[profile_id] = inner
    return lookup


def device_supports_capability(
    device: Device,
    capability_id: str,
    spec_lookup: dict[str, dict[str, CapabilityDoc]],
) -> bool:
    """判断设备是否支持指定 capability。"""
    profile_id = device_profile_id(device)
    if not profile_id:
        return False
    profile_docs = spec_lookup.get(profile_id)
    if not profile_docs:
        return False
    return capability_id in profile_docs


def capability_doc_for_device(
    device: Device,
    capability_id: str,
    spec_lookup: dict[str, dict[str, CapabilityDoc]],
) -> CapabilityDoc | None:
    """获取设备对应 capability 的文档。"""
    profile_id = device_profile_id(device)
    if not profile_id:
        return None
    return spec_lookup.get(profile_id, {}).get(capability_id)


def find_capability_description(
    capability_id: str,
    spec_lookup: dict[str, dict[str, CapabilityDoc]],
) -> str:
    """查找 capability 描述文本。"""
    for profile_docs in spec_lookup.values():
        doc = profile_docs.get(capability_id)
        if doc and isinstance(doc.description, str) and doc.description.strip():
            return doc.description.strip()
    return ""


def build_capability_options(
    *,
    query_text: str,
    devices: list[Device],
    vector_searcher: VectorSearcher,
    spec_index: dict[str, list[CapabilityDoc]],
    options_top_n: int = DEFAULT_OPTIONS_TOP_N,
    options_search_k: int = DEFAULT_OPTIONS_SEARCH_K,
    evidence_per_capability: int = DEFAULT_EVIDENCE_PER_CAPABILITY,
) -> tuple[list[CapabilityOption], dict[str, Any]]:
    """基于检索证据与覆盖率构造 capability 候选。"""
    if not devices:
        return [], {"top1_ratio": 0.0, "margin": 0.0}

    spec_lookup = build_spec_lookup(spec_index)
    device_ids = {device.id for device in devices}
    candidates = vector_searcher.search(
        query_text,
        top_k=options_search_k,
        device_ids=device_ids,
    )

    evidence: dict[str, list[float]] = {}
    for cand in candidates:
        cap_id = cand.capability_id
        if not isinstance(cap_id, str) or not cap_id:
            continue
        evidence.setdefault(cap_id, []).append(float(cand.vector_score))

    aggregated: list[tuple[str, float, list[float]]] = []
    for cap_id, scores in evidence.items():
        top_scores = sorted(scores, reverse=True)[:evidence_per_capability]
        aggregated.append((cap_id, sum(top_scores), top_scores))

    aggregated.sort(key=lambda item: item[1], reverse=True)
    aggregated = aggregated[:options_top_n]

    total_score = sum(item[1] for item in aggregated)
    options: list[CapabilityOption] = []
    for cap_id, score, top_scores in aggregated:
        support_devices = [
            device for device in devices
            if device_supports_capability(device, cap_id, spec_lookup)
        ]
        support_count = len(support_devices)
        total_devices = len(devices)
        coverage = support_count / total_devices if total_devices else 0.0

        examples: list[str] = []
        for device in support_devices[:3]:
            room = device.room.strip() if isinstance(device.room, str) else ""
            name = device.name.strip() if isinstance(device.name, str) else ""
            if room and name:
                examples.append(f"{room}/{name}")
            elif name:
                examples.append(name)
            else:
                examples.append(device.id)

        probability = score / total_score if total_score else 0.0
        options.append(
            CapabilityOption(
                capability_id=cap_id,
                description=find_capability_description(cap_id, spec_lookup),
                score=score,
                top_scores=top_scores,
                probability=probability,
                support_count=support_count,
                total_devices=total_devices,
                coverage=coverage,
                examples=examples,
            )
        )

    top1_ratio, margin = compute_confidence(options)
    return options, {
        "top1_ratio": top1_ratio,
        "margin": margin,
    }


def compute_confidence(options: list[CapabilityOption]) -> tuple[float, float]:
    """计算 top1 比例与前两名差距。"""
    if not options:
        return 0.0, 0.0

    sorted_opts = sorted(options, key=lambda opt: opt.probability, reverse=True)
    top1 = float(sorted_opts[0].probability)
    if len(sorted_opts) < 2:
        return top1, top1
    top2 = float(sorted_opts[1].probability)
    return top1, top1 - top2


def is_low_confidence(
    top1_ratio: float,
    margin: float,
    *,
    top1_ratio_threshold: float = DEFAULT_CONFIDENCE_TOP1_RATIO_THRESHOLD,
    margin_threshold: float = DEFAULT_CONFIDENCE_MARGIN_THRESHOLD,
) -> bool:
    """判断置信度是否过低。"""
    return top1_ratio < top1_ratio_threshold or margin < margin_threshold


def select_targets(
    devices: list[Device],
    capability_id: str,
    spec_lookup: dict[str, dict[str, CapabilityDoc]],
) -> list[Device]:
    """筛选出支持指定 capability 的设备。"""
    return [
        device for device in devices
        if device_supports_capability(device, capability_id, spec_lookup)
    ]


def group_by_command_compatibility(
    targets: list[Device],
    capability_id: str,
    spec_lookup: dict[str, dict[str, CapabilityDoc]],
) -> list[Group]:
    """按命令兼容性对设备分组。"""
    buckets: dict[tuple, list[Device]] = {}
    for device in targets:
        doc = capability_doc_for_device(device, capability_id, spec_lookup)
        if doc is None:
            continue
        signature = compatibility_signature(doc)
        buckets.setdefault(signature, []).append(device)

    groups: list[Group] = []
    for idx, (_, devices) in enumerate(buckets.items(), start=1):
        groups.append(
            Group(
                id=f"group-{idx}",
                name=f"compatibility-{idx}",
                device_ids=[device.id for device in devices],
            )
        )
    groups.sort(key=lambda g: len(g.device_ids), reverse=True)
    return groups


def compatibility_signature(doc: CapabilityDoc) -> tuple:
    """生成描述命令兼容性的签名。"""
    value_range = None
    if doc.value_range is not None:
        value_range = (
            float(doc.value_range.minimum),
            float(doc.value_range.maximum),
            doc.value_range.unit or "",
        )

    value_values: tuple[str, ...] | None = None
    if doc.value_options:
        values = [
            opt.value for opt in doc.value_options
            if isinstance(opt.value, str) and opt.value.strip()
        ]
        value_values = tuple(sorted(set(values)))

    return (
        doc.type,
        value_range,
        value_values,
    )


def split_into_batches(device_ids: list[str], batch_size: int) -> list[list[str]]:
    """按固定大小切分设备列表。"""
    if batch_size <= 0:
        return [list(device_ids)]
    return [
        device_ids[i : i + batch_size]
        for i in range(0, len(device_ids), batch_size)
    ]
