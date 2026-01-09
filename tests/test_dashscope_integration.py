"""DashScope integration tests.

Uses real DashScope API (qwen-flash + text-embedding-v4) to validate:
- LLM extraction accuracy
- Pipeline end-to-end retrieval behavior

Requirements:
- DASHSCOPE_API_KEY environment variable
- RUN_DASHSCOPE_IT=1 environment variable

Optional environment variables:
- DASHSCOPE_PIPELINE_TOP_K: pipeline top-k, default 5
- DASHSCOPE_MAX_QUERIES: max test cases, default unlimited
- DASHSCOPE_CMD_PARSER_MAX_CASES: max command parser cases, default unlimited
- DASHSCOPE_LLM_MODEL: LLM model name, default qwen-flash
- DASHSCOPE_EMBEDDING_MODEL: embedding model name, default text-embedding-v4
"""

import json
import os
import time
import unittest
from pathlib import Path
from typing import Any

from command_parser import CommandParserConfig, parse_command_output
from command_parser.prompt import DEFAULT_SYSTEM_PROMPT
from context_retrieval.doc_enrichment import load_spec_index
from context_retrieval.models import Device
from context_retrieval.pipeline import retrieve
from context_retrieval.state import ConversationState

# Progress logging toggle (default enabled; set to 0 to disable)
PROGRESS_ENABLED = os.getenv("DASHSCOPE_IT_PROGRESS", "1") != "0"

FIXTURE_DIR = Path(__file__).parent
QUERY_PATH = FIXTURE_DIR / "dashscope_integration_queries.json"
CMD_PARSER_CASES_PATH = FIXTURE_DIR / "dashscope_command_parser_cases.json"
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
        device = Device(id=device_id, name=name, room=room, category=device_type)
        profile_id = _extract_profile_id(item)
        if profile_id:
            setattr(device, "profile_id", profile_id)
        if category:
            setattr(device, "category", category)
        devices.append(device)
    return devices


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


def _device_profile_id(device: Device) -> str | None:
    profile_id = getattr(device, "profile_id", None) or getattr(device, "profileId", None)
    if isinstance(profile_id, str) and profile_id.strip():
        return profile_id.strip()
    return None


def _build_spec_lookup(spec_index: dict[str, list[Any]]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}
    for profile_id, docs in spec_index.items():
        lookup[profile_id] = {doc.id for doc in docs if getattr(doc, "id", None)}
    return lookup


def _supports(
    device: Device,
    capability_id: str,
    spec_lookup: dict[str, set[str]],
) -> bool:
    profile_id = _device_profile_id(device)
    if not profile_id:
        return False
    return capability_id in spec_lookup.get(profile_id, set())


# Skip switch
SKIP_REASON = None
if not os.getenv("RUN_DASHSCOPE_IT"):
    SKIP_REASON = "RUN_DASHSCOPE_IT=1 is required to enable DashScope integration tests"
elif not os.getenv("DASHSCOPE_API_KEY"):
    SKIP_REASON = "DASHSCOPE_API_KEY is required to enable DashScope integration tests"

# Configurable params
PIPELINE_TOP_K = int(os.getenv("DASHSCOPE_PIPELINE_TOP_K", "5"))
MAX_QUERIES = int(os.getenv("DASHSCOPE_MAX_QUERIES", "0")) or None
CMD_PARSER_MAX_CASES = int(os.getenv("DASHSCOPE_CMD_PARSER_MAX_CASES", "0")) or None
LLM_MODEL = os.getenv("DASHSCOPE_LLM_MODEL", "qwen-flash")
EMBEDDING_MODEL = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")


def load_test_queries() -> list[dict[str, Any]]:
    """Load test cases."""
    with open(QUERY_PATH, "r", encoding="utf-8") as handle:
        queries = json.load(handle)
    if MAX_QUERIES:
        queries = queries[:MAX_QUERIES]
    return queries


def load_command_parser_cases() -> list[dict[str, Any]]:
    """Load command parser integration cases."""
    with open(CMD_PARSER_CASES_PATH, "r", encoding="utf-8") as handle:
        cases = json.load(handle)
    if CMD_PARSER_MAX_CASES:
        cases = cases[:CMD_PARSER_MAX_CASES]
    return cases


