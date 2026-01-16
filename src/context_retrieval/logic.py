"""复杂语义求值。

处理 scope 过滤（包含/排除）。条件依赖扩展待后续优化。
"""

from __future__ import annotations

import re
from typing import Iterable

from context_retrieval.models import Device, QueryIR

_WHITESPACE_RE = re.compile(r"\s+")
_BRACKET_TRANSLATION = str.maketrans(
    {
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
    }
)
_DASH_TRANSLATION = str.maketrans(
    {
        "－": "-",
        "—": "-",
        "–": "-",
        "―": "-",
        "−": "-",
    }
)


def _normalize_text(value: str) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    cleaned = cleaned.translate(_BRACKET_TRANSLATION)
    cleaned = cleaned.translate(_DASH_TRANSLATION)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _normalize_room_terms(terms: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for term in terms:
        if not isinstance(term, str):
            continue
        if term == "*":
            continue
        cleaned = _normalize_text(term)
        if not cleaned or len(cleaned) <= 1:
            continue
        normalized.add(cleaned)
    return normalized


def _overlaps(span: tuple[int, int], other: tuple[int, int]) -> bool:
    return span[0] < other[1] and other[0] < span[1]


def _extract_room_from_name(
    name: str,
    room_terms: list[str],
) -> tuple[str | None, bool]:
    if not name or not room_terms:
        return None, False

    spans: list[tuple[int, int]] = []
    matched: list[str] = []

    for term in room_terms:
        start = 0
        while True:
            idx = name.find(term, start)
            if idx < 0:
                break
            span = (idx, idx + len(term))
            if any(_overlaps(span, existing) for existing in spans):
                start = idx + 1
                continue
            spans.append(span)
            matched.append(term)
            start = idx + len(term)

    unique: list[str] = []
    seen: set[str] = set()
    for term in matched:
        if term in seen:
            continue
        seen.add(term)
        unique.append(term)

    if not unique:
        return None, False
    if len(unique) > 1:
        return None, True
    return unique[0], False


def apply_scope_filters(
    devices: list[Device],
    ir: QueryIR,
) -> tuple[list[Device], dict[str, object]]:
    """根据 IR 的 scope 过滤设备。"""
    include_terms = _normalize_room_terms(ir.scope_include)
    exclude_terms = _normalize_room_terms(ir.scope_exclude)
    rooms_known = _normalize_room_terms(
        _normalize_text(device.room) for device in devices
    )
    command_terms = include_terms | exclude_terms
    unknown_terms = sorted(term for term in command_terms if term not in rooms_known)
    room_terms = sorted(rooms_known | command_terms, key=len, reverse=True)

    meta: dict[str, object] = {}
    if unknown_terms:
        meta["room_unknown_terms"] = unknown_terms

    room_name_used = 0
    room_name_ambiguous = 0
    scoped: list[tuple[Device, str, str | None, bool]] = []
    enable_unknown_fallback = bool(unknown_terms)

    for device in devices:
        room_norm = _normalize_text(device.room)
        name_norm = _normalize_text(device.name)
        name_room, ambiguous = _extract_room_from_name(name_norm, room_terms)
        room_conflict = not room_norm or (
            name_room is not None and room_norm and name_room != room_norm
        )
        use_name_fallback = enable_unknown_fallback or room_conflict

        if ambiguous and use_name_fallback:
            room_name_ambiguous += 1
            name_room = None

        if use_name_fallback and name_room:
            room_name_used += 1

        if exclude_terms:
            if room_norm and room_norm in exclude_terms:
                continue
            if use_name_fallback and name_room and name_room in exclude_terms:
                continue

        scoped.append((device, room_norm, name_room, use_name_fallback))

    result = [device for device, _, _, _ in scoped]

    if include_terms:
        include_filtered = [
            device
            for device, room_norm, name_room, use_name_fallback in scoped
            if (room_norm and room_norm in include_terms)
            or (use_name_fallback and name_room and name_room in include_terms)
        ]
        if include_filtered:
            result = include_filtered
        else:
            meta["scope_include_fallback"] = 1

    if room_name_used:
        meta["room_name_used"] = room_name_used
    if room_name_ambiguous:
        meta["room_name_ambiguous"] = room_name_ambiguous

    return result, meta
