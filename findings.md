# Findings & Decisions：Stage2 Capability Rerank（action -> capability）

## Requirements
- 目标：在“人工设计评测集”（待后续讨论）上，将 `action(command_parser 真值)` 在指定设备 `profileId` 的候选能力集合中 Top1 选对 capability，达到 Top1 ≥ 99%。
- 输入：action（仅使用 action；不拼 raw query、不拼 scope/target 等）。
- 候选：来自 `src/spec.jsonl`，设备对应唯一 `profileId`，每个 profile 的 capabilities 数量 <= 11。
- 匹配范围：与当前设备 profile 中的每一个 capability 进行匹配/评分。
- 输出：最佳 capability 的 `label_index`（按 capability_id 排序后的组内索引）。

## Research Findings
- `src/spec.jsonl` 文件名是 jsonl，但内容实际是 JSON 数组（`json.load` 可直接读取）。
- 仅考虑含 `capabilities` 字段的 profile。
- 含 `capabilities` 的 profile 共 40；capabilities 分布：min=1、p50=3.5、p90=6、max=11（天然 hard negatives），统计范围同上。
- 训练/评测数据：使用 AI 模拟数据（待定义生成规则与样本 schema）。
- `tests/integration/smartthings_devices.jsonl`：可提供 `deviceId -> profile.id` 映射，且设备 profile 一定可找到对应关系。
- 现有 spec loader：`src/context_retrieval/doc_enrichment.py:load_spec_index()` 已能将 `spec.jsonl` 解析为 `profileId -> CapabilityDoc[]`，可复用其 value_range/value_list 提取逻辑。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 训练样本以 `profileId` 为“组”做组内排序/多分类 | 与线上“profile 子集内精排”一致，直接对齐 Top1 指标 |
| `query_text = normalize_action(action)`（action 来自 AI 模拟数据） | 只保留最关键的意图/参数，降低噪声，便于小数据集稳定训练 |
| `doc_text` 包含 `capability_id` + `拆解(main/x/y)` | 人工集阶段优先冲 99%；拆解 token 让模型更容易学到结构对齐 |
| `doc_text` 不设长度上限（自然上限 ≤ 256） | 当前字段组合在本项目中不可能超过 256，避免额外裁剪带来的信息损失与规则复杂度 |
| 基座模型选 `BGE-Reranker-v2-M3` | 采用成熟 reranker 体系，匹配交叉编码精排任务形态 |
| 训练/推理脚手架使用 FlagEmbedding | 与 BGE 系列高度对齐，降低自研脚手架成本与不确定性 |
| capabilities 顺序固定（按 capability_id 排序） | label_index 由此定义，保证稳定与实验可复现 |
| 脏数据不“强行修复”，而是输出 skipped + reason | 99% 目标对脏样本极其敏感，先确保评测口径正确 |

## 当前“数据构造”设计（冻结版）
### 输入文件
- `src/spec.jsonl`
- `tests/integration/smartthings_devices.jsonl`
- AI 模拟数据文件（待生成，字段需覆盖样本构造所需的 action 与期望能力）

### 样本展开
- 不考虑多设备：NLU 已完成拆分，AI 模拟数据按“单设备样本”生成。
- 每条样本包含 `case_id`、`device_id`、`action`、`expected_capability_id`。
- 通过 `device_id -> profile_id` 取候选集合。
- label 取 `expected_capability_id`，映射为组内 `label_index`；缺失/不可映射则进入 skipped。

### normalize_action（冻结版）
- **仅做清理，不做语义映射**
- 清理规则：
  - 去除首尾空白
  - 合并连续空白为单个空格
  - 去除特殊符号（保留中文、字母、数字、`=`、`%`、`C`、`K`）
- 数值格式统一：
  - 小数最多 2 位
  - 百分比显式携带 `%`（如 `设置音量=20%`）
  - 温度使用 `C`（如 `设置温度=26C`）
- **语义正确性由 AI 生成阶段保证**（通过推荐动词表引导）
- 非标准动作原样输出，不强制归一化

### Trigger Words 机制（冻结版）

**设计目标**：解决 NLU 输出的动词（如"打开"）在不同设备上下文中语义不同的问题。

**核心思路**：不在 action 侧做映射，而是在 doc_text 中增加 `触发词` 字段，让模型学习 action 与 trigger_words 的匹配关系。

#### 两级配置 + 完整覆盖

| 级别 | 文件 | 说明 |
|------|------|------|
| Category 级别 | `category_trigger_words.yaml` | 按设备类型定义通用规则（12 个 category） |
| ProfileId 级别 | `profile_trigger_words.yaml` | 特定 profileId 的完整定义（可选） |

**查找优先级**：
```
if profileId in profile_trigger_words:
    # 该 profileId 有定义 → 完全使用它的，不再查 category
    return profile_trigger_words[profileId]
else:
    # 该 profileId 无定义 → 使用 category 的
    return category_trigger_words[category]
```

#### Category 列表（共 12 个）
```
AirConditioner, Blind, Charger, Fan, Hub, Light,
NetworkAudio, Unknown, Switch, Television, Washer, SmartPlug
```

#### category_trigger_words.yaml 示例
```yaml
Light:
  on: [打开, 开, 开灯]
  off: [关闭, 关, 关灯]
  setLevel: [设置亮度, 调亮度, 调光]
  setColorTemperature: [设置色温, 调色温]

Washer:
  on: [启动, 打开, 开始]
  off: [停止, 关闭]
  pause: [暂停]
  start: [启动, 开始, 洗衣服]
  cancel: [取消, 停止]

Television:
  on: [打开, 开, 开电视]
  off: [关闭, 关, 关电视]
  mute: [静音]
  unmute: [取消静音, 开声音]
  setVolume: [设置音量, 调音量]

# ... 其他 categories
```

