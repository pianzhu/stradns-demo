"""DashScope integration tests.

Uses real DashScope API (qwen-flash + text-embedding-v4) to validate:
- LLM extraction accuracy
- Embedding recall rate

Requirements:
- DASHSCOPE_API_KEY environment variable
- RUN_DASHSCOPE_IT=1 environment variable

Optional environment variables:
- DASHSCOPE_TOP_N: embedding top-N, default 10
- DASHSCOPE_MAX_QUERIES: max test cases, default unlimited
- DASHSCOPE_LLM_MODEL: LLM model name, default qwen-flash
- DASHSCOPE_EMBEDDING_MODEL: embedding model name, default text-embedding-v4
"""

import json
import os
import time
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from context_retrieval.category_gating import filter_by_category, map_type_to_category
from context_retrieval.doc_enrichment import CapabilityDoc, load_spec_index
from context_retrieval.models import Candidate, Device
from context_retrieval.scoring import apply_room_bonus

# Progress logging toggle (default enabled; set to 0 to disable)
PROGRESS_ENABLED = os.getenv("DASHSCOPE_IT_PROGRESS", "1") != "0"

FIXTURE_DIR = Path(__file__).parent
QUERY_PATH = FIXTURE_DIR / "dashscope_integration_queries.json"
ROOMS_PATH = FIXTURE_DIR / "smartthings_rooms.jsonl"
DEVICES_PATH = FIXTURE_DIR / "smartthings_devices.jsonl"


def _log_progress(message: str) -> None:
    """Print progress with flush for real-time output."""
    if PROGRESS_ENABLED:
        print(message, flush=True)


