# Task Plan: Stage2 Capability Rerank 微调（action -> capability）

## Goal
在“已知设备（profileId 已确定）”前提下，用本地可托管的 reranker 微调方案，将 `action(command_parser 真值)` 精确匹配到 `src/spec.jsonl` 中该 profile 的最佳 capability，离线人工设计集 Top1 ≥ 99%，并为后续 POC（x86 CPU 500ms 左右）留出推理形态与护栏。

## Current Phase
Phase 1

## Phases

### Phase 1: 需求与现状盘点
- [x] 明确 Stage2 任务边界：profileId 内（<=11 candidates）做精排
- [x] 明确 query 仅使用 action（训练用真值 action）
- [x] 明确 doc_text 包含 capability_id（优先冲人工集 99%）
- [ ] 补齐性能/部署约束（POC x86 CPU 500ms）对应的推理引擎与模型选择结论
- **Status:** in_progress

### Phase 2: 数据集规格冻结（可复现）
- [ ] 定义样本 schema（jsonl）
- [ ] 定义 action 规范化规则（normalize_action）
- [ ] 定义 capability doc_text 生成规则（字段顺序固定、长度上限）
- [ ] 定义 train/val/test 拆分规则（按 case_id 固定种子）
- [ ] 定义脏数据门禁与 skipped 统计口径
- **Status:** pending

### Phase 3: 微调方案落地
- [ ] 选择基座与训练脚手架（优先 FlagEmbedding/bge-reranker；备选 qwen3 rerank 0.6b）
- [ ] 训练目标：组内多分类（列表式交叉熵）或可替代目标（pairwise）
- [ ] 评测输出：Top1 + 混淆矩阵 + 分桶（profile/action）
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
1. 基座模型最终选哪类以满足 x86 CPU ~500ms：bge-reranker（FlagEmbedding）还是 0.6B rerank？
2. doc_text 的长度上限与字段裁剪规则是什么（直接影响 CPU 延迟与效果）？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Stage2 只在 profileId 内做精排（候选<=11） | 候选集合小，适合用 rerank 直接优化 Top1 |
| query_text 只用 action，且训练时用真值 action | 降低噪声与训练不稳定，先冲人工集 Top1≥99% |
| doc_text 包含 capability_id | 人工集阶段优先达成 99%，后续再做“去 ID”消融评估 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| exec_command 入参类型错误（cmd 误传 list） | 1 | 改为字符串形式 `bash -lc '...'` |

## Notes
- 本 plan 先聚焦：数据构造 + 微调（不改线上链路、不做产品化实现）。
