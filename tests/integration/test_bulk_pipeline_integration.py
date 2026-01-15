"""DashScope bulk pipeline integration tests."""

from __future__ import annotations

import json
import os
import time
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from context_retrieval.doc_enrichment import load_spec_index
from context_retrieval.models import Device
from context_retrieval.pipeline import retrieve
from context_retrieval.state import ConversationState

# Progress logging toggle (default enabled; set to 0 to disable)
PROGRESS_ENABLED = os.getenv("DASHSCOPE_IT_PROGRESS", "1") != "0"

FIXTURE_DIR = Path(__file__).parent
CASE_PATH = FIXTURE_DIR / "dashscope_bulk_pipeline_cases.jsonl"
ROOMS_PATH = FIXTURE_DIR / "smartthings_rooms.jsonl"
DEVICES_PATH = FIXTURE_DIR / "smartthings_devices.jsonl"

# Skip switch
SKIP_REASON = None
if not os.getenv("RUN_DASHSCOPE_IT"):
    SKIP_REASON = "RUN_DASHSCOPE_IT=1 is required to enable DashScope integration tests"
elif not os.getenv("DASHSCOPE_API_KEY"):
    SKIP_REASON = "DASHSCOPE_API_KEY is required to enable DashScope integration tests"

# Configurable params
PIPELINE_TOP_K = int(os.getenv("DASHSCOPE_PIPELINE_TOP_K", "5"))
MAX_CASES = int(os.getenv("DASHSCOPE_BULK_IT_MAX_CASES", "0")) or None
LLM_MODEL = os.getenv("DASHSCOPE_LLM_MODEL", "qwen-flash")
EMBEDDING_MODEL = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")


def _log_progress(message: str) -> None:
    if PROGRESS_ENABLED:
        print(message, flush=True)


def _short_text(text: str, max_len: int = 60) -> str:
    cleaned = (text or "").replace("\n", " ").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[: max_len - 3]}..."


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def load_room_map(path: Path) -> dict[str, str]:
    room_map: dict[str, str] = {}
    for item in load_jsonl(path):
        room_id = item.get("roomId")
        name = item.get("name")
        if isinstance(room_id, str) and isinstance(name, str) and room_id and name:
            room_map[room_id] = name
    return room_map