#### profile_trigger_words.yaml 示例
```yaml
# 三星某型号洗衣机 - 完整定义，不再查 category
"samsung-washer-profile-abc":
  on: [启动, 打开, 开始洗涤, 洗衣服]
  off: [停止, 关闭, 停]
  pause: [暂停, 等一下, 先停]
  cancel: [取消, 不洗了]
```

#### doc_text 格式更新
```
{description}[; 触发词={trigger_words}][; 参数={param_schema}][; 可选={value_list_top}]; ID={capability_id}
```

示例：
- `电源启用; 触发词=打开,开,开灯; ID=main-switch-on`
- `启动洗涤; 触发词=启动,打开,开始洗涤,洗衣服; ID=main-...-start`

### NotAvailable 类 capability 处理
- `*-NotAvailable` 类 capability（共 8 个）全部标记为 skipped
- reason: `capability_not_available`
- 不生成训练样本

### capability doc_text（冻结版）
格式（单行）：
`{description}[; 触发词={trigger_words}][; 参数={param_schema}][; 可选={value_list_top}]; ID={capability_id}`

规则：
- `[]` 表示可选字段，为空时省略整个部分（不输出占位符）
- `trigger_words`：从 Trigger Words 机制获取（profileId 优先，category 兜底）
- `param_schema`：仅当存在 `value_range` 时输出
  - 格式：`范围={min}-{max}{unit}`（unit 取数组第一个元素，无则为空）
- `value_list_top`：仅当存在 `value_list` 时输出
  - 最多取前 5 个，格式：`value:description`，逗号分隔
- 当前字段组合自然长度 ≤ 256，不设额外长度上限

示例：
- `电源启用; 触发词=打开,开,开灯; ID=main-switch-on`
- `调光器; 触发词=设置亮度,调亮度; 参数=范围=0-100%; ID=main-switchLevel-setLevel`
- `启动洗涤; 触发词=启动,打开,开始洗涤; ID=main-...-start`
- `空气净化器风扇模式; 触发词=设置模式,调模式; 可选=auto:自动,sleep:睡眠,low:低,medium:中,high:高; ID=main-airPurifierFanMode-setAirPurifierFanMode`

### 脏数据门禁与 skipped 统计口径（冻结版）

**原则**：脏数据不强行修复，输出到 `skipped.jsonl`，附带 reason。

| 脏数据类型 | 触发条件 | reason 标记 |
|-----------|----------|-------------|
| device_id 无法映射 | `device_id` 在 `smartthings_devices.jsonl` 中找不到 | `device_not_found` |
| profile_id 无 capabilities | 映射到的 profile 无 `capabilities` 字段 | `profile_no_capabilities` |
| expected_capability_id 不存在 | 不在该 profile 的 capabilities 列表中 | `capability_not_in_profile` |
| action 为空或无效 | `action` 字段为空、null 或纯空白 | `action_empty` |
| NotAvailable 类 capability | capability_id 以 `-NotAvailable` 结尾 | `capability_not_available` |
| category 缺失 | 设备无 category 信息，无法获取 trigger_words | `category_missing` |
| 重复样本 | `case_hash` 重复（构造阶段去重） | `duplicate_case_hash` |

**skipped.jsonl 格式**：
```json
{"case_id": "xxx", "device_id": "yyy", "action": "zzz", "reason": "device_not_found"}
```

**stats.json 中的 skipped 统计**：
```json
{
  "skipped_total": 123,
  "skipped_by_reason": {
    "device_not_found": 10,
    "capability_not_in_profile": 5,
    "duplicate_case_hash": 100,
    ...
  }
}
```

### 输出文件（建议）
- `datasets/stage2_rerank/train.jsonl`
- `datasets/stage2_rerank/val.jsonl`
- `datasets/stage2_rerank/test.jsonl`
- `datasets/stage2_rerank/gen_config.yaml`（AI 模拟数据生成配置与模板版本）
- `datasets/stage2_rerank/splits.json`（固定 seed + case_id 列表）
- `datasets/stage2_rerank/skipped.jsonl`（含 reason）
- `datasets/stage2_rerank/stats.json`（样本量、profile 分布、capability 分布、skipped 分类计数）

## 当前“微调”设计（冻结版）
### 基座与训练脚手架
- `BGE-Reranker-v2-M3` + FlagEmbedding reranker 训练/推理流程

### 训练目标（推荐）
- 组内多分类（列表式交叉熵）：
  - 输入：`query_text` + `doc_texts[]`（同一 profile 的 capabilities_doc_text）
  - 输出：`score_i`（每个 capability 一个分数）
  - loss：`CE(softmax(scores), label_index)`

### 评测输出（最小集合）
- Top1（主指标）
- 混淆矩阵（按 capability_id）
- 分桶：按 profileId、按 action 类型（打开/关闭/设置/查询/静音）

### 消融开关（先写进设计，后续实现）
- `doc_text` 是否包含 `capability_id`（用于评估“捷径风险”与泛化能力）
注：暂不考虑量化与 `max_length` 相关消融，其他可选项后续再定。

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `spec.jsonl` 实为 JSON 数组（非逐行 JSONL） | 数据构造脚本按 `json.load` 读取 |
| AI 模拟数据生成规则尚未冻结 | 待后续确认生成模板与 schema |

## Resources
- `src/context_retrieval/doc_enrichment.py`（spec 解析与 value_range/value_list 提取）
- `tests/integration/smartthings_devices.jsonl`（device->profile 映射）
- `datasets/stage2_rerank/gen_config.yaml`（AI 模拟数据生成配置）
