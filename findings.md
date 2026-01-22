# Findings & Decisions：Stage2 Capability Rerank（action -> capability）

## Requirements
- 目标：在“人工设计评测集”上，将 `action(command_parser 真值)` 在指定设备 `profileId` 的候选能力集合中 Top1 选对 capability，达到 Top1 ≥ 99%。
- 输入：action（仅使用 action；不拼 raw query、不拼 scope/target 等）。
- 候选：来自 `src/spec.jsonl`，设备对应唯一 `profileId`，每个 profile 的 candidates 数量 <= 11。
- 输出：最佳 capability（以 capability_id 或 label_index 表达，取决于后续训练/推理 API）。
- 部署倾向：本地托管；x86 CPU；POC 期望延迟 ~500ms（候选<=11）。

## Research Findings
- `src/spec.jsonl` 文件名是 jsonl，但内容实际是 JSON 数组（`json.load` 可直接读取）。
- profile 数量约 45；单 profile capabilities 最大 11（天然 hard negatives）。
- 现有用例集：
  - `tests/integration/dashscope_command_parser_cases.json`：约 50 条，含稳定 `expected_fields.action`（可作为训练 query 真值，避免把线上解析噪声引入训练）。
  - `tests/integration/dashscope_bulk_pipeline_cases.jsonl`：约 50 条，含 `expected_device_ids / expected_capability_ids`。
  - `tests/integration/smartthings_devices.jsonl`：可提供 `deviceId -> profile.id` 映射。
- 现有 spec loader：`src/context_retrieval/doc_enrichment.py:load_spec_index()` 已能将 `spec.jsonl` 解析为 `profileId -> CapabilityDoc[]`，可复用其 value_range/value_list 提取逻辑。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 训练样本以 `profileId` 为“组”做组内排序/多分类 | 与线上“profile 子集内精排”一致，直接对齐 Top1 指标 |
| `query_text = normalize_action(expected_action)` | 只保留最关键的意图/参数，降低噪声，便于小数据集稳定训练 |
| `doc_text` 包含 `capability_id` + `拆解(main/x/y)` | 人工集阶段优先冲 99%；拆解 token 让模型更容易学到结构对齐 |
| candidates 顺序固定（按 capability_id 排序） | 保证 label_index 稳定与实验可复现 |
| 脏数据不“强行修复”，而是输出 skipped + reason | 99% 目标对脏样本极其敏感，先确保评测口径正确 |

## 当前“数据构造”设计（冻结版）
### 输入文件
- `src/spec.jsonl`
- `tests/integration/smartthings_devices.jsonl`
- `tests/integration/dashscope_command_parser_cases.json`（主用）

### 样本展开
- 对每个 case，按 `expected_device_ids` 展开成多条样本：`sample_id = {case_id}::{device_id}`。
- 通过 `device_id -> profile_id` 取候选集合。
- label 取 `expected_capability_ids`：
  - 若长度==1：复用到该 case 的所有 device 样本
  - 若长度==device 数：按位置对齐（需要用例保证 device 顺序稳定）
  - 否则：判脏样本，进入 skipped

### normalize_action（最小可行）
- 去除多余空白；统一分隔符（例如全角/半角等号）；统一常见同义动词到 canonical（打开/关闭/设置/查询/静音/取消静音）。
- 不做复杂改写增强（增强属于后续步骤，先跑通闭环）。

### capability doc_text（字段顺序固定 + 可裁剪）
建议格式（单行）：
`能力={description}; 参数={param_schema}; 可选={value_list_top}; 标识={capability_id}; 拆解={component/capability/command}`

其中：
- `param_schema`：
  - 有 `value_range`：`范围={min}-{max}{unit}`
  - 否则：`类型={type}`
- `value_list_top`：最多取前 5 个 `value:description`

### 输出文件（建议）
- `datasets/stage2_rerank/train.jsonl`
- `datasets/stage2_rerank/val.jsonl`
- `datasets/stage2_rerank/test.jsonl`
- `datasets/stage2_rerank/splits.json`（固定 seed + case_id 列表）
- `datasets/stage2_rerank/skipped.jsonl`（含 reason）
- `datasets/stage2_rerank/stats.json`（样本量、profile 分布、capability 分布、skipped 分类计数）

## 当前“微调”设计（冻结版）
### 训练目标（推荐）
- 组内多分类（列表式交叉熵）：
  - 输入：`query_text` + `doc_texts[]`（同一 profile 的 candidates）
  - 输出：`score_i`（每个 candidate 一个分数）
  - loss：`CE(softmax(scores), label_index)`

### 评测输出（最小集合）
- Top1（主指标）
- 混淆矩阵（按 capability_id）
- 分桶：按 profileId、按 action 类型（打开/关闭/设置/查询/静音）

### 消融开关（先写进设计，后续实现）
- `doc_text` 是否包含 `capability_id`（用于评估“捷径风险”与泛化能力）
- `max_length`（性能与效果 trade-off）

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `spec.jsonl` 实为 JSON 数组（非逐行 JSONL） | 数据构造脚本按 `json.load` 读取 |

## Resources
- `src/context_retrieval/doc_enrichment.py`（spec 解析与 value_range/value_list 提取）
- `tests/integration/dashscope_command_parser_cases.json`（action 真值）
- `tests/integration/smartthings_devices.jsonl`（device->profile 映射）

