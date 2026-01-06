"""Category metrics for coverage, mapping, and gating recall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class CategoryCoverage:
    """Category coverage statistics."""

    total: int
    with_category: int
    missing: int
    coverage_rate: float
    missing_rate: float


@dataclass(frozen=True)
class MappingStats:
    """Type hint mapping statistics."""

    total: int
    with_type_hint: int
    hits: int
    hit_rate: float
    trigger_rate: float


@dataclass(frozen=True)
class RecallCase:
    """Recall comparison case for hard/soft gating."""

    expected_ids: list[str]
    hard_ranked_ids: list[str]
    soft_ranked_ids: list[str]


@dataclass(frozen=True)
class RecallComparison:
    """Recall curves for hard and soft gating."""

    hard: dict[int, float]
    soft: dict[int, float]
    total: int = 0


def compute_category_coverage(items: Iterable[dict]) -> CategoryCoverage:
    """Compute category coverage from SmartThings device items."""
    total = 0
    with_category = 0

    for item in items:
        total += 1
        if _item_has_category(item):
            with_category += 1

    missing = total - with_category
    coverage_rate = with_category / total if total else 0.0
    missing_rate = missing / total if total else 0.0

    return CategoryCoverage(
        total=total,
        with_category=with_category,
        missing=missing,
        coverage_rate=coverage_rate,
        missing_rate=missing_rate,
    )


def compute_mapping_stats(
    type_hints: Iterable[str | None],
    mapping: Mapping[str, str],
) -> MappingStats:
    """Compute hit and trigger rates for type hint mapping."""
    total = 0
    with_type_hint = 0
    hits = 0

    mapping_lower = {
        key.lower(): value
        for key, value in mapping.items()
        if isinstance(key, str)
    }

    for hint in type_hints:
        total += 1
        normalized = _normalize_hint(hint)
        if normalized is None:
            continue
        with_type_hint += 1

        if normalized in mapping or normalized.lower() in mapping_lower:
            hits += 1

    hit_rate = hits / with_type_hint if with_type_hint else 0.0
    trigger_rate = hits / total if total else 0.0

    return MappingStats(
        total=total,
        with_type_hint=with_type_hint,
        hits=hits,
        hit_rate=hit_rate,
        trigger_rate=trigger_rate,
    )


def compare_gating_recall(
    cases: Sequence[RecallCase],
    k_values: Sequence[int],
) -> RecallComparison:
    """Compare recall@k for hard and soft gating."""
    ks = sorted({int(k) for k in k_values if int(k) > 0})
    total = len(cases)

    hard: dict[int, float] = {}
    soft: dict[int, float] = {}

    for k in ks:
        hard_hits = 0
        soft_hits = 0
        for case in cases:
            if _has_recall(case.expected_ids, case.hard_ranked_ids, k):
                hard_hits += 1
            if _has_recall(case.expected_ids, case.soft_ranked_ids, k):
                soft_hits += 1

        hard[k] = hard_hits / total if total else 0.0
        soft[k] = soft_hits / total if total else 0.0

    return RecallComparison(hard=hard, soft=soft, total=total)


def _item_has_category(item: dict) -> bool:
    if not isinstance(item, dict):
        return False

    components = item.get("components")
    if not components:
        return False

    for component in components:
        if not isinstance(component, dict):
            continue
        categories = component.get("categories")
        if not categories:
            continue
        for category in categories:
            if isinstance(category, dict) and category.get("name"):
                return True
    return False


def _normalize_hint(hint: str | None) -> str | None:
    if not isinstance(hint, str):
        return None
    normalized = hint.strip()
    if not normalized:
        return None
    return normalized


def _has_recall(expected_ids: Sequence[str], ranked_ids: Sequence[str], k: int) -> bool:
    if not expected_ids:
        return True
    if not ranked_ids:
        return False

    top_ids = set(ranked_ids[:k])
    for expected in expected_ids:
        if expected in top_ids:
            return True
    return False
