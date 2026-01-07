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

### 决策 2.1：action 输出中文并在英文时降级

当前 `DEFAULT_SYSTEM_PROMPT` 为英文描述，LLM 在中文 query 下可能返回英文 `action`（例如 "turn on"、"adjust"）。这会导致：

- `action` 与中文 query / 中文文档语料出现语言不一致，embedding 相似度排序退化
- 召回链路强依赖 `action` 时，出现可复现的误召回或漏召回

**决策**：

1. 在 system prompt 中明确约束：`action` 必须为中文意图短语（不包含英文字母），无法判断时省略或返回空值。
2. 增加代码侧校验：当 `action` 包含英文字母时视为无效，并降级为使用 `QueryIR.raw` 作为向量检索文本（同时记录调试日志）。

示例（仅表达规则，具体实现细节在 apply 阶段落地）：

```python
if action and re.search(r"[A-Za-z]", action):
    action = None
search_text = action or raw
```

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

### 决策 7：全链路验收以 pipeline 输出为准

此前集成测试更多验证 embedding 子路径，容易出现“测试通过但 pipeline 行为不一致”的情况（例如 scope 过滤顺序、融合评分、候选结构变化）。

**决策**：集成测试以 `pipeline.retrieve()` 的最终输出为准，覆盖：

- `scope_exclude` 预过滤 → category gating → keyword/vector 混合召回 → 融合评分 → top-k
- 输出有效性：候选必须能解析到真实设备信息（`device_id/name/room`）与有效 `CommandSpec`
- 逐用例关键日志：便于定位误召回/漏召回发生在哪个阶段

### 决策 8：量词（quantifier）与 Group 聚合（兼顾召回与爆炸防护）

目标拆分（与你的关注点对齐）：

- **检索召回质量（A）**：确保“all lights”能覆盖所有符合条件的灯设备，而不是仅返回 top-k 代表样本
- **候选数量控制（B）**：防止“all devices”等极端 query 导致候选集合爆炸
- **输出格式与行为（C）**：当匹配到多个设备时，以 group 作为可执行单位（同组设备具备一致命令集）

#### 8.1 Bulk mode 触发条件

当 `QueryIR.quantifier` 为 `all` 或 `except` 时进入 bulk mode；`one/any` 仍走现有 top-k 排序路径。

#### 8.2 “先选命令，再扩展集合”的原则

bulk mode 的核心思想：先确定“要执行的命令（capability_id）”，再扩展到“所有支持该命令的目标设备（targets）”，最后用 group 与 batch 压缩输出与执行。

注意：`targets` 的规模不应反向影响 `capability_id` 的选择；`targets` 仅用于后续分组与分片处理。

#### 8.3 capability_id 选择：聚合置信度 + 低置信度时 LLM 仲裁

capability_id 的选择优先使用“命令级向量召回”的证据（vector candidates 自带 capability_id），并对同一个 capability_id 的证据进行聚合：

- 构建 `top-N` 候选 capability 选项（`N=5`）
- 使用更大的候选窗口获取证据（例如 `OPTIONS_SEARCH_K=50~100`），避免 `top_k=5` 证据过少导致置信度虚高
- 为避免“支持设备数多 → 证据累计更高”的偏置，对每个 `capability_id` 仅保留 top-M 条证据参与聚合（例如 `M=3`）
- 对聚合得分进行归一化，得到分布 `p_i`
- 置信度判定使用两个指标（组合更稳）：
  - `top1_ratio = p1`
  - `margin = p1 - p2`

bulk mode 下还需要关注覆盖度：`coverage = supports(capability_id) / len(filtered_devices)`，用于检测“选中的命令无法覆盖全集”（避免 silent drop）。

当低置信度（`top1_ratio` 或 `margin` 低于阈值）时，需要二选一明确实现路径（否则会与“不增加 LLM 调用次数”的目标冲突）：

1) **默认推荐（不增加 LLM 调用次数）**：不自动选定；返回 `hint=need_clarification` + top-2/3 选项摘要，让用户闭集选择（例如返回 `choice_index`）；最多 1 轮澄清，用户回答后重跑全链路。

2) **可选（允许额外 1 次 LLM 调用）**：在 `ENABLE_BULK_ARBITRATION_LLM=1` 时触发 LLM 闭集仲裁（仍避免“自由生成命令”）：

- 输入：top-N capability 选项列表（仅包含必要证据：capability_id、描述、支持设备数、示例设备/room）
- 输出（最小协议，`0-based`）二选一：

```json
{"choice_index": 2}
```

或

```json
{"question": "..."}
```

澄清问题采用开放式提问；最多允许 1 轮澄清。用户回答后重跑全链路；若仍低置信度，则降级为非 bulk（返回 top-k 代表候选并提示用户更具体）。

#### 8.4 Group 的定义（兼容性 group）与 batch 分片

使用 group 作为“可批量执行”的最小单位，分组必须保证 **同组设备可安全执行同一个 capability_id**。

分组依据采用“所选 capability_id 的 CommandSpec 兼容性”：

- 对每个 target 设备，找到与 `capability_id` 对应的 `CommandSpec`
- 以该 `CommandSpec` 的参数形状作为 compatibility signature（例如 `type/value_range/value_list` 的结构）
- signature 完全一致的设备可合并为同一个 compatibility group

在执行/后处理阶段，再对每个 compatibility group 做固定大小分片（batch），用于并发控制与爆炸防护：

- `BATCH_SIZE = 20`
- 不依赖 room 分组（room 可能为空/不可用）

```python
if ir.quantifier in {"all", "except"}:
    devices0 = apply_scope_filters(devices, ir)          # scope_exclude first
    devices1 = category_gating(devices0, ir.type_hint)   # optional, skip if Unknown/invalid
    options = build_capability_options(ir, devices1, top_n=5)
    cap_id = select_capability_with_confidence_or_llm(options)
    targets = [d for d in devices1 if supports(d, cap_id)]
    groups = group_by_command_compatibility(targets, cap_id)
    batches = split_groups_into_batches(groups, batch_size=20)
    return bulk_result_with_hints(groups, batches, cap_id)
```

说明：

- `capability_id` 必须先被明确选定（必要时经 LLM 仲裁），再扩展 `targets`（保证 A：例如 all lights → 全量灯设备）
- `targets` 必须是“全量匹配集合”（保证 A：例如 all lights → 全量灯设备）
- 对外输出按 compatibility group 压缩；内部处理/执行按 batch 分片（保证 B/C）

#### 8.5 爆炸防护策略（固定 batch + 明确提示）

爆炸防护优先通过固定 batch 分片实现（不依赖 room）：

- `BATCH_SIZE = 20`

当目标规模较大时，不直接返回不可控规模的候选列表，而是：

- 返回 compatibility groups（可执行单位）及其 batch 切分计划（用于下游并发控制）
- 必要时返回明确 hint（例如 `too_many_targets`），提示用户缩小范围（room/category/name）
- 明确系统上限（例如 `MAX_TARGETS` / `MAX_GROUPS`）：超过上限时返回 `hint=too_many_targets` 并提示用户缩小范围或确认继续，避免返回不可控规模的候选列表

#### 8.6 scope_include 在 bulk mode 下的处理

沿用现有策略：`scope_include` 作为评分加权因素，而非硬过滤条件，以避免遗漏自定义名称中包含房间信息的设备。

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
│   ├── [New] action language validation (English action fallback to raw)
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
