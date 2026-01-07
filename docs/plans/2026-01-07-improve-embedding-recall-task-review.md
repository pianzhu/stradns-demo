# 改进 Embedding 召回率：任务清单效果评审

本文是对 OpenSpec 变更 `improve-embedding-recall` 的任务清单（`openspec/changes/improve-embedding-recall/tasks.md`）逐项 review，目标是判断每个任务是否**足以**推动 Embedding 召回率达到预期，并明确关键前提、主要风险与验证方式。

## 1. 范围与输入

- 变更说明：`openspec/changes/improve-embedding-recall/proposal.md`
- 设计决策：`openspec/changes/improve-embedding-recall/design.md`
- 任务清单：`openspec/changes/improve-embedding-recall/tasks.md`
- 评估基准：`tests/test_dashscope_integration.py` + `tests/dashscope_integration_queries.json`

## 2. 预期效果与验收口径（需要先对齐）

当前文档中存在两种目标口径：

- `proposal.md`：集成测试召回率从 40% 提升到 **≥60%**
- `design.md`：top-10 召回命中率从 40% 提升到 **≥90%**

如果不先统一目标与指标（至少明确以 `Recall@10` 为准，以及阈值到底是 60% 还是 90%），那么任务完成后的“是否达标”会出现结论不一致的问题。

建议把验收拆成两层：

- **Gate（必须达标）**：`Recall@10 >= 60%`（与现有测试阈值一致）
- **Stretch（期望达标）**：`Recall@10 >= 90%`，并补充 `Top-1`/`MRR`/按 `category` 分桶结果，避免“Top-10 看起来好但体验差”

## 3. 核心增益链路（帕累托）

从“召回率为什么低”的第一性原理看，提升 `Recall@10` 的最有效路径是：

1. **先降噪**：减少候选集中的互相干扰（例如同动词但不同设备类型）
2. **再增信号**：让每条 embedding 文档更贴近用户 query 的语义分布，且更可区分
3. **兜底可用性**：当 `type_hint` 不可靠时不要 hard fail（否则误杀会直接降低召回）

对应到任务清单，真正承载主要增益的是：

- `Category gating`（降噪）
- `doc enrichment + command-level index`（增信号）
- `fallback + merge scoring`（兜底）

## 4. 逐任务评审（是否能达到预期）

下表按任务清单编号给出判断：是否对提升 `Recall@10` 有直接贡献、依赖的前提、以及主要风险与验证点。