def _matches_expected_fields(command, expected_fields: dict[str, Any]) -> bool:
    if not expected_fields:
        return True

    action = expected_fields.get("action")
    if isinstance(action, str) and action and command.action != action:
        return False

    expected_include = expected_fields.get("scope_include")
    if isinstance(expected_include, list) and expected_include:
        actual_include = set(command.scope.include)
        if not set(expected_include) <= actual_include:
            return False

    expected_exclude = expected_fields.get("scope_exclude")
    if isinstance(expected_exclude, list) and expected_exclude:
        actual_exclude = set(command.scope.exclude)
        if not set(expected_exclude) <= actual_exclude:
            return False

    target_name = expected_fields.get("target_name")
    if isinstance(target_name, str) and target_name and command.target.name != target_name:
        return False

    target_type = expected_fields.get("target_type")
    if isinstance(target_type, str) and target_type and command.target.type_hint != target_type:
        return False

    target_quantifier = expected_fields.get("target_quantifier")
    if (
        isinstance(target_quantifier, str)
        and target_quantifier
        and command.target.quantifier != target_quantifier
    ):
        return False

    return True


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
        """Validate (Chinese) action coverage and scope_include accuracy."""
        _log_progress("\n[LLM] start...")
        total = 0
        action_valid = 0
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
                if (
                    isinstance(action_text, str)
                    and action_text.strip()
                    and not any("A" <= ch <= "Z" or "a" <= ch <= "z" for ch in action_text)
                ):
                    action_valid += 1

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

        action_coverage = action_valid / total if total > 0 else 0
        scope_accuracy = scope_correct / scope_total if scope_total > 0 else 0

        print("\n=== LLM extraction summary ===")
        print(f"total cases: {total}")
        print(f"action coverage: {action_coverage:.2%} ({action_valid}/{total})")
        print(f"scope accuracy: {scope_accuracy:.2%} ({scope_correct}/{scope_total})")

        self.assertGreaterEqual(
            action_coverage, 0.6, f"action coverage should be >= 60%, got {action_coverage:.2%}"
        )
        if scope_total > 0:
            self.assertGreaterEqual(
                scope_accuracy, 0.6, f"scope accuracy should be >= 60%, got {scope_accuracy:.2%}"
            )


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopeCommandParserContract(unittest.TestCase):
    """DashScope command parser contract integration tests."""

    @classmethod
    def setUpClass(cls):
        """Initialize LLM client."""
        from context_retrieval.ir_compiler import DashScopeLLM

        start = time.perf_counter()
        cls.llm = DashScopeLLM(model=LLM_MODEL)
        cls.cases = load_command_parser_cases()
        _log_progress(
            f"[CmdParser] init done model={LLM_MODEL} cases={len(cls.cases)} "
            f"(DASHSCOPE_CMD_PARSER_MAX_CASES={CMD_PARSER_MAX_CASES or 'ALL'}) "
            f"elapsed={time.perf_counter() - start:.2f}s"
        )

    def test_command_parser_contract(self):
        """Validate LLM output is parsable and matches expected fields."""
        _log_progress("\n[CmdParser] start...")
        total = 0
        parsed_ok = 0
        matched = 0
        results = []

        for idx, case in enumerate(self.cases, start=1):
            query = case.get("query", "")
            expected_fields = case.get("expected_fields", {}) or {}

            total += 1
            try:
                call_start = time.perf_counter()
                raw_output = self.llm.generate_with_prompt(
                    query,
                    DEFAULT_SYSTEM_PROMPT,
                )
                call_cost = time.perf_counter() - call_start

                parsed = parse_command_output(
                    raw_output,
                    config=CommandParserConfig(),
                )

                if not parsed.is_unknown:
                    parsed_ok += 1

                hit = any(
                    _matches_expected_fields(cmd, expected_fields)
                    for cmd in parsed.commands
                )
                if hit:
                    matched += 1
                    status = "HIT"
                else:
                    status = "MISS"

                results.append((query, status, expected_fields, parsed.commands))
                _log_progress(
                    f"[CmdParser] {idx}/{len(self.cases)} {status} elapsed={call_cost:.2f}s "
                    f"query={_short_text(str(query))} commands={len(parsed.commands)}"
                )
                time.sleep(0.1)

            except Exception as exc:
                results.append((query, "ERROR", expected_fields, str(exc)))
                _log_progress(
                    f"[CmdParser] {idx}/{len(self.cases)} error query={_short_text(str(query))} "
                    f"err={exc}"
                )

        parsed_rate = parsed_ok / total if total > 0 else 0
        match_rate = matched / total if total > 0 else 0

        print("\n=== Command parser contract summary ===")
        print(f"total cases: {total}")
        print(f"parsed ok rate: {parsed_rate:.2%} ({parsed_ok}/{total})")
        print(f"match rate: {match_rate:.2%} ({matched}/{total})")

        misses = [r for r in results if r[1] == "MISS"]
        if misses:
            print(f"\nMissed cases ({len(misses)}):")
            for query, _, expected, parsed_cmds in misses[:10]:
                print(f"  query: {query}")
                print(f"    expected: {expected}")
                print(f"    parsed: {[cmd.raw for cmd in parsed_cmds]}")

        self.assertGreaterEqual(
            parsed_rate,
            0.6,
            f"parsed ok rate should be >= 60%, got {parsed_rate:.2%}",
        )
        self.assertGreaterEqual(
            match_rate,
            0.6,
            f"match rate should be >= 60%, got {match_rate:.2%}",
        )


