# gating Specification

## Purpose
TBD - created by archiving change add-context-retrieval. Update Purpose after archive.
## 需求
### 需求：Top-K 筛选

系统必须按总分降序排列候选，并返回前 k 个结果。

#### 场景：返回排序后的 Top-K

- 给定：候选列表包含 lamp-1（score=0.90）、lamp-2（score=0.70）、lamp-3（score=0.50）
- 且：top_k = 2
- 当：执行筛选
- 则：结果应包含 lamp-1 和 lamp-2
- 且：lamp-1 应排在第一位

### 需求：分数接近提示

当 top1 和 top2 分数接近时，系统必须返回 hint 供大模型参考。

#### 场景：分差不足返回提示

- 给定：候选列表包含 lamp-1（score=0.80）和 lamp-2（score=0.78）
- 且：close_threshold 为 0.1
- 当：执行筛选
- 则：hint 应为 "multiple_close_matches"

#### 场景：分差足够无提示

- 给定：候选列表包含 lamp-1（score=0.90）和 lamp-2（score=0.60）
- 当：执行筛选
- 则：hint 应为 None

### 需求：空结果处理

当没有召回候选时，系统必须返回空列表，且 hint 必须为 None。

#### 场景：无候选返回空

- 给定：候选列表为空
- 当：执行筛选
- 则：结果列表应为空
- 且：hint 应为 None

