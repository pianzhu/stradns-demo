# Improve Embedding Recall Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不改变 QueryIR 接口的前提下，完成命令级向量检索的 pipeline 集成，并补齐 category gating、fallback 权重、room bonus、日志与 DashScope 集成测试更新。

**Architecture:** 先补齐运行依赖与命令级评分合并逻辑，再逐步把 category gating 与 room bonus 接入 pipeline；随后更新 DashScope 集成测试的命令文本构建方式，并补充可观测性与文档。

**Tech Stack:** Python 3.13, unittest, uv, dashscope, numpy, rapidfuzz, PyYAML

### Task 0: Add runtime dependencies for vector search

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Step 1: Run the failing test (baseline)**

Run: `PYTHONPATH=src uv run python -m unittest discover -s tests -p "test*.py" -v`
Expected: FAIL with `ModuleNotFoundError` for `numpy`, `rapidfuzz`, or `yaml`

**Step 2: Add missing dependencies**

Run: `uv add numpy pyyaml rapidfuzz`
Expected: `pyproject.toml` and `uv.lock` updated

**Step 3: Re-run baseline tests**

Run: `PYTHONPATH=src uv run python -m unittest discover -s tests -p "test*.py" -v`
Expected: Import errors resolved (other tests may still fail)

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add runtime deps for vector search"
```

### Task 1: Merge command-level candidates in scoring

**Files:**
- Modify: `src/context_retrieval/scoring.py`
- Modify: `tests/test_scoring.py`

**Step 1: Write the failing test**

```python
def test_merge_with_capability_ids_applies_keyword_score(self):
    keyword = [
        Candidate(entity_id="lamp-1", keyword_score=0.8, reasons=["name_exact"])
    ]
    vector = [
        Candidate(
            entity_id="lamp-1",
            capability_id="cap-on",
            vector_score=0.6,
            reasons=["semantic_match"],
        ),
        Candidate(
            entity_id="lamp-1",
            capability_id="cap-off",
            vector_score=0.4,
            reasons=["semantic_match"],
        ),
    ]

    merged = merge_and_score(keyword, vector, w_keyword=1.0, w_vector=0.5)

    self.assertEqual({c.capability_id for c in merged}, {"cap-on", "cap-off"})
    self.assertTrue(all(c.keyword_score == 0.8 for c in merged))
    self.assertTrue(all(c.capability_id is not None for c in merged))
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run python -m unittest tests.test_scoring.TestMergeAndScore.test_merge_with_capability_ids_applies_keyword_score -v`
Expected: FAIL because merge ignores `capability_id`

**Step 3: Write minimal implementation**

```python
# src/context_retrieval/scoring.py

def merge_and_score(...):
    keyword_by_entity = {c.entity_id: c for c in keyword_candidates}
    vector_by_key = {(c.entity_id, c.capability_id): c for c in vector_candidates}

    merged = []
    seen_entities = set()

    for (entity_id, capability_id), vec_cand in vector_by_key.items():
        kw_cand = keyword_by_entity.get(entity_id)
        keyword_score = kw_cand.keyword_score if kw_cand else 0.0
        vector_score = vec_cand.vector_score
        total_score = keyword_score * w_keyword + vector_score * w_vector

        reasons = []
        if kw_cand:
            reasons.extend(kw_cand.reasons)
        for r in vec_cand.reasons:
            if r not in reasons:
                reasons.append(r)

        merged.append(
            Candidate(
                entity_id=entity_id,
                entity_kind=vec_cand.entity_kind,
                capability_id=capability_id,
                keyword_score=keyword_score,
                vector_score=vector_score,
                total_score=total_score,
                reasons=reasons,
            )
        )
        seen_entities.add(entity_id)

    for entity_id, kw_cand in keyword_by_entity.items():
        if entity_id in seen_entities:
            continue
        merged.append(
            Candidate(
                entity_id=entity_id,
                entity_kind=kw_cand.entity_kind,
                capability_id=None,
                keyword_score=kw_cand.keyword_score,
                vector_score=0.0,
                total_score=kw_cand.keyword_score * w_keyword,
                reasons=list(kw_cand.reasons),
            )
        )

    merged.sort(key=lambda c: c.total_score, reverse=True)
    return merged
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run python -m unittest tests.test_scoring.TestMergeAndScore.test_merge_with_capability_ids_applies_keyword_score -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/context_retrieval/scoring.py tests/test_scoring.py
git commit -m "refactor: merge command-level candidates"
```

### Task 2: Convert scope_include to a scoring bonus

**Files:**
- Modify: `src/context_retrieval/logic.py`
- Modify: `src/context_retrieval/scoring.py`
- Modify: `src/context_retrieval/pipeline.py`
- Modify: `tests/test_logic.py`
- Modify: `tests/test_scoring.py`
- Modify: `tests/test_pipeline.py`

**Step 1: Write the failing tests**

```python
# tests/test_logic.py

