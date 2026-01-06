# 设计文档：改进 Embedding 召回率

## 上下文

### 问题现状

集成测试显示 embedding 召回率仅 40%（目标 ≥60%）。典型失败案例：

| 用户查询 | LLM action | 期望命令 | 实际 top-1 |
|---------|-----------|---------|-----------|
| 打开客厅的灯 | `open` | `main-switch-on` | `main-windowShade-open` |
| 把灯光调到50% | `adjust` | `main-switchLevel-setLevel` | `main-windowShadeTiltLevel-setShadeTiltLevel` |

**根因**：泛化动词 + 无类型区分 + 短文本相似度退化。

### 数据源

1. **SmartThings API**：`GET /v1/devices?locationId=...`
   - 返回 `items[].components[].categories[].name`：设备类别（Light/Blind/AirConditioner/...）
   - 返回 `items[].profile.id`：关联 spec.jsonl 的 profileId

2. **spec.jsonl**：本地规范文件
   - 结构：`{profileId, capabilities: [{id, description, type, value_range}]}`
   - 用途：为每个 capability 提供中文语义描述

## 目标 / 非目标

### 目标

- 将 top-10 召回命中率从 40% 提升到 ≥ 90%
- 保持现有 QueryIR 接口兼容
- 不增加 LLM 调用次数

### 非目标

- 不改变 LLM prompt 结构（后续优化可单独做）
- 不支持多 component 设备（当前仅处理 `main` component）
- 不处理跨 category 的模糊命令

## 决策

### 决策 1：双通道检索架构

```
用户查询
    ↓
LLM 解析 → QueryIR (action, type_hint, name_hint, scope_include...)
    ↓
┌─────────────────────────────────────────────────────────────┐
│  type_hint 存在且可映射到 category?                          │
│    ├─ Yes → Category Gating → 子候选集 → Embedding 检索      │
│    │                                                         │
│    └─ No  → Keyword 模糊匹配 (name + room) 为主              │
└─────────────────────────────────────────────────────────────┘
    ↓
融合排序 → Top-K
```

**理由**：
- 有 type_hint → 用户使用通用描述（"灯"），category gating 有效
- 无 type_hint → 用户使用自定义名称（"老伙计"），名称匹配更有效

### 决策 2：type_hint → Category 映射

使用静态映射表 + 模糊匹配：

```python
TYPE_TO_CATEGORY = {
    # 灯光类
    "灯": "Light", "灯光": "Light", "照明": "Light", "台灯": "Light",
    # 窗帘类
    "窗帘": "Blind", "遮阳": "Blind", "百叶窗": "Blind",
    # 空调类
    "空调": "AirConditioner", "冷气": "AirConditioner",
    # 开关类
    "开关": "Switch", "插座": "SmartPlug",
    # 影音类
    "电视": "Television", "音响": "NetworkAudio",
    # 其他
    "风扇": "Fan", "洗衣机": "Washer", "充电器": "Charger",
}
```

**考虑的替代方案**：
- LLM 直接输出 category 枚举 → 需改 prompt，增加复杂度
- embedding 相似度匹配 type_hint → 额外计算开销

**选择理由**：静态映射简单可控，覆盖常见场景，易于维护。

### 决策 3：文档富化策略

**当前文档**：
```
设备名 房间 类型 命令描述1 命令描述2 ...
```

**富化后文档**（按命令粒度）：
```
{category} {capability_id} {description} {同义词扩展}
```

**示例**：
```
# 原始
Light switch 电源启用

# 富化后
Light switch 电源启用 打开 开 开启 启动 on
```

**同义词扩展表**：
```python
VERB_SYNONYMS = {
    "启用": ["打开", "开", "开启", "启动", "on"],
    "关闭": ["关", "关掉", "停止", "off"],
    "调": ["调节", "调整", "设置", "调到", "设为"],
}
```

**带参数命令的处理**（`value_list`）：

spec.jsonl 中部分命令包含 `value_list`，参数描述也携带重要语义：

