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

### normalize_action（最小可行）
- 动词归一化由 command parser 完成（标准动词表约 ≤ 15），AI 模拟数据生成与线上产出共享该规范。
- `normalize_action` 仅做空白/符号清理与幂等兜底，不做复杂改写增强。

### capability doc_text（字段顺序固定 + 不裁剪）
注：该段规则后续再确认，当前先保留占位描述。
建议格式（单行）：
`能力={description}; 参数={param_schema}; 可选={value_list_top}; 标识={capability_id}; 拆解={component/capability/command}`

其中：
- `param_schema`：
  - 有 `value_range`：`范围={min}-{max}{unit}`
  - 否则：`类型={type}`
- `value_list_top`：最多取前 5 个 `value:description`
注：当前字段组合在本项目中自然长度不超过 256，因此不再设置额外长度上限或裁剪规则。

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