def test_include_single_room_does_not_filter(self):
    ir = QueryIR(raw="turn on living room light", scope_include={"Living"})
    result = apply_scope_filters(self.all_devices, ir)
    self.assertEqual({d.id for d in result}, {"lamp-1", "lamp-2", "lamp-3"})

# tests/test_scoring.py

def test_room_bonus_applied(self):
    candidates = [Candidate(entity_id="lamp-1", total_score=0.5)]
    devices = {"lamp-1": Device(id="lamp-1", name="Lamp", room="Living", type="light")}

    boosted = apply_room_bonus(candidates, devices, {"Living"})

    self.assertGreater(boosted[0].total_score, 0.5)
    self.assertIn("room_bonus", boosted[0].reasons)

# tests/test_pipeline.py

def test_retrieve_does_not_drop_scope_include_devices(self):
    result = retrieve(
        text="turn off bedroom light",
        devices=self.devices,
        llm=self.llm,
        state=self.state,
    )
    candidate_ids = {c.entity_id for c in result.candidates}
    self.assertIn("lamp-1", candidate_ids)
    self.assertIn("lamp-2", candidate_ids)
```

**Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src uv run python -m unittest tests.test_logic.TestApplyScopeFilters.test_include_single_room_does_not_filter -v`
- `PYTHONPATH=src uv run python -m unittest tests.test_scoring.TestMergeAndScore.test_room_bonus_applied -v`
- `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_retrieve_does_not_drop_scope_include_devices -v`

Expected: FAIL due to scope include filtering and missing `apply_room_bonus`

**Step 3: Write minimal implementation**

```python
# src/context_retrieval/logic.py

def apply_scope_filters(devices: list[Device], ir: QueryIR) -> list[Device]:
    result = devices
    if ir.scope_exclude:
        result = [d for d in result if d.room not in ir.scope_exclude]
    return result
```

```python
# src/context_retrieval/scoring.py

ROOM_MATCH_BONUS = 0.2


def apply_room_bonus(
    candidates: list[Candidate],
    devices: dict[str, Device],
    scope_include: set[str],
    bonus: float = ROOM_MATCH_BONUS,
) -> list[Candidate]:
    if not candidates or not scope_include:
        return candidates

    boosted = []
    for cand in candidates:
        device = devices.get(cand.entity_id)
        if device and device.room in scope_include:
            reasons = list(cand.reasons)
            if "room_bonus" not in reasons:
                reasons.append("room_bonus")
            boosted.append(
                Candidate(
                    entity_id=cand.entity_id,
                    entity_kind=cand.entity_kind,
                    capability_id=cand.capability_id,
                    keyword_score=cand.keyword_score,
                    vector_score=cand.vector_score,
                    total_score=cand.total_score + bonus,
                    reasons=reasons,
                )
            )
        else:
            boosted.append(cand)
    return boosted
```

```python
# src/context_retrieval/pipeline.py

merged = merge_and_score(...)
merged = apply_room_bonus(merged, {d.id: d for d in filtered_devices}, ir.scope_include)
```

**Step 4: Run tests to verify they pass**

