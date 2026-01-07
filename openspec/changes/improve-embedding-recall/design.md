# 设计文档：改进 Embedding 召回率

## 上下文

### 问题现状

集成测试显示 embedding 召回率仅 40%（目标 ≥90%）。典型失败案例：

| 用户查询 | LLM action | 期望命令 | 实际 top-1 |
|---------|-----------|---------|-----------|
| 打开客厅的灯 | `open` | `main-switch-on` | `main-windowShade-open` |
| 把灯光调到50% | `adjust` | `main-switchLevel-setLevel` | `main-windowShadeTiltLevel-setShadeTiltLevel` |

**根因**：泛化动词 + 无类型区分 + 短文本相似度退化。

### 数据源

1. **SmartThings API**：`GET /v1/devices?locationId=...`
   - 返回 `items[].components[].categories[].name`：设备类别（Light/Blind/AirConditioner/...）
   - 返回 `items[].profile.id`：关联 spec.jsonl 的 profileId
   具体数据参考README

2. **spec.jsonl**：本地规范文件
   - 结构：`{profileId, capabilities: [{id, description, type, value_range}]}`
   - 用途：为每个 capability 提供中文语义描述

## 目标 / 非目标

### 目标

- 将 top-10 召回命中率从 40% 提升到 ≥ 90%
- 保持现有 QueryIR 接口兼容
- 不增加 LLM 调用次数

### 非目标

- 不引入 `type_hint` 同义词映射表（由 LLM 直接输出 canonical category）
- 不支持多 component 设备（当前仅处理 `main` component）
- 不处理跨 category 的模糊命令

## 决策

### 决策 1：双通道检索架构

```
User query
    ↓
LLM parse → QueryIR (action, type_hint, name_hint, scope_include...)
    ↓
┌─────────────────────────────────────────────────────────────┐
│  Is type_hint a valid category (and not Unknown)?            │
│    ├─ Yes → Category gating → filtered set → embedding search │
│    │                                                         │
│    └─ No  → Keyword-first (name + room)                       │
└─────────────────────────────────────────────────────────────┘
    ↓
Merge ranking → Top-K
```

**理由**：
- `type_hint != Unknown` → 用户更可能在描述设备类型，category gating 有效
- `type_hint` 缺失/非法或为 `Unknown` → 用户更可能在使用自定义名称，名称匹配更有效

### 决策 2：type_hint 输出约束为 categories

在 system prompt 中显式列举所有合法 categories，并要求 `type_hint` 必须从该集合中选择；无法判断时输出 `Unknown`。

```python
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
```

**考虑的替代方案**：
- 维护 `type_hint` 同义词映射表 → 多语言与同义词会持续扩张，维护成本高且不可控
- 通过 embedding 相似度推断 type_hint → 引入额外计算与不确定性

**选择理由**：由 LLM 直接输出 canonical category，将语言/同义词问题收敛到 prompt；代码侧只做归一化与合法性校验。

### 决策 3：文档富化策略

**当前文档**：
```
device_name room type cmd_desc1 cmd_desc2 ...
```

**富化后文档**（按命令粒度，纯语义描述）：
```
{description} {synonyms} {value_descriptions}
```

> **设计决策**：不在文档中包含 `category` 和 `capability_id`。中英混合文本会干扰 embedding 模型的语义理解，降低向量化准确度。

**示例**：
```
# Original
电源启用

# Enriched
电源启用 打开 开 开启 启动 on
```

**同义词扩展表**（示例，实际可按数据分布扩展）：
```python
VERB_SYNONYMS = {
    "enable": ["turn on", "on", "start"],
    "disable": ["turn off", "off", "stop"],
    "set": ["adjust", "change", "configure"],
}
```

**带参数命令的处理**（`value_list`）：

spec.jsonl 中部分命令包含 `value_list`，参数描述也携带重要语义：

```json
{
  "id": "main-airConditionerMode-setAirConditionerMode",
  "description": "set air conditioner mode",
  "value_list": [
    {"value": "cooling", "description": "cool"},
    {"value": "heating", "description": "heat"}
  ]
}
```

**策略**：将 `value_list` 中的所有参数描述拼接到命令文档中：

```python
def build_doc_with_values(cap: dict) -> str:
    parts = [cap["description"]]  # "set air conditioner mode"
    if "value_list" in cap:
        for v in cap["value_list"]:
            parts.append(v["description"])  # "cool", "heat", ...
    return " ".join(parts)

# Result: "set air conditioner mode cool heat"
```

