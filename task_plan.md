# Task Plan: Stage2 Capability Rerank 微调（action -> capability）

## Goal
在已知设备（deviceId 可映射到唯一 profileId）的前提下，微调一个可本地托管的交叉编码精排模型（BGE-Reranker-v2-M3 + FlagEmbedding），仅使用 action 作为 query，在该 profile 的候选 capability 集合（每组不超过 11 个）内选出 Top1 capability，并输出组内 label_index（capabilities 按 capability_id 排序后定义索引）。在人工设计评测集上达到 Top1 ≥ 99%，并产出可复现的数据构造、训练、评测与推理脚手架；性能目标（x86 处理器上单条 action × 候选数的端到端耗时约 500ms）作为 Phase 4 的基准验收项。

## Current Phase
Phase 2

## Phases

### Phase 1: 需求与现状盘点（冻结版）
- [x] 明确 Stage2 任务边界：profileId 内（<=11 candidates）做精排
- [x] 明确 query 仅使用 action（训练用真值 action）
- [x] 明确候选来源：`src/spec.jsonl` 的 profile.capabilities（仅考虑含 capabilities 字段的 profile）
- [x] 明确输出：组内 `label_index`（capabilities 按 capability_id 排序后定义索引，保证稳定可复现）
- [x] 明确 doc_text 包含 capability_id（优先冲人工集 99%）
- [x] 明确 `src/spec.jsonl` 文件名为 jsonl，但内容实际为 JSON 数组（按 `json.load` 读取）
- [x] 明确 deviceId -> profileId 映射来源：`tests/integration/smartthings_devices.jsonl`
- [x] 明确可复用现有 spec loader：`src/context_retrieval/doc_enrichment.py:load_spec_index()`（含 value_range/value_list 提取逻辑）
- [x] 明确基座模型：`BGE-Reranker-v2-M3`
- [x] 明确训练/推理脚手架：FlagEmbedding reranker
- [x] 明确脏数据策略：不强行修复，输出 skipped + reason
- **Status:** completed

### Phase 2: 数据集规格冻结（可复现）
- [ ] 定义样本 schema（jsonl）
  - 必填字段：`case_id`、`device_id`、`action`、`expected_capability_id`
  - `case_id`：生成时分配的全局唯一编号（可读、可追踪）
  - `case_hash`：基于 `device_id + action + attr_key + 参数摘要` 的确定性哈希（用于去重/追溯；不参与模型输入）
  - `expected_capability_id`：必须与 `src/spec.jsonl` 中的 `capability_id` 完全一致（严格字符串匹配）
  - `attr_key`：规范属性键（用于“设置”动作的追溯与去歧义；不参与模型输入；通常可由 `expected_capability_id` 的 capability 段推导，如 `main-thermostatMode-setThermostatMode` -> `thermostatMode`）
    - 取值规则（冻结）：由 `expected_capability_id` 自动推导（不依赖额外业务词表）
    - 非“设置”动作：`attr_key` 固定为空字符串 `""`（用于稳定 `case_hash` 口径）
  - 元数据字段（不参与模型输入，仅用于可复现与排错）：`profile_id`、`expected_label_index`、`gen_version`、`split`（train/val/test）、`case_hash`、`attr_key`
- [ ] 冻结 AI 模拟数据规模 N（总样本数）
  - 结论：N = 12,000（按“单设备样本”行数计，即最终展开后的 jsonl 总行数；train/val/test 总和；后续按覆盖不足增量生成）
- [x] 定义 action 规范化规则（normalize_action）
  - normalize_action 仅做空白/符号清理，不做语义映射
  - 清理规则：去除首尾空白、合并连续空白、去除特殊符号
  - 数值格式：小数最多 2 位，百分比显式携带 `%`，温度使用 `C`
  - 语义匹配由 doc_text 中的 trigger_words 提供线索
  - 非标准动作原样输出（不强制归一化）
- [x] 定义 Trigger Words 机制（Category + ProfileId 覆盖）
  - 两级配置：`category_trigger_words.yaml`（通用）+ `profile_trigger_words.yaml`（特定 profileId 完整覆盖）
  - 查找优先级：profileId 有定义 → 完全使用它的；否则 → 使用 category 的
  - Category 列表（12 个）：AirConditioner, Blind, Charger, Fan, Hub, Light, NetworkAudio, Unknown, Switch, Television, Washer, SmartPlug
  - 详见 findings.md Trigger Words 机制