@unittest.skipIf(SKIP_REASON, SKIP_REASON or "")
class TestDashScopePipelineRetrieve(unittest.TestCase):
    """DashScope pipeline end-to-end integration tests."""

    @classmethod
    def setUpClass(cls):
        """Initialize pipeline deps and build vector index."""
        import logging

        logging.basicConfig(level=logging.INFO)
        from context_retrieval.ir_compiler import DashScopeLLM
        from context_retrieval.vector_search import DashScopeVectorSearcher

        start = time.perf_counter()
        cls.llm = DashScopeLLM(model=LLM_MODEL)

        queries = load_test_queries()
        spec_path = Path(__file__).parent.parent / "src" / "spec.jsonl"
        spec_index = load_spec_index(str(spec_path))
        cls.spec_lookup = _build_spec_lookup(spec_index)

        room_map = load_room_map(ROOMS_PATH)
        device_items = load_jsonl(DEVICES_PATH)
        devices = build_devices_from_items(device_items, room_map)

        available_capabilities: set[str] = set()
        for device in devices:
            profile_id = _device_profile_id(device)
            if profile_id:
                available_capabilities |= cls.spec_lookup.get(profile_id, set())

        filtered_queries = filter_queries_by_capabilities(
            queries,
            available_capabilities,
        )  # type: ignore

        cls.devices = devices
        cls.devices_by_id = {device.id: device for device in devices}
        cls.queries = filtered_queries or queries

        cls.vector_searcher = DashScopeVectorSearcher(
            spec_index=spec_index,
            model=EMBEDDING_MODEL,
        )

        index_start = time.perf_counter()
        cls.vector_searcher.index(devices)
        _log_progress(
            f"[Pipeline] init done llm={LLM_MODEL} embedding={EMBEDDING_MODEL} "
            f"queries={len(cls.queries)} devices={len(cls.devices)} "
            f"index_elapsed={time.perf_counter() - index_start:.2f}s "
            f"elapsed={time.perf_counter() - start:.2f}s"
        )

    def test_pipeline_recall_rate(self):
        """Validate pipeline.retrieve() recall and output validity."""
        _log_progress("\n[Pipeline] start...")
        total = 0
        hits = 0
        option_hits = 0
        results = []

        cases = [c for c in self.queries if c.get("expected_capability_ids")]
        for idx, case in enumerate(cases, start=1):
            query = case["query"]
            expected_cap_ids = case.get("expected_capability_ids", [])
            expected_fields = case.get("expected_fields", {}) or {}
            expected_quantifier = expected_fields.get("quantifier")
            expect_bulk = expected_quantifier in {"all", "except"}
            if not expected_cap_ids:
                continue

            total += 1
            try:
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

                # 候选数量受控
                self.assertLessEqual(len(result.candidates), PIPELINE_TOP_K)

                # 结构有效性：device/group 引用必须可解析，且 capability_id 必须可映射
                group_by_id = {group.id: group for group in result.groups}
                if expect_bulk and result.hint not in {"need_clarification", "too_many_targets"}:
                    self.assertTrue(result.groups)
                    self.assertTrue(all(c.entity_kind == "group" for c in result.candidates))
                for cand in result.candidates:
                    cap_id = cand.capability_id
                    self.assertIsInstance(cap_id, str)
                    self.assertTrue(bool(cap_id))

                    if cand.entity_kind == "device":
                        device = self.devices_by_id.get(cand.entity_id)
                        self.assertIsNotNone(device)
                        self.assertTrue(_supports(device, cap_id, self.spec_lookup))  # type: ignore[arg-type]
                    elif cand.entity_kind == "group":
                        group = group_by_id.get(cand.entity_id)
                        self.assertIsNotNone(group)
                        for device_id in group.device_ids: # type: ignore
                            device = self.devices_by_id.get(device_id)
                            self.assertIsNotNone(device)
                            self.assertTrue(_supports(device, cap_id, self.spec_lookup))  # type: ignore[arg-type]
                    else:  # pragma: no cover
                        raise AssertionError(f"unexpected entity_kind: {cand.entity_kind}")

                top_cap_ids = [
                    cand.capability_id
                    for cand in result.candidates
                    if isinstance(cand.capability_id, str) and cand.capability_id
                ]

                hit = any(cap_id in top_cap_ids for cap_id in expected_cap_ids)
                option_hit = (
                    result.hint == "need_clarification"
                    and any(
                        opt.capability_id in expected_cap_ids
                        for opt in result.options
                    )
                )

                if hit:
                    hits += 1
                    results.append((query, "HIT", expected_cap_ids, top_cap_ids[:3], result.hint))
                elif option_hit:
                    option_hits += 1
                    results.append((query, "HIT_OPTION", expected_cap_ids, [opt.capability_id for opt in result.options], result.hint))
                else:
                    results.append((query, "MISS", expected_cap_ids, top_cap_ids[:3], result.hint))

                option_preview = ",".join(opt.capability_id for opt in result.options)
                _log_progress(
                    f"[Pipeline] {idx}/{len(cases)} {results[-1][1]} elapsed={call_cost:.2f}s "
                    f"query={_short_text(query)} hint={result.hint} "
                    f"expected={','.join(expected_cap_ids[:2])} "
                    f"top_caps={','.join(top_cap_ids[:3])} options={option_preview} "
                    f"candidates={len(result.candidates)} groups={len(result.groups)}"
                )
                time.sleep(0.1)

            except Exception as exc:
                results.append((query, "ERROR", expected_cap_ids, [], str(exc)))
                _log_progress(
                    f"[Pipeline] {idx}/{len(cases)} error query={_short_text(query)} err={exc}"
                )

        effective_hit_rate = (hits + option_hits) / total if total > 0 else 0

        print(f"\n=== Pipeline recall summary (top-{PIPELINE_TOP_K}) ===")
        print(f"total cases: {total}")
        print(f"hits: {hits}")
        print(f"hits (need_clarification options): {option_hits}")
        print(f"effective hit rate: {effective_hit_rate:.2%}")

        missed = [r for r in results if r[1] == "MISS"]
        if missed:
            print(f"\nMissed cases ({len(missed)}):")
            for query, _, expected, actual_top3, hint in missed[:10]:
                print(f"  query: {query}")
                print(f"    expected: {expected}")
                print(f"    top-3: {actual_top3} hint={hint}")

        self.assertGreaterEqual(
            effective_hit_rate,
            0.6,
            f"top-{PIPELINE_TOP_K} hit rate should be >= 60%, got {effective_hit_rate:.2%}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
