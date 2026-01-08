"""Document enrichment helpers for vector search."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from context_retrieval.models import Device, ValueOption, ValueRange

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapabilityDoc:
    """Capability document for enrichment."""

    id: str
    description: str = ""
    type: str | None = None
    value_range: ValueRange | None = None
    value_options: list[ValueOption] = field(default_factory=list)
    value_descriptions: list[str] = field(default_factory=list)


VERB_SYNONYMS: dict[str, list[str]] = {
    "enable": ["turn on", "on", "start"],
    "disable": ["turn off", "off", "stop"],
    "set": ["adjust", "change", "configure"],
    "\u7535\u6e90\u542f\u7528": ["\u6253\u5f00", "\u5f00", "\u5f00\u542f", "\u542f\u52a8", "on"],
    "\u7535\u6e90\u5173\u95ed": ["\u5173", "\u5173\u6389", "\u505c\u6b62", "off"],
    "\u8c03": ["\u8c03\u8282", "\u8c03\u6574", "\u8bbe\u7f6e", "\u8c03\u5230", "\u8bbe\u4e3a"],
}


def load_spec_index(spec_path: str) -> dict[str, list[CapabilityDoc]]:
    """Load spec index from spec.jsonl file."""
    with open(spec_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    index: dict[str, list[CapabilityDoc]] = {}
    for profile in _ensure_list(payload):
        profile_id = profile.get("profileId")
        if not isinstance(profile_id, str) or not profile_id:
            continue

        docs: list[CapabilityDoc] = []
        for cap in _ensure_list(profile.get("capabilities")):
            cap_id = cap.get("id")
            if not isinstance(cap_id, str) or not cap_id:
                continue
            description = cap.get("description") or ""
            cap_type = cap.get("type")
            if not isinstance(cap_type, str) or not cap_type.strip():
                cap_type = None

            value_range = _extract_value_range(cap)
            value_options = _extract_value_options(cap)
            value_descriptions = _extract_value_descriptions(cap)
            docs.append(
                CapabilityDoc(
                    id=cap_id,
                    description=description,
                    type=cap_type,
                    value_range=value_range,
                    value_options=value_options,
                    value_descriptions=value_descriptions,
                )
            )

        index[profile_id] = docs

    return index


def enrich_description(desc: str) -> str:
    """Enrich description with verb synonyms."""
    if not isinstance(desc, str):
        return ""
    normalized = desc.strip()
    if not normalized:
        return ""

    lowered = normalized.lower()
    extras: list[str] = []
    seen = set()
    for key, synonyms in VERB_SYNONYMS.items():
        if key in lowered:
            for synonym in synonyms:
                if synonym in seen:
                    continue
                seen.add(synonym)
                extras.append(synonym)

    if not extras:
        return normalized
    return f"{normalized} {' '.join(extras)}"


def build_enriched_doc(device: Device, spec_index: dict[str, list[CapabilityDoc]]) -> list[str]:
    """Build enriched documents for a device."""
    profile_id = getattr(device, "profile_id", None) or getattr(device, "profileId", None)
    docs = spec_index.get(profile_id) if profile_id else None

    if not docs:
        if profile_id:
            logger.warning("spec index missing for device profile_id=%s", profile_id)
        return [_build_fallback_doc(device)]

    enriched_docs: list[str] = []
    for doc in docs:
        parts: list[str] = []

        enriched_desc = enrich_description(doc.description)
        if enriched_desc:
            parts.append(enriched_desc)

        for value_desc in doc.value_descriptions:
            if not isinstance(value_desc, str):
                continue
            cleaned = value_desc.strip()
            if cleaned:
                parts.append(cleaned)

        enriched_docs.append(" ".join(parts))

    return enriched_docs


def _build_fallback_doc(device: Device) -> str:
    parts: list[str] = []
    for value in (device.name, device.room):
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)


def _extract_value_descriptions(capability: dict) -> list[str]:
    descriptions: list[str] = []
    value_list = capability.get("value_list")
    if not isinstance(value_list, list):
        return descriptions
    for item in value_list:
        if not isinstance(item, dict):
            continue
        desc = item.get("description")
        if isinstance(desc, str) and desc.strip():
            descriptions.append(desc.strip())
    return descriptions


def _extract_value_options(capability: dict) -> list[ValueOption]:
    options: list[ValueOption] = []
    value_list = capability.get("value_list")
    if not isinstance(value_list, list):
        return options

    for item in value_list:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        desc = item.get("description")
        description = desc.strip() if isinstance(desc, str) else ""
        options.append(ValueOption(value=value.strip(), description=description))
    return options


def _extract_value_range(capability: dict) -> ValueRange | None:
    value_range = capability.get("value_range")
    if not isinstance(value_range, dict):
        return None

    minimum = value_range.get("minimum")
    maximum = value_range.get("maximum")
    if not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        return None

    unit_value = value_range.get("unit")
    unit = ""
    if isinstance(unit_value, str):
        unit = unit_value
    elif isinstance(unit_value, list):
        first = unit_value[0] if unit_value else None
        if isinstance(first, str):
            unit = first

    return ValueRange(minimum=float(minimum), maximum=float(maximum), unit=unit)


def _ensure_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