Run:
- `PYTHONPATH=src uv run python -m unittest tests.test_logic.TestApplyScopeFilters.test_include_single_room_does_not_filter -v`
- `PYTHONPATH=src uv run python -m unittest tests.test_scoring.TestMergeAndScore.test_room_bonus_applied -v`
- `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_retrieve_does_not_drop_scope_include_devices -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/context_retrieval/logic.py src/context_retrieval/scoring.py src/context_retrieval/pipeline.py tests/test_logic.py tests/test_scoring.py tests/test_pipeline.py
git commit -m "feat: apply scope include as score bonus"
```

### Task 3: Add category gating and fallback weights

**Files:**
- Modify: `src/context_retrieval/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Step 1: Write the failing tests**

```python
from unittest import mock
from context_retrieval.category_gating import map_type_to_category

class RecordingVectorSearcher(StubVectorSearcher):
    def __init__(self):
        super().__init__({})
        self.indexed_ids = []

    def index(self, devices):
        self.indexed_ids = [d.id for d in devices]


def test_retrieve_applies_category_gating(self):
    devices = [
        Device(id="lamp-1", name="Lamp", room="Living", type="light"),
        Device(id="ac-1", name="AC", room="Living", type="airConditioner"),
    ]
    llm = FakeLLM({"turn on light": {"action": "turn on", "type_hint": "light"}})
    recorder = RecordingVectorSearcher()

    result = retrieve(
        text="turn on light",
        devices=devices,
        llm=llm,
        state=ConversationState(),
        vector_searcher=recorder,
    )

    self.assertEqual(recorder.indexed_ids, ["lamp-1"])
    self.assertTrue(all(c.entity_id == "lamp-1" for c in result.candidates))


def test_retrieve_fallback_weights_without_type_hint(self):
    llm = FakeLLM({"turn on device": {"action": "turn on"}})
    with mock.patch("context_retrieval.pipeline.merge_and_score") as merge_mock:
        merge_mock.return_value = []
        retrieve(
            text="turn on device",
            devices=self.devices,
            llm=llm,
            state=self.state,
        )
        _, kwargs = merge_mock.call_args
        self.assertEqual(kwargs["w_keyword"], 1.2)
        self.assertEqual(kwargs["w_vector"], 0.2)
```

**Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_retrieve_applies_category_gating -v`
- `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_retrieve_fallback_weights_without_type_hint -v`

Expected: FAIL because gating/weights are not applied

**Step 3: Write minimal implementation**

```python
# src/context_retrieval/pipeline.py
import logging
from context_retrieval.category_gating import map_type_to_category, filter_by_category

DEFAULT_KEYWORD_WEIGHT = 1.0
DEFAULT_VECTOR_WEIGHT = 0.3
FALLBACK_KEYWORD_WEIGHT = 1.2
FALLBACK_VECTOR_WEIGHT = 0.2

logger = logging.getLogger(__name__)

# ... inside retrieve()
filtered_devices = apply_scope_filters(devices, ir)

mapped_category = map_type_to_category(ir.type_hint)
if mapped_category:
    gated_devices = filter_by_category(filtered_devices, mapped_category)
else:
    gated_devices = filtered_devices

w_keyword = DEFAULT_KEYWORD_WEIGHT
w_vector = DEFAULT_VECTOR_WEIGHT
if not mapped_category:
    w_keyword = FALLBACK_KEYWORD_WEIGHT
    w_vector = FALLBACK_VECTOR_WEIGHT

# keyword + vector search use gated_devices
searcher = KeywordSearcher(gated_devices)
keyword_candidates = searcher.search(ir)
if vector_searcher:
    vector_searcher.index(gated_devices)
    vector_candidates = vector_searcher.search(search_text, top_k=top_k)

merged = merge_and_score(
    keyword_candidates,
    vector_candidates=vector_candidates,
    w_keyword=w_keyword,
    w_vector=w_vector,
)
```

**Step 4: Run tests to verify they pass**

Run:
- `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_retrieve_applies_category_gating -v`
- `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_retrieve_fallback_weights_without_type_hint -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/context_retrieval/pipeline.py tests/test_pipeline.py
git commit -m "feat: add category gating and fallback weights"
```