def _short_text(text: str, max_len: int = 60) -> str:
    """Shorten text for log output."""
    cleaned = (text or "").replace("\n", " ").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[: max_len - 3]}..."


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL file into a list of dicts."""
    items: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def load_room_map(path: Path) -> dict[str, str]:
    """Load roomId to room name mapping from JSONL."""
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
    """Build Device entries from SmartThings-style items."""
    devices: list[Device] = []
    for item in items:
        device_id = item.get("deviceId")
        if not isinstance(device_id, str) or not device_id:
            continue
        name = _extract_device_name(item)
        room_id = item.get("roomId")
        room = room_map.get(room_id, "") if isinstance(room_id, str) else ""
        category = _extract_category(item)
        device_type = category or "Unknown"
        device = Device(id=device_id, name=name, room=room, type=device_type)
        profile_id = _extract_profile_id(item)
        if profile_id:
            setattr(device, "profile_id", profile_id)
        if category:
            setattr(device, "category", category)
        devices.append(device)
    return devices


def _build_fallback_text(device: Device) -> str:
    parts: list[str] = []
    for value in (device.name, device.room, device.type):
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)


def build_capability_text(doc: CapabilityDoc) -> str:
    """Build capability text from description and value descriptions."""
    parts: list[str] = []
    if isinstance(doc.description, str) and doc.description.strip():
        parts.append(doc.description.strip())
    for value_desc in doc.value_descriptions:
        if isinstance(value_desc, str) and value_desc.strip():
            parts.append(value_desc.strip())
    return " ".join(parts)


def build_command_corpus(
    devices: list[Device],
    spec_index: dict[str, list[CapabilityDoc]],
) -> tuple[list[dict[str, str | None]], list[str]]:
    entries: list[dict[str, str | None]] = []
    texts: list[str] = []

    for device in devices:
        profile_id = getattr(device, "profile_id", None) or getattr(
            device, "profileId", None
        )
        spec_docs = spec_index.get(profile_id) if profile_id else None

        if not spec_docs:
            entries.append(
                {
                    "device_id": device.id,
                    "capability_id": None,
                    "category": getattr(device, "category", None),
                    "room": device.room,
                }
            )
            texts.append(_build_fallback_text(device))
            continue

        for spec_doc in spec_docs:
            entries.append(
                {
                    "device_id": device.id,
                    "capability_id": spec_doc.id,
                    "category": getattr(device, "category", None),
                    "room": device.room,
                }
            )
            texts.append(build_capability_text(spec_doc))

    return entries, texts


def filter_queries_by_capabilities(
    queries: list[dict[str, Any]],
    available_capabilities: set[str],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in queries:
        expected = item.get("expected_capability_ids", [])
        if not isinstance(expected, list):
            continue
        if any(cap in available_capabilities for cap in expected):
            filtered.append(item)
    return filtered


def select_entries_by_device_ids(
    entries: list[dict[str, Any]],
    embeddings: np.ndarray,
    device_ids: set[str],
) -> tuple[list[dict[str, Any]], np.ndarray]:
    if not device_ids:
        return entries, embeddings
    indices = [
        idx for idx, entry in enumerate(entries) if entry.get("device_id") in device_ids
    ]
    if not indices:
        return entries, embeddings
    filtered_embeddings = embeddings[indices]
    filtered_entries = [entries[idx] for idx in indices]
    return filtered_entries, filtered_embeddings


# Skip switch
SKIP_REASON = None
if not os.getenv("RUN_DASHSCOPE_IT"):
    SKIP_REASON = "RUN_DASHSCOPE_IT=1 is required to enable DashScope integration tests"
elif not os.getenv("DASHSCOPE_API_KEY"):
    SKIP_REASON = "DASHSCOPE_API_KEY is required to enable DashScope integration tests"

# Configurable params
TOP_N = int(os.getenv("DASHSCOPE_TOP_N", "10"))
MAX_QUERIES = int(os.getenv("DASHSCOPE_MAX_QUERIES", "0")) or None
LLM_MODEL = os.getenv("DASHSCOPE_LLM_MODEL", "qwen-flash")
EMBEDDING_MODEL = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")


def load_test_queries() -> list[dict[str, Any]]:
    """Load test cases."""
    with open(QUERY_PATH, "r", encoding="utf-8") as handle:
        queries = json.load(handle)
    if MAX_QUERIES:
        queries = queries[:MAX_QUERIES]
    return queries


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopeLLMExtraction(unittest.TestCase):
    """DashScope LLM extraction integration tests."""

    @classmethod
    def setUpClass(cls):
        """Initialize LLM client."""
        from context_retrieval.ir_compiler import DashScopeLLM

        start = time.perf_counter()
        cls.llm = DashScopeLLM(model=LLM_MODEL)
        cls.queries = load_test_queries()
        _log_progress(
            f"[LLM] init done model={LLM_MODEL} queries={len(cls.queries)} "
            f"(DASHSCOPE_MAX_QUERIES={MAX_QUERIES or 'ALL'}) "
            f"elapsed={time.perf_counter() - start:.2f}s"
        )

    def test_llm_extraction_accuracy(self):
        """Validate action coverage and scope_include accuracy."""
        _log_progress("\n[LLM] start...")
        total = 0
        action_present = 0
        scope_total = 0
        scope_correct = 0
        results = []

        cases = [c for c in self.queries if c.get("expected_capability_ids")]
        for idx, case in enumerate(cases, start=1):
            query = case["query"]
            expected = case.get("expected_fields", {}) or {}
            expected_scope = expected.get("scope_include", [])

            total += 1
            try:
                call_start = time.perf_counter()
                result = self.llm.parse(query)
                call_cost = time.perf_counter() - call_start

                action_text = result.get("action", "")
                if isinstance(action_text, str) and action_text.strip():
                    action_present += 1

                if expected_scope:
                    scope_total += 1
                    actual_scope = result.get("scope_include", [])
                    expected_set = set(expected_scope)
                    actual_set = set(actual_scope)
                    if expected_set <= actual_set or expected_set == actual_set:
                        scope_correct += 1

                results.append((query, action_text, expected_scope))
                _log_progress(
                    f"[LLM] {idx}/{len(cases)} ok elapsed={call_cost:.2f}s "
                    f"query={_short_text(query)} action={_short_text(str(action_text))}"
                )
                time.sleep(0.1)

            except Exception as exc:
                results.append((query, "", expected_scope))
                _log_progress(
                    f"[LLM] {idx}/{len(cases)} error query={_short_text(query)} err={exc}"
                )

        action_coverage = action_present / total if total > 0 else 0
        scope_accuracy = scope_correct / scope_total if scope_total > 0 else 0

        print("\n=== LLM extraction summary ===")
        print(f"total cases: {total}")
        print(f"action coverage: {action_coverage:.2%} ({action_present}/{total})")
        print(f"scope accuracy: {scope_accuracy:.2%} ({scope_correct}/{scope_total})")

        self.assertGreaterEqual(
            action_coverage, 0.6, f"action coverage should be >= 60%, got {action_coverage:.2%}"
        )
        if scope_total > 0:
            self.assertGreaterEqual(
                scope_accuracy, 0.6, f"scope accuracy should be >= 60%, got {scope_accuracy:.2%}"
            )


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopeEmbeddingRecall(unittest.TestCase):
    """DashScope embedding recall integration tests."""

    @classmethod
    def setUpClass(cls):
        """Initialize embedding model and index."""
        from context_retrieval.ir_compiler import DashScopeLLM
        from context_retrieval.vector_search import DashScopeEmbeddingModel

        start = time.perf_counter()
        cls.llm = DashScopeLLM(model=LLM_MODEL)
        cls.embedding_model = DashScopeEmbeddingModel(model=EMBEDDING_MODEL)

        queries = load_test_queries()
        spec_path = Path(__file__).parent.parent / "src" / "spec.jsonl"
        spec_index = load_spec_index(str(spec_path))

        room_map = load_room_map(ROOMS_PATH)
        device_items = load_jsonl(DEVICES_PATH)
        devices = build_devices_from_items(device_items, room_map)
        entries, texts = build_command_corpus(devices, spec_index)

        available_capabilities = {
            entry["capability_id"]
            for entry in entries
            if entry.get("capability_id")
        }
        filtered_queries = filter_queries_by_capabilities(queries, available_capabilities)

        cls.devices = devices
        cls.devices_by_id = {device.id: device for device in devices}
        cls.entries = entries
        cls.texts = texts
        cls.queries = filtered_queries or queries

        _log_progress(
            f"[Embedding] init done llm={LLM_MODEL} embedding={EMBEDDING_MODEL} "
            f"queries={len(cls.queries)} entries={len(cls.entries)} devices={len(cls.devices)} "
            f"elapsed={time.perf_counter() - start:.2f}s"
        )

        print(f"\nBuilding embedding index for {len(cls.entries)} commands...")
        index_start = time.perf_counter()
        cls.embeddings = cls.embedding_model.encode(cls.texts)
        print(
            f"Index built, shape: {cls.embeddings.shape} "
            f"(elapsed {time.perf_counter() - index_start:.2f}s)"
        )

    def _search_top_n(
        self,
        query_embedding: np.ndarray,
        entries: list[dict[str, Any]],
        embeddings: np.ndarray,
        top_n: int = TOP_N,
    ) -> list[Candidate]:
        if embeddings is None or not entries:
            return []

        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        corpus_norm = embeddings / (
            np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
        )
        similarities = corpus_norm @ query_norm
        top_indices = np.argsort(similarities)[::-1][:top_n]

        candidates: list[Candidate] = []
        for idx in top_indices:
            score = float(similarities[idx])
            entry = entries[idx]
            candidates.append(
                Candidate(
                    entity_id=entry.get("device_id", ""),
                    entity_kind="device",
                    capability_id=entry.get("capability_id"),
                    vector_score=score,
                    total_score=score,
                    reasons=["semantic_match"],
                )
            )
        return candidates

    def _top_capability_ids(
        self, candidates: list[Candidate], top_n: int
    ) -> list[str]:
        ranked = sorted(candidates, key=lambda cand: cand.total_score, reverse=True)
        result: list[str] = []
        seen = set()
        for cand in ranked:
            cap_id = cand.capability_id
            if not isinstance(cap_id, str) or not cap_id:
                continue
            if cap_id in seen:
                continue
            seen.add(cap_id)
            result.append(cap_id)
            if len(result) >= top_n:
                break
        return result

    def test_embedding_recall_rate(self):
        """Validate embedding recall using LLM action text."""
        _log_progress("\n[Embedding] start...")
        total = 0
        hits = 0
        results = []

        cases = [c for c in self.queries if c.get("expected_capability_ids")]
        for idx, case in enumerate(cases, start=1):
            query = case["query"]
            expected_cap_ids = case.get("expected_capability_ids", [])
            if not expected_cap_ids:
                continue

            total += 1
            try:
                llm_start = time.perf_counter()
                ir = self.llm.parse(query)
                llm_cost = time.perf_counter() - llm_start

                action_text = ir.get("action", "")
                type_hint = ir.get("type_hint")
                scope_include = ir.get("scope_include", [])

                search_text = action_text if action_text else query

                search_start = time.perf_counter()
                query_embedding = self.embedding_model.encode([search_text])[0]

                mapped_category = map_type_to_category(type_hint)
                gated_devices = (
                    filter_by_category(self.devices, mapped_category)
                    if mapped_category
                    else self.devices
                )
                gated_device_ids = {device.id for device in gated_devices}
                gated_entries, gated_embeddings = select_entries_by_device_ids(
                    self.entries, self.embeddings, gated_device_ids
                )

                candidates = self._search_top_n(
                    query_embedding,
                    gated_entries,
                    gated_embeddings,
                    TOP_N,
                )
                scope_set = {
                    name for name in scope_include if isinstance(name, str) and name
                }
                candidates = apply_room_bonus(candidates, self.devices_by_id, scope_set)
                search_cost = time.perf_counter() - search_start

                top_cap_ids = self._top_capability_ids(candidates, TOP_N)
                hit = any(cap_id in top_cap_ids for cap_id in expected_cap_ids)

                if hit:
                    hits += 1
                    results.append((query, "HIT", expected_cap_ids, top_cap_ids[:3]))
                else:
                    results.append((query, "MISS", expected_cap_ids, top_cap_ids[:3]))

                _log_progress(
                    f"[Embedding] {idx}/{len(cases)} {results[-1][1]} llm={llm_cost:.2f}s "
                    f"embed+search={search_cost:.2f}s query={_short_text(query)} "
                    f"search_text={_short_text(search_text)}"
                )
                time.sleep(0.1)

            except Exception as exc:
                results.append((query, "ERROR", expected_cap_ids, []))
                _log_progress(
                    f"[Embedding] {idx}/{len(cases)} error query={_short_text(query)} err={exc}"
                )

        hit_rate = hits / total if total > 0 else 0

        print(f"\n=== Embedding recall summary (top-{TOP_N}) ===")
        print(f"total cases: {total}")
        print(f"hits: {hits}")
        print(f"hit rate: {hit_rate:.2%}")

        missed = [r for r in results if r[1] == "MISS"]
        if missed:
            print(f"\nMissed cases ({len(missed)}):")
            for query, _, expected, actual_top3 in missed[:10]:
                print(f"  query: {query}")
                print(f"    expected: {expected}")
                print(f"    top-3: {actual_top3}")

        self.assertGreaterEqual(
            hit_rate,
            0.6,
            f"top-{TOP_N} hit rate should be >= 60%, got {hit_rate:.2%}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
