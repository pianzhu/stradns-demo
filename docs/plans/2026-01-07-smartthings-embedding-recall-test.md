# SmartThings-style DashScope Integration Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 使用 README 中的 SmartThings 数据格式构造虚拟设备数据，并结合 spec.jsonl 构建富化命令语料；在集成测试中用真实 DashScope LLM 与 embedding 计算召回率，并对比基线与增强方案（category gating + room bonus）的提升。

**Architecture:** 测试启动时加载虚拟 rooms/devices 负载，构建 roomId->roomName 映射并生成 Device 列表（包含 profile_id、category、room）。使用 spec.jsonl 生成命令级富化语料并向量化，同时构建 baseline 语料（description + value_list）。查询时通过 DashScope LLM 生成 QueryIR，增强路径执行 category gating 与 room bonus，基线路径不做 gating/bonus；输出两者召回率与 delta。

**Tech Stack:** Python 3.13, unittest, dashscope, numpy

---

### Task 1: Add SmartThings fixture parsing helpers

**Files:**
- Modify: `tests/test_dashscope_integration.py`

**Step 1: Write the failing tests**

```python
class TestSmartThingsParsing(unittest.TestCase):
    def test_parse_room_map(self):
        payload = {
            "items": [
                {"roomId": "r1", "name": "Living"},
                {"roomId": "r2", "name": "Bedroom"},
            ]
        }
        room_map = _parse_room_map(payload)
        self.assertEqual(room_map, {"r1": "Living", "r2": "Bedroom"})

    def test_build_devices_from_items(self):
        room_map = {"r1": "Living"}
        items = [
            {
                "deviceId": "d1",
                "label": "Lamp",
                "roomId": "r1",
                "components": [{"categories": [{"name": "Light"}]}],
                "profile": {"id": "p1"},
            }
        ]
        devices = build_devices_from_items(items, room_map)
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device.id, "d1")
        self.assertEqual(device.name, "Lamp")
        self.assertEqual(device.room, "Living")
        self.assertEqual(device.type, "Light")
        self.assertEqual(getattr(device, "profile_id"), "p1")
        self.assertEqual(getattr(device, "category"), "Light")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestSmartThingsParsing -v`
Expected: FAIL because `_parse_room_map` and `build_devices_from_items` are missing

**Step 3: Write minimal implementation**

```python
def _parse_room_map(payload: dict[str, Any]) -> dict[str, str]:
    room_map: dict[str, str] = {}
    for item in payload.get("items", []):
        room_id = item.get("roomId")
        name = item.get("name")
        if isinstance(room_id, str) and isinstance(name, str) and room_id and name:
            room_map[room_id] = name
    return room_map


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
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestSmartThingsParsing -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dashscope_integration.py
git commit -m "test: add smartthings fixture parsing"
```

---

### Task 2: Build corpora helpers and entry selection

**Files:**
- Modify: `tests/test_dashscope_integration.py`

**Step 1: Write the failing tests**

```python
def test_build_command_corpus_with_spec_index(self):
    device = Device(id="d1", name="Lamp", room="Living", type="Light")
    setattr(device, "profile_id", "p1")
    setattr(device, "category", "Light")
    spec_index = {"p1": [CapabilityDoc(id="cap-on", description="enable", value_descriptions=["high"])]}
    entries, texts = build_command_corpus([device], spec_index)
    self.assertEqual(entries[0]["capability_id"], "cap-on")
    self.assertIn("enable", texts[0])


def test_filter_queries_by_available_capabilities(self):
    queries = [{"expected_capability_ids": ["cap-a"]}, {"expected_capability_ids": ["cap-b"]}]
    available = {"cap-b"}
    filtered = filter_queries_by_capabilities(queries, available)
    self.assertEqual(len(filtered), 1)


def test_select_entries_by_device_ids(self):
    entries = [
        {"device_id": "d1", "capability_id": "cap-a"},
        {"device_id": "d2", "capability_id": "cap-b"},
    ]
    embeddings = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    filtered_entries, filtered_embeddings = select_entries_by_device_ids(
        entries, embeddings, {"d2"}
    )
    self.assertEqual(len(filtered_entries), 1)
    self.assertEqual(filtered_entries[0]["device_id"], "d2")
    self.assertEqual(filtered_embeddings.shape[0], 1)
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestSmartThingsParsing.test_build_command_corpus_with_spec_index -v`
Expected: FAIL because helpers are missing

**Step 3: Write minimal implementation**