**理由**：
- 用户说"空调制冷"时，"制冷"能匹配到文档
- 避免为每个参数值生成独立向量（索引膨胀）
- 当前规模下（value_list 通常 <10 项）拼接不会稀释语义
- 不依赖 LLM 输出稳定性，查询任意表达都有机会命中

### 决策 4：索引粒度

**选择**：命令级索引（而非设备级）

```
# Device-level (current)
device_id → embedding([name, room, type, cmd1_desc, cmd2_desc, ...])

# Command-level (new)
(device_id, capability_id) → embedding([description, synonyms, value_descriptions])
```

> **注意**：`capability_id` 仅作为索引键，不参与 embedding 文本构建。

**理由**：
- 命令级文档区分度更高
- 避免多命令描述混在一起稀释语义
- 检索结果直接对应具体命令
- 纯语义文本（无英文标识符）提升向量化准确度

### 决策 5：scope_include 作为评分加权（非硬过滤）

**问题**：设备自定义名称可能包含房间词（如"客厅老伙计"），若用 `scope_include` 做硬过滤会遗漏。

**决策**：`scope_include` 不作为预过滤条件，而是作为评分加权因素。

```python
# Incorrect: hard filter
devices = [d for d in devices if d.room in scope_include]  # may drop custom names

# Correct: score bonus
if device.room in scope_include:
    score += ROOM_MATCH_BONUS
```

**理由**：
- 避免因自定义名称中的房间词导致遗漏
- keyword 检索可通过名称模糊匹配召回这些设备
- 房间匹配仍能通过加权提升排名

### 决策 6：Fallback 策略

当 `type_hint` 缺失/非法或为 `Unknown` 时：

1. **不做 category gating**，保留全量候选集
2. **提升 keyword 权重**：优先使用 name/room 模糊匹配
3. 使用现有 `keyword_search.py` 的评分逻辑

**理由**：用户使用自定义名称时，名称本身是最强信号。

## 风险 / 权衡

| 风险 | 缓解措施 |
|------|----------|
| type_hint 输出不在合法集合 | prompt 约束 + 归一化校验 + fallback 保底 |
| 同义词表维护成本 | 初期聚焦高频动词，后续按需扩展 |
| 命令级索引存储量增加 | 当前设备规模（<1000）可接受 |
| category 与实际能力不匹配 | 以 spec.jsonl 为准，category 仅做初筛 |

## 模块设计

### 新增模块

```
src/context_retrieval/
├── category_gating.py      # Category gating
│   ├── ALLOWED_CATEGORIES  # Canonical categories
│   └── filter_by_category() # Filtering helper
│
└── doc_enrichment.py       # Document enrichment
    ├── VERB_SYNONYMS       # Synonym expansion
    ├── load_spec_index()   # spec.jsonl loader
    └── build_enriched_doc() # Doc builder
```

### 修改模块

```
pipeline.py
├── retrieve()
│   ├── [New] type_hint canonicalization + validation
│   ├── [New] type_hint != Unknown → category gating
│   ├── [New] Unknown/invalid → keyword-heavy fallback
│   └── [Existing] merge scoring

vector_search.py
├── DashScopeVectorSearcher  # Refactored: replaces InMemoryVectorSearcher + DashScopeEmbeddingModel
│   ├── __init__() accepts spec_index
│   ├── index() builds command-level corpus
│   ├── search() returns Candidate with capability_id
│   └── encode() for direct embedding access
├── StubVectorSearcher  # For testing
└── build_command_corpus()  # Shared corpus builder
```

### 数据流

```
At startup:
spec.jsonl → load_spec_index() → {profileId: [capability_docs]}
    ↓
devices + spec_index → build_enriched_docs() → corpus embeddings

At query time:
QueryIR.type_hint → normalize + validate → category
    ↓
category + devices → filter_by_category() → filtered_devices
    ↓
QueryIR.action → embedding → cosine_search(corpus) → candidates
```

## 待决问题

1. **spec.jsonl 加载时机**：启动时一次性加载 vs 懒加载？
   - 建议：启动时加载，当前规模可接受

2. **embedding 重建策略**：设备列表变化时如何更新？
   - 建议：首次查询时按需构建，缓存复用

3. **Device.category 字段**：
   - `Device.type` 字段已重命名为 `Device.category`，与 SmartThings API 和 category gating 逻辑保持一致
   - 测试/集成环境用 fixture 注入；生产环境应来自 SmartThings `components[].categories[].name`