### Task 4: Update DashScope capability text builder

**Files:**
- Modify: `tests/test_dashscope_integration.py`

**Step 1: Write the failing test**

```python
class TestCapabilityTextBuilder(unittest.TestCase):
    def test_build_enriched_capability_text(self):
        cap = {
            "id": "cap-on",
            "description": "enable",
            "value_list": [
                {"value": "high", "description": "high"},
            ],
        }
        text = build_enriched_capability_text(cap)
        self.assertIn("cap-on", text)
        self.assertIn("enable", text)
        self.assertIn("turn on", text)
        self.assertIn("high", text)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run python -m unittest tests.test_dashscope_integration.TestCapabilityTextBuilder.test_build_enriched_capability_text -v`
Expected: FAIL because `build_enriched_capability_text` is missing

**Step 3: Write minimal implementation**

```python
from context_retrieval.doc_enrichment import enrich_description


def build_enriched_capability_text(cap: dict[str, Any]) -> str:
    cap_id = cap.get("id", "")
    description = cap.get("description", "")
    enriched_desc = enrich_description(description)
    parts = [cap_id]
    if enriched_desc:
        parts.append(enriched_desc)

    value_list = cap.get("value_list") or []
    for item in value_list:
        if isinstance(item, dict):
            value_desc = item.get("description")
            if isinstance(value_desc, str) and value_desc.strip():
                parts.append(value_desc.strip())

    return " ".join(p for p in parts if p)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run python -m unittest tests.test_dashscope_integration.TestCapabilityTextBuilder.test_build_enriched_capability_text -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dashscope_integration.py
git commit -m "test: enrich dashscope capability texts"
```

### Task 5: Add pipeline debug logging

**Files:**
- Modify: `src/context_retrieval/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Step 1: Write the failing test**

```python
import logging


def test_pipeline_logs_gating_and_scores(self):
    llm = FakeLLM({"turn on light": {"action": "turn on", "type_hint": "light"}})
    with self.assertLogs("context_retrieval.pipeline", level=logging.INFO) as ctx:
        retrieve(
            text="turn on light",
            devices=self.devices,
            llm=llm,
            state=self.state,
        )
    joined = "\n".join(ctx.output)
    self.assertIn("mapped_category=Light", joined)
    self.assertIn("gating_before=", joined)
    self.assertIn("gating_after=", joined)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_pipeline_logs_gating_and_scores -v`
Expected: FAIL because logs are missing

**Step 3: Write minimal implementation**

```python
# src/context_retrieval/pipeline.py
logger.info(
    "mapped_category=%s type_hint=%s",
    mapped_category,
    ir.type_hint,
)
logger.info(
    "gating_before=%s gating_after=%s",
    len(filtered_devices),
    len(gated_devices),
)

if merged:
    top_preview = [
        f"{c.entity_id}:{c.capability_id}:{c.total_score:.3f}" for c in merged[:5]
    ]
    logger.info("top_candidates=%s", ",".join(top_preview))
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run python -m unittest tests.test_pipeline.TestRetrieve.test_pipeline_logs_gating_and_scores -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/context_retrieval/pipeline.py tests/test_pipeline.py
git commit -m "feat: add pipeline debug logs"
```

### Task 6: Update DashScope integration README

**Files:**
- Modify: `tests/README_dashscope_integration.md`

**Step 1: Update documentation**

- Update embedding section to state capability text includes synonyms and value_list descriptions.
- Mention category is included when available from device metadata.

**Step 2: Commit**

```bash
git add tests/README_dashscope_integration.md
git commit -m "docs: update dashscope integration notes"
```

### Task 7: Update OpenSpec task checklist

**Files:**
- Modify: `openspec/changes/improve-embedding-recall/tasks.md`

**Step 1: Mark completed tasks**

- Mark 1.1, 1.2, 2.1, 2.2, 3.1-3.4, 4.1-4.3, 5.1-5.2 as completed once done.

**Step 2: Commit**

```bash
git add openspec/changes/improve-embedding-recall/tasks.md
git commit -m "docs: update improve-embedding-recall task status"
```