```python
def build_command_corpus(
    devices: list[Device],
    spec_index: dict[str, list[CapabilityDoc]],
) -> tuple[list[dict[str, str | None]], list[str]]:
    entries: list[dict[str, str | None]] = []
    texts: list[str] = []
    for device in devices:
        profile_id = getattr(device, "profile_id", None) or getattr(device, "profileId", None)
        spec_docs = spec_index.get(profile_id) if profile_id else None
        docs = build_enriched_doc(device, spec_index)
        if spec_docs and len(docs) == len(spec_docs):
            for doc, spec_doc in zip(docs, spec_docs):
                entries.append({
                    "device_id": device.id,
                    "capability_id": spec_doc.id,
                    "category": getattr(device, "category", None),
                    "room": device.room,
                })
                texts.append(doc)
        else:
            for doc in docs:
                entries.append({
                    "device_id": device.id,
                    "capability_id": None,
                    "category": getattr(device, "category", None),
                    "room": device.room,
                })
                texts.append(doc)
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
    indices = [idx for idx, entry in enumerate(entries) if entry.get("device_id") in device_ids]
    if not indices:
        return entries, embeddings
    filtered_embeddings = embeddings[indices]
    filtered_entries = [entries[idx] for idx in indices]
    return filtered_entries, filtered_embeddings
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestSmartThingsParsing.test_build_command_corpus_with_spec_index -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dashscope_integration.py
git commit -m "test: add corpus helpers and entry selection"
```

---

### Task 3: Wire fixtures into embedding integration flow

**Files:**
- Modify: `tests/test_dashscope_integration.py`

**Step 1: Write the failing test**

```python
def test_apply_room_bonus_respects_scope_include(self):
    devices = {"d1": Device(id="d1", name="Lamp", room="Living", type="Light")}
    candidates = [Candidate(entity_id="d1", total_score=0.5)]
    boosted = apply_room_bonus(candidates, devices, {"Living"})
    self.assertGreater(boosted[0].total_score, 0.5)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestSmartThingsParsing.test_apply_room_bonus_respects_scope_include -v`
Expected: FAIL because `apply_room_bonus` is not imported

**Step 3: Write minimal implementation**

```python
from context_retrieval.category_gating import map_type_to_category, filter_by_category
from context_retrieval.doc_enrichment import CapabilityDoc, build_enriched_doc, load_spec_index
from context_retrieval.scoring import apply_room_bonus
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestSmartThingsParsing.test_apply_room_bonus_respects_scope_include -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dashscope_integration.py
git commit -m "test: use room bonus in embedding integration"
```

---

### Task 4: Update embedding integration implementation

**Files:**
- Modify: `tests/test_dashscope_integration.py`

**Step 1: Write the failing test**

Run: `RUN_DASHSCOPE_IT=1 DASHSCOPE_API_KEY=xxx PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopeEmbeddingIntegration.test_embedding_recall_with_action_text -v`
Expected: FAIL because the integration flow still uses spec.jsonl only and does not apply SmartThings fixtures, gating, or room bonus

**Step 2: Write minimal implementation**

```python
# In setUpClass:
# 1) load spec index
# 2) load fixture rooms/devices payload
# 3) build devices + device map
# 4) build enriched corpus entries/texts + embeddings
# 5) build baseline texts + embeddings
# 6) filter queries by available capability ids
```

```python
# In test_embedding_recall_with_action_text:
# - compute query embedding from action (fallback to raw)
# - if type_hint maps to category -> filter devices and select entries/embeddings
# - search by cosine similarity to get candidates
# - apply_room_bonus and re-sort
# - compute hit rate for enhanced vs baseline (no gating/bonus)
```

**Step 3: Run test to verify it passes**

Run: `RUN_DASHSCOPE_IT=1 DASHSCOPE_API_KEY=xxx PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopeEmbeddingIntegration.test_embedding_recall_with_action_text -v`
Expected: PASS with printed baseline/enhanced hit rates and delta

**Step 4: Commit**

```bash
git add tests/test_dashscope_integration.py
git commit -m "test: use smartthings fixtures in embedding recall"
```

---

### Task 5: Update README with simulated SmartThings data usage

**Files:**
- Modify: `tests/README_dashscope_integration.md`

**Step 1: Update documentation**

Add a note that SmartThings device data is simulated from README format and no SmartThings token is required for these tests. Keep DashScope requirements unchanged.

**Step 2: Commit**

```bash
git add tests/README_dashscope_integration.md
git commit -m "docs: describe smartthings fixture usage"
```
