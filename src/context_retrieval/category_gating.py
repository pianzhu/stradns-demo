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
    "Unknown",
    "Switch",
    "Television",
    "Washer",
    "SmartPlug",
)

_ALLOWED_CATEGORY_LOOKUP: dict[str, str] = {}
for category in ALLOWED_CATEGORIES:
    key = "".join(ch for ch in category.lower() if ch.isalnum())
    if key:
        _ALLOWED_CATEGORY_LOOKUP[key] = category


def map_type_to_category(type_hint: str | None) -> str | None:
    """Resolve a canonical category from text.

    The input is expected to be one of the canonical categories, but the function is
    tolerant to case, whitespace, and separators (for example: "Smart Plug",
    "smartplug", or "smartthings:air-conditioner").
    """
    key = _compact_key(type_hint)
    if not key:
        return None

    direct = _ALLOWED_CATEGORY_LOOKUP.get(key)
    if direct:
        return direct

    for category_key, category in _ALLOWED_CATEGORY_LOOKUP.items():
        if category_key and category_key in key:
            return category

    return None


def filter_by_category(devices: Iterable[Device], category: str | None) -> list[Device]:
    """Filter devices by category."""
    device_list = list(devices)

    canonical_category = map_type_to_category(category)
    if not canonical_category:
        return device_list

    category_key = _compact_key(canonical_category)
    if not category_key:
        return device_list

    filtered: list[Device] = []
    for device in device_list:
        if _device_matches_category(device, category_key):
            filtered.append(device)
    return filtered or device_list


def _device_matches_category(device: Device, category_key: str) -> bool:
    for raw_value in _device_category_values(device):
        mapped = map_type_to_category(raw_value)
        if not mapped:
            continue
        mapped_key = _compact_key(mapped)
        if mapped_key == category_key:
            return True
    return False


def _device_category_values(device: Device) -> list[str]:
    values: list[str] = []

    category = getattr(device, "category", None)
    if isinstance(category, str) and category.strip():
        values.append(category)

    categories = getattr(device, "categories", None)
    if isinstance(categories, (list, tuple, set)):
        for item in categories:
            if isinstance(item, str) and item.strip():
                values.append(item)
            elif isinstance(item, dict):
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    values.append(name)

    if isinstance(device.category, str) and device.category.strip():
        values.append(device.category)

    return values


def _compact_key(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return "".join(ch for ch in stripped.lower() if ch.isalnum())