```json
{
  "id": "main-airConditionerMode-setAirConditionerMode",
  "description": "设置空调模式",
  "value_list": [
    {"value": "cooling", "description": "制冷"},
    {"value": "heating", "description": "制热"}
  ]
}
```

**策略**：将 `value_list` 中的所有参数描述拼接到命令文档中：

```python
def build_doc_with_values(cap: dict) -> str:
    parts = [cap["description"]]  # "设置空调模式"
    if "value_list" in cap:
        for v in cap["value_list"]:
            parts.append(v["description"])  # "制冷", "制热", ...
    return " ".join(parts)

# 结果: "设置空调模式 制冷 制热"
```

**理由**：
- 用户说"空调制冷"时，"制冷"能匹配到文档
- 避免为每个参数值生成独立向量（索引膨胀）
- 当前规模下（value_list 通常 <10 项）拼接不会稀释语义
- 不依赖 LLM 输出稳定性，查询任意表达都有机会命中

### 决策 4：索引粒度

**选择**：命令级索引（而非设备级）

```
# 设备级（当前）
device_id → embedding([name, room, type, cmd1_desc, cmd2_desc, ...])

# 命令级（新）
(device_id, capability_id) → embedding([category, capability, description, synonyms])
```

**理由**：
- 命令级文档区分度更高
- 避免多命令描述混在一起稀释语义
- 检索结果直接对应具体命令

### 决策 5：scope_include 作为评分加权（非硬过滤）

**问题**：设备自定义名称可能包含房间词（如"客厅老伙计"），若用 `scope_include` 做硬过滤会遗漏。

**决策**：`scope_include` 不作为预过滤条件，而是作为评分加权因素。

```python
# 错误做法：硬过滤
devices = [d for d in devices if d.room in scope_include]  # ❌ 会遗漏"客厅老伙计"

# 正确做法：评分加权
if device.room in scope_include:
    score += ROOM_MATCH_BONUS  # ✓ 加分但不排除
```

**理由**：
- 避免因自定义名称中的房间词导致遗漏
- keyword 检索可通过名称模糊匹配召回这些设备
- 房间匹配仍能通过加权提升排名

### 决策 6：Fallback 策略

当 `type_hint` 为空或映射失败时：

1. **不做 category gating**，保留全量候选集
2. **提升 keyword 权重**：优先使用 name/room 模糊匹配
3. 使用现有 `keyword_search.py` 的评分逻辑

**理由**：用户使用自定义名称时，名称本身是最强信号。

## 风险 / 权衡

| 风险 | 缓解措施 |
|------|----------|
| type_hint 映射表不完整 | 持续补充 + fallback 保底 |
| 同义词表维护成本 | 初期聚焦高频动词，后续按需扩展 |
| 命令级索引存储量增加 | 当前设备规模（<1000）可接受 |
| category 与实际能力不匹配 | 以 spec.jsonl 为准，category 仅做初筛 |

## 模块设计

### 新增模块

```
src/context_retrieval/
├── category_gating.py      # Category 过滤
│   ├── TYPE_TO_CATEGORY    # 映射表
│   └── filter_by_category() # 过滤函数
│
└── doc_enrichment.py       # 文档富化
    ├── VERB_SYNONYMS       # 同义词表
    ├── load_spec_index()   # 加载 spec.jsonl
    └── build_enriched_doc() # 构建富化文档
```

### 修改模块

```
pipeline.py
├── retrieve()
│   ├── [新增] 判断 type_hint → category 映射
│   ├── [新增] 有映射 → apply_category_gating()
│   ├── [新增] 无映射 → 增强 keyword 权重
│   └── [现有] 融合评分

vector_search.py
├── InMemoryVectorSearcher
│   ├── [修改] __init__() 接收 spec_index
│   └── [修改] _build_corpus() 使用富化文档
```

### 数据流

```
启动时：
spec.jsonl → load_spec_index() → {profileId: [capability_docs]}
    ↓
devices + spec_index → build_enriched_docs() → corpus embeddings

检索时：
QueryIR.type_hint → TYPE_TO_CATEGORY → category
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

3. **多 category 设备**：一个设备有多个 category 时如何处理？
   - 建议：当前忽略，按首个 category 处理