def _extract_device_name(item: dict[str, Any]) -> str:
    for key in ("label", "name", "deviceId"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Unknown"


def _extract_profile_id(item: dict[str, Any]) -> str | None:
    profile = item.get("profile")
    if isinstance(profile, dict):
        profile_id = profile.get("id")
        if isinstance(profile_id, str) and profile_id.strip():
            return profile_id.strip()
    return None


def _extract_category(item: dict[str, Any]) -> str | None:
    components = item.get("components")
    if not isinstance(components, list):
        return None
    for component in components:
        if not isinstance(component, dict):
            continue
        categories = component.get("categories")
        if not isinstance(categories, list):
            continue
        for category in categories:
            if not isinstance(category, dict):
                continue
            name = category.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def build_devices_from_items(
    items: list[dict[str, Any]],
    room_map: dict[str, str],
) -> list[Device]:
    devices: list[Device] = []
    for item in items:
        device_id = item.get("deviceId")
        if not isinstance(device_id, str) or not device_id:
            continue
        name = _extract_device_name(item)
        room_id = item.get("roomId")
        room = room_map.get(room_id, "") if isinstance(room_id, str) else ""
        category = _extract_category(item) or "Unknown"
        device = Device(id=device_id, name=name, room=room, category=category)
        profile_id = _extract_profile_id(item)
        if profile_id:
            setattr(device, "profile_id", profile_id)
        devices.append(device)
    return devices


def load_cases() -> list[dict[str, Any]]:
    cases = load_jsonl(CASE_PATH)
    if MAX_CASES:
        return cases[:MAX_CASES]
    return cases


def build_device_indexes(devices: list[Device]):
    device_by_id: dict[str, Device] = {d.id: d for d in devices}
    room_name_to_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    room_name_category_to_ids: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    for device in devices:
        room = device.room or ""
        name = device.name or ""
        if not room or not name:
            continue
        room_name_to_ids[(room, name)].append(device.id)
        room_name_category_to_ids[(room, name, device.category or "")].append(device.id)

    duplicates = {
        key: ids
        for key, ids in room_name_category_to_ids.items()
        if len(ids) > 1
    }
    if duplicates:
        summary = ", ".join(
            f"{room}/{name}/{category}={ids}"
            for (room, name, category), ids in list(duplicates.items())[:5]
        )
        raise AssertionError(
            "同一房间内存在同名同类设备，建议重命名以降低歧义: " + summary
        )

    room_name_ambiguous = {
        key for key, ids in room_name_to_ids.items() if len(ids) > 1
    }

    label_by_id = {}
    for device in devices:
        label_by_id[device.id] = f"{device.room}/{device.name}"

    return device_by_id, room_name_to_ids, room_name_category_to_ids, room_name_ambiguous, label_by_id


def _parse_room_name(text: str) -> tuple[str, str]:
    if "/" not in text:
        raise ValueError(f"expected '房间/设备名', got: {text}")
    room, name = text.split("/", 1)
    room = room.strip()
    name = name.strip()
    if not room or not name:
        raise ValueError(f"invalid room/name: {text}")
    return room, name


def resolve_expected_devices(
    case: dict[str, Any],
    room_name_to_ids: dict[tuple[str, str], list[str]],
    room_name_category_to_ids: dict[tuple[str, str, str], list[str]],
    room_name_ambiguous: set[tuple[str, str]],
) -> set[str]:
    result: set[str] = set()

    expected_ids = case.get("expected_device_ids") or []
    if isinstance(expected_ids, list):
        for device_id in expected_ids:
            if isinstance(device_id, str) and device_id:
                result.add(device_id)

    expected_devices = case.get("expected_devices") or []
    if not isinstance(expected_devices, list):
        raise ValueError("expected_devices must be a list")

    for entry in expected_devices:
        if isinstance(entry, str):
            room, name = _parse_room_name(entry)
            if (room, name) in room_name_ambiguous:
                raise ValueError(f"房间内同名设备需指定 category: {room}/{name}")
            ids = room_name_to_ids.get((room, name))
            if not ids:
                raise ValueError(f"未找到设备: {room}/{name}")
            if len(ids) > 1:
                raise ValueError(f"房间内同名设备需改名: {room}/{name}")
            result.add(ids[0])
            continue

        if isinstance(entry, dict):
            room = entry.get("room")
            name = entry.get("name")
            category = entry.get("category")
            if not isinstance(room, str) or not isinstance(name, str):
                raise ValueError(f"expected_devices entry missing room/name: {entry}")
            room = room.strip()
            name = name.strip()
            if category is not None:
                if not isinstance(category, str) or not category.strip():
                    raise ValueError(f"invalid category: {entry}")
                category = category.strip()
                ids = room_name_category_to_ids.get((room, name, category))
            else:
                if (room, name) in room_name_ambiguous:
                    raise ValueError(f"房间内同名设备需指定 category: {room}/{name}")
                ids = room_name_to_ids.get((room, name))
            if not ids:
                raise ValueError(f"未找到设备: {room}/{name} {category or ''}")
            if len(ids) > 1:
                raise ValueError(f"房间内同名设备需改名: {room}/{name}")
            result.add(ids[0])
            continue

        raise ValueError(f"unexpected expected_devices entry: {entry}")

    return result


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopeBulkPipelineIntegration(unittest.TestCase):
    """DashScope bulk pipeline integration tests."""

    @classmethod
    def setUpClass(cls):
        import logging

        logging.basicConfig(level=logging.INFO)
        from context_retrieval.ir_compiler import DashScopeLLM
        from context_retrieval.vector_search import DashScopeVectorSearcher

        start = time.perf_counter()
        cls.llm = DashScopeLLM(model=LLM_MODEL)

        room_map = load_room_map(ROOMS_PATH)
        device_items = load_jsonl(DEVICES_PATH)
        cls.devices = build_devices_from_items(device_items, room_map)
        (
            cls.device_by_id,
            cls.room_name_to_ids,
            cls.room_name_category_to_ids,
            cls.room_name_ambiguous,
            cls.label_by_id,
        ) = build_device_indexes(cls.devices)

        spec_path = Path(__file__).parent.parent.parent / "src" / "spec.jsonl"
        spec_index = load_spec_index(str(spec_path))
        cls.vector_searcher = DashScopeVectorSearcher(
            spec_index=spec_index,
            model=EMBEDDING_MODEL,
        )

        index_start = time.perf_counter()
        cls.vector_searcher.index(cls.devices)
        _log_progress(
            f"[BulkIT] init done llm={LLM_MODEL} embedding={EMBEDDING_MODEL} "
            f"devices={len(cls.devices)} index_elapsed={time.perf_counter() - index_start:.2f}s "
            f"elapsed={time.perf_counter() - start:.2f}s"
        )

    def test_bulk_pipeline_cases(self):
        cases = load_cases()
        if not cases:
            self.fail("no cases loaded")

        results_by_complexity: dict[str, Counter[str]] = defaultdict(Counter)
        failed_cases: list[tuple[str, str]] = []

        for idx, case in enumerate(cases, start=1):
            case_id = case.get("id", f"case-{idx}")
            query = case.get("query", "")
            complexity = case.get("complexity", "unknown")
            expected_caps = set(case.get("expected_capability_ids") or [])
            notes = case.get("notes", "")

            try:
                if not isinstance(notes, str):
                    raise ValueError("notes must be a string")

                raw_expected_ids = case.get("expected_device_ids")
                if not isinstance(raw_expected_ids, list) or not raw_expected_ids:
                    raise ValueError("expected_device_ids is required and must be a non-empty list")

                expected_devices = {
                    device_id for device_id in raw_expected_ids
                    if isinstance(device_id, str) and device_id
                }
                if len(expected_devices) != len(raw_expected_ids):
                    raise ValueError("expected_device_ids must contain non-empty strings only")

                if "expected_devices" in case:
                    resolved_from_descriptors = resolve_expected_devices(
                        {"expected_devices": case.get("expected_devices") or []},
                        self.room_name_to_ids,
                        self.room_name_category_to_ids,
                        self.room_name_ambiguous,
                    )
                    if resolved_from_descriptors != expected_devices:
                        raise ValueError(
                            f"expected_device_ids mismatch expected_devices: ids={sorted(expected_devices)} "
                            f"expected_devices={sorted(resolved_from_descriptors)}"
                        )

                if not expected_caps:
                    raise ValueError("expected_capability_ids is empty")

                call_start = time.perf_counter()
                result = retrieve(
                    text=query,
                    devices=self.devices,
                    llm=self.llm,
                    state=ConversationState(),
                    top_k=PIPELINE_TOP_K,
                    vector_searcher=self.vector_searcher,
                )
                call_cost = time.perf_counter() - call_start

                actual_devices: set[str] = set()
                if result.groups:
                    for group in result.groups:
                        actual_devices.update(group.device_ids)
                else:
                    for cand in result.candidates:
                        if cand.entity_kind == "device":
                            actual_devices.add(cand.entity_id)

                candidate_caps = {
                    cand.capability_id
                    for cand in result.candidates
                    if isinstance(cand.capability_id, str) and cand.capability_id
                }
                option_caps = {
                    opt.capability_id
                    for opt in result.options
                    if isinstance(opt.capability_id, str) and opt.capability_id
                }
                selected_cap = result.selected_capability_id
                actual_caps = {selected_cap} if selected_cap else candidate_caps

                device_missing = expected_devices - actual_devices
                cap_missing = expected_caps - actual_caps

                status = "PASS"
                hint = result.hint
                clarify_ok = False
                if hint in {"need_clarification", "too_many_targets"}:
                    clarify_ok = bool(result.question) or expected_caps <= option_caps
                    if selected_cap:
                        clarify_ok = clarify_ok or expected_caps <= {selected_cap}
                    status = "CLARIFY_PASS" if clarify_ok else "FAIL"
                else:
                    if device_missing or cap_missing:
                        status = "FAIL"

                results_by_complexity[str(complexity)][status] += 1

                expected_device_labels = [
                    self.label_by_id.get(device_id, device_id)
                    for device_id in sorted(expected_devices)
                ]
                actual_device_labels = [
                    self.label_by_id.get(device_id, device_id)
                    for device_id in sorted(actual_devices)
                ]

                group_preview = [
                    f"{group.id}:{len(group.device_ids)}"
                    for group in result.groups[:5]
                ]
                batches_preview = [
                    f"{gid}:{len(batches)}"
                    for gid, batches in list(result.batches.items())[:5]
                ]
                option_preview = ",".join(list(option_caps)[:5])

                _log_progress(
                    f"[BulkIT] {idx}/{len(cases)} {case_id} {status} "
                    f"elapsed={call_cost:.2f}s hint={hint} "
                    f"query={_short_text(str(query))}"
                )
                _log_progress(
                    f"  expected_devices={expected_device_labels}"
                )
                _log_progress(
                    f"  actual_devices={actual_device_labels}"
                )
                _log_progress(
                    f"  expected_caps={sorted(expected_caps)} actual_caps={sorted(actual_caps)} "
                    f"options={option_preview} selected={selected_cap}"
                )
                if device_missing:
                    missing_labels = [
                        self.label_by_id.get(device_id, device_id)
                        for device_id in sorted(device_missing)
                    ]
                    _log_progress(f"  missing_devices={missing_labels}")
                if cap_missing:
                    _log_progress(f"  missing_caps={sorted(cap_missing)}")
                if result.question:
                    _log_progress(f"  question={result.question}")
                if group_preview:
                    _log_progress(f"  groups={group_preview} batches={batches_preview}")

                if status == "FAIL":
                    failed_cases.append((case_id, f"missing_devices={len(device_missing)} missing_caps={len(cap_missing)}"))

                time.sleep(0.05)

            except Exception as exc:
                results_by_complexity[str(complexity)]["ERROR"] += 1
                failed_cases.append((case_id, str(exc)))
                _log_progress(
                    f"[BulkIT] {idx}/{len(cases)} {case_id} ERROR "
                    f"query={_short_text(str(query))} err={exc}"
                )

        print("\n=== Bulk pipeline integration summary ===")
        for complexity, stats in results_by_complexity.items():
            total = sum(stats.values())
            summary = ", ".join(f"{k}={v}" for k, v in stats.items())
            print(f"{complexity}: total={total} {summary}")

        if failed_cases:
            print("\nFailed cases (first 10):")
            for case_id, reason in failed_cases[:10]:
                print(f"  {case_id}: {reason}")

        self.assertFalse(failed_cases, f"failed cases: {len(failed_cases)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