| 任务 | 预期增益 | 达成前提 | 主要风险 | 建议验证 |
| --- | --- | --- | --- | --- |
| 1.1 `category_gating.py` | 高（降噪） | `type_hint` 输出准确且设备 `category` 覆盖充分 | **误杀**：`type_hint` 错但合法导致 hard false-negative | 统计 gating 触发率、过滤比例、分 `category` 的 `Recall@10` delta；对比 hard vs soft gating |
| 1.2 `doc_enrichment.py` | 高（增信号） | `profileId -> spec` 覆盖率高且 `capability_id` 对齐稳定 | 同义词引入噪声/中英混杂导致向量漂移；缺 spec 时降级文档信号不足 | 做 ablation：不加同义词/不加 value 描述/仅中文扩展；记录缺 spec 比例与对应召回 |
| 2.1 命令级索引 + `DashScopeVectorSearcher` | 高且必要 | 每条向量能映射到正确 `(device_id, capability_id)` | 索引构建成本上升；每次检索重建索引可能浪费 | 对同设备多命令场景检查（如 `setLevel` vs `on/off`），确认排序能区分 |
| 2.2 删除冗余代码 | 低（可维护） | 所有引用已迁移 | 回归风险（误删被间接依赖） | 运行单测与集成测试，确保 import 路径无回退 |
| 3.1 `retrieve()` 集成 gating | 高（降噪落地） | gating 放在 `scope` 后，且不会叠加过窄 | scope + gating 叠加过窄导致召回下滑 | 记录 `gating_before/after` 分布，定位“过窄 query” |
| 3.2 fallback 策略 | 中（防崩盘） | `type_hint` 为 `Unknown` 时 keyword 能提供有效信号 | keyword 若缺 `name/room` 信号会弱，可能拖累召回 | 单独统计 `type_hint=Unknown/非法/None` 子集的 `Recall@10`，并调参或引入二阶段扩展候选 |
| 3.3 命令级候选 + 融合适配 | 高且必要 | 融合逻辑对命令级结果的权重合理 | keyword 仍是设备级，若 `w_vector` 偏低会伤命令区分 | 针对多命令设备用例检查 `Recall@10` 与 `Top-1` 是否改善 |
| 3.4 `scope_include` 加权 | 中/低（偏排序） | room 字段质量足够 | LLM room 解析噪声导致误加权 | 分“有/无 `scope_include`”分别统计指标；观察误加权样例 |
| 4.1 单测更新 | 间接（防回归） | 覆盖关键逻辑分支 | 覆盖不全导致误以为安全 | 覆盖 `type_hint` 归一化、spec 缺失降级、value_list 拼接、候选命令映射 |
| 4.2 集成测试阈值 | 不是增益来源（验收） | 指标口径一致 | 阈值过宽掩盖体验问题；或与 design 目标冲突 | 同时输出 `Recall@10/Top-1/MRR`，并按 `category` 分桶 |
| 4.3 回归测试 | 保障项 | keyword/scope 行为不变 | 不易察觉的退化 | 保留 keyword-only 路径基线，做 before/after 对比 |
| 5.1 README 更新 | 不是增益来源（可复现） | 记录完整配置与结果 | 仅写结论不写证据，难以复现 | 写清 before/after、样本数、环境变量、分桶与失败样例 |
| 5.2 调试日志 | 不是增益来源（定位工具） | 日志能支撑逐 query 追溯 | 过多噪声或缺关键信息 | 至少能追溯：`type_hint->category`、gating 数量变化、Top candidates 与分数组成 |

## 5. 事前验尸（最可能的失败方式）

### 5.1 最薄弱环节：hard gating 误杀

当 `type_hint` 错但属于合法集合时，hard gating 会将正确设备整体过滤掉，直接造成 `Recall@10` 下滑（这是不可由排序修复的 false-negative）。

建议补充一个明确的“误杀缓解”策略（作为任务清单的硬交付物）：

- **Soft gating**：把 `category` 作为先验加分，而不是硬过滤
- **Two-pass retrieval**：先在 gated 集合检索；若得分低/置信度低/候选数不足，再扩到全集补检

### 5.2 富化文档的噪声风险

同义词扩展容易引入与 query 语种不一致的 token（例如英文 `on/off`），可能导致 embedding 语义漂移或稀释。

建议通过 ablation 固化“同义词到底带来多少增益”，并按样本分布逐步扩展，而非一次性扩大词表。

### 5.3 指标通过但体验不佳

仅用 `Recall@10` 可能掩盖 `Top-1` 很差的问题。建议把 `Top-1` 或 `MRR` 作为补充输出（至少在 README 中），否则很难确认“用户一次命中”的体验改善。

## 6. 建议的验证步骤（最小可执行）

建议以同一批 queries 固化对比，并补充分桶与 ablation：

```bash
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration -v
```

建议追加的统计输出（可在测试或独立脚本中实现）：

- `Recall@10`, `Top-1`, `MRR`
- 按 `type_hint`（有效/Unknown/缺失/非法）分桶
- 按 `category` 分桶（Light/Blind/AirConditioner/...）
- hard gating vs soft/two-pass gating 对比
- doc enrichment ablation 对比（no-synonyms / no-values / full）

## 7. 结论

任务清单的主链路（`category gating` + `命令级索引` + `spec 驱动的文档富化` + `fallback/融合`）方向正确，理论上对提升 `Recall@10` 有直接帮助，达到 `≥60%` 的概率高。

若预期效果按 `design.md` 的 `≥90%`，当前任务清单还缺少两个“达标关键件”：

1. **hard gating 误杀缓解**（soft/two-pass gating）
2. **更强的可复现实证**（分桶指标 + ablation + before/after 报告）