- [x] 定义 capability doc_text 生成规则（字段顺序固定、不设长度上限）
  - 格式：`{description}[; 触发词={trigger_words}][; 参数={param_schema}][; 可选={value_list_top}]; ID={capability_id}`
  - `[]` 表示可选字段，为空时省略
  - `trigger_words`：从 Trigger Words 机制获取
  - `param_schema`：仅当存在 `value_range` 时输出，格式 `范围={min}-{max}{unit}`
  - `value_list_top`：仅当存在 `value_list` 时输出，最多前 5 个，格式 `value:description`
  - 当前字段组合自然长度 ≤ 256，不设额外长度上限
  - Stage2 仍只预测 `capability_id`（label_index），`value_list` 仅作为 doc_text 线索
- [ ] 定义 train/val/test 拆分规则（按 case_id + 固定 seed=42，由脚本计算）
  - 比例：train/val/test = 90/5/5（N=12,000 -> 10,800/600/600）
  - 将 `split` 写回每条样本（train/val/test），避免口径漂移
  - 同步落盘 `splits.json`（seed + case_id 列表），保证可复现
- [x] 定义脏数据门禁与 skipped 统计口径
  - 脏数据不强行修复，输出到 `skipped.jsonl`，附带 reason
  - 7 种脏数据类型：`device_not_found`, `profile_no_capabilities`, `capability_not_in_profile`, `action_empty`, `capability_not_available`, `category_missing`, `duplicate_case_hash`
  - 重复样本在构造阶段通过 `case_hash` 去重，标记为 skipped
  - `stats.json` 中统计 skipped 分类计数
- **Status:** completed

### Phase 3: 微调方案落地
- [x] 选择基座与训练脚手架：BGE-Reranker-v2-M3 + FlagEmbedding
- [x] 训练目标：组内多分类（列表式交叉熵）
- [x] 评测输出：Top1 + 混淆矩阵 + 分桶（profile/action）
- **Status:** pending

### Phase 4: 推理与性能 POC（CPU）
- [ ] 推理形态：batch=候选数、max_length、量化策略
- [ ] 端到端微基准：单条 action * 11 candidates 的耗时分布（p50/p95）
- [ ] 失败回退策略（解析失败/低置信/margin 小）
- **Status:** pending

### Phase 5: 交付与下一步
- [ ] 输出可复现的训练/评测说明与配置
- [ ] 明确“人工集 99% -> 真实分布”迁移路径（后续工作，不在本轮实现）
- **Status:** pending

## Key Questions
1. “人工设计评测集”的最终定义与覆盖范围是什么（设备/profile 分布、action 类型分布、边界样例口径）？
2. AI 模拟数据的 schema 与生成模板/版本如何冻结，以保证可复现实验与可追溯数据漂移？
3. Phase 4 的性能验收口径如何定义（硬件型号、并发、候选数上限、p50/p95 阈值、量化/推理参数）？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Stage2 只在 profileId 内做精排（候选<=11） | 候选集合小，适合用 rerank 直接优化 Top1 |
| query_text 只用 action，且训练时用真值 action | 降低噪声与训练不稳定，先冲人工集 Top1≥99% |
| doc_text 包含 capability_id | 人工集阶段优先达成 99%，后续再做“去 ID”消融评估 |
| 训练样本以 profileId 为组做组内排序/多分类 | 与线上“profile 子集内精排”一致，直接对齐 Top1 指标 |
| normalize_action 仅做最小清理（空白/符号/幂等兜底） | 动词归一化由 command parser 保证，避免离线规则引入不可控偏差 |
| doc_text 包含 capability 拆解（main/x/y） | 强化结构对齐信号，优先冲人工集 99% |
| doc_text 不设长度上限（自然上限 ≤ 256） | 避免裁剪带来信息损失与规则复杂度 |
| capabilities 顺序固定（按 capability_id 排序） | label_index 由此定义，保证稳定与实验可复现 |
| 基座模型：BGE-Reranker-v2-M3 | 交叉编码精排任务形态匹配，体系成熟 |
| 训练/推理脚手架：FlagEmbedding | 与 BGE 系列对齐，降低自研不确定性 |
| 脏数据不强行修复，输出 skipped + reason | 99% 目标对脏样本敏感，先确保评测口径正确 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| exec_command 入参类型错误（cmd 误传 list） | 1 | 改为字符串形式 `bash -lc '...'` |

## Notes
- 本 plan 先聚焦：数据构造 + 微调（不改线上链路、不做产品化实现）。
