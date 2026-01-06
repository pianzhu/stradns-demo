"""Category gating helpers."""

from __future__ import annotations

from typing import Iterable

from context_retrieval.models import Device


ALLOWED_CATEGORIES = (
    "AirConditioner",
    "Blind",
    "Charger",
    "Fan",
    "Hub",
    "Light",
    "NetworkAudio",
    "Others",
    "Switch",
    "Television",
    "Washer",
    "SmartPlug",
)

_ALLOWED_CATEGORY_LOOKUP = {category.lower(): category for category in ALLOWED_CATEGORIES}

TYPE_TO_CATEGORY: dict[str, str] = {
    "light": "Light",
    "lamp": "Light",
    "lighting": "Light",
    "blind": "Blind",
    "shade": "Blind",
    "curtain": "Blind",
    "airconditioner": "AirConditioner",
    "air-conditioner": "AirConditioner",
    "air conditioner": "AirConditioner",
    "ac": "AirConditioner",
    "switch": "Switch",
    "plug": "SmartPlug",
    "smartplug": "SmartPlug",
    "outlet": "SmartPlug",
    "television": "Television",
    "tv": "Television",
    "audio": "NetworkAudio",
    "speaker": "NetworkAudio",
    "sound": "NetworkAudio",
    "networkaudio": "NetworkAudio",
    "fan": "Fan",
    "washer": "Washer",
    "washingmachine": "Washer",
    "charger": "Charger",
    "charging": "Charger",
    "hub": "Hub",
    "other": "Others",
    "others": "Others",
}


def map_type_to_category(type_hint: str | None) -> str | None:
    """Map a type hint to a category."""
    normalized = _normalize_hint(type_hint)
    if not normalized:
        return None

    direct = TYPE_TO_CATEGORY.get(normalized)
    if direct:
        return _canonical_category(direct)

    compact = _compact_text(normalized)
    if compact and compact in TYPE_TO_CATEGORY:
        return _canonical_category(TYPE_TO_CATEGORY[compact])

    return None


def filter_by_category(devices: Iterable[Device], category: str | None) -> list[Device]:
    """Filter devices by category."""
    canonical_category = _canonical_category(category)
    if not canonical_category:
        return list(devices)

    compact_category = _compact_text(_normalize_hint(canonical_category))
    if not compact_category:
        return list(devices)

    filtered: list[Device] = []
    for device in devices:
        if _device_matches_category(device, compact_category):
            filtered.append(device)
    return filtered


def _device_matches_category(device: Device, compact_category: str) -> bool:
    device_category = getattr(device, "category", None)
    canonical_category = _canonical_category(device_category)
    if canonical_category:
        compact_device_category = _compact_text(_normalize_hint(canonical_category))
        if compact_device_category == compact_category:
            return True

    device_type = _normalize_hint(device.type)
    if not device_type:
        return False

    compact_device_type = _compact_text(device_type)
    if compact_device_type == compact_category:
        return True

    return compact_category in compact_device_type


def _normalize_hint(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip().lower()
    return stripped or None


def _compact_text(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum())


def _canonical_category(value: str | None) -> str | None:
    normalized = _normalize_hint(value)
    if not normalized:
        return None
    return _ALLOWED_CATEGORY_LOOKUP.get(normalized)
