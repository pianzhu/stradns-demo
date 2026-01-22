# 监督 Rerank + SFT 微调计划（设备 -> 能力两阶段）

> 创建日期：2026-01-22  
> 状态：想法记录（待进一步确认后进入实施）

## 1. 目标与范围

- 目标：显著提高“设备相关命令”的 rerank top1 设备召回率（Top-1 选对设备）。
- 约束：仅基于现有手写/集成用例构造监督数据（无线上日志/回执）。
- 采用两阶段选择：
  - Stage 1：在候选设备 topN=10 内做设备重排/选择（核心优化点）。
  - Stage 2：在“已确认设备/类别”后，对该设备的候选能力（capabilities）做选择；候选通常 <= 10，因此直接全量输入。

## 2. 关键假设（依赖现状判断）

- 设备召回：在当前检索管线下，正确设备以极高概率已进入 topN=10（因此 rerank 可带来显著收益）。
- 能力召回：在已确认设备/类别后，正确 capability_id “不在候选集”的概率很低（因此 Stage 2 更适合作为精排/选择，而非补召回）。

## 3. 方案概述（推荐）

### 3.1 Stage 2：用 action 选择 capability（核心问题聚焦）

- 输入 query：优先使用 `command_parser` 解析得到的 `action`（见 `src/context_retrieval/ir_compiler.py` 的 `QueryIR.action`）。
  - 若 `action` 为空或 UNKNOWN：回退到 `raw query`。
- 选择对象：该设备对应 profile 的 capability 列表（<= 10 时全量输入）。
- 输出：强约束 JSON，例如 `{"choice_index": <int>}`，用于选择最匹配的 capability。

### 3.2 Capability Doc（不使用同义词的推荐格式）

仅使用 `spec.jsonl` 中字段（`id/description/type/value_range/value_list`），拼成单行、字段顺序固定的 doc：

```text
能力: {description} | 参数: {param_schema} | 可选: {value_list_top} | 标识: {capability_id} | 拆解: {component}/{capability}/{command}
```

- `param_schema`：
  - 有 `value_range`：`范围={minimum}-{maximum}{unit}`（unit 若是数组取第一个）
  - 否则：`类型={type}`
- `value_list_top`：若存在 `value_list`，拼 `value:description`，最多前 5 个；没有则省略该段。
- `拆解`：把 `capability_id` 按 `-` 分为三段，例如 `main-switchLevel-setLevel -> main/switchLevel/setLevel`。

## 4. 数据集构造（仅基于手写用例）

- 种子标注来源：
  - `tests/integration/dashscope_bulk_pipeline_cases.jsonl`（包含 query、expected_device_ids、expected_capability_ids 等）。
- Stage 1 数据：
  - 对每条 query 跑一次当前检索管线，截取 topN=10 作为候选设备集合；
  - label 为正确设备在候选集合中的索引（若不在 topN，标记为召回失败样本，单独统计，不直接用于 rerank 训练）。
- Stage 2 数据：
  - 基于正确设备（或已选设备）展开其 capability 候选集合（<= 10 全量）；
  - 使用上面的 capability doc 格式构造候选文本；
  - label 为正确 capability_id 的索引。

## 5. 评估与回退策略

- 离线指标（最小集合）：
  - Stage 1：Top-1 / Top-3 / Top-10 设备命中率（按 query 统计）。
  - Stage 2：Top-1 capability 命中率（仅在设备已正确/或以正确设备为前提统计）。
- 回退策略：
  - rerank 输出解析失败、或输出索引越界：回退到当前启发式/原排序结果。
  - `action` 缺失或 UNKNOWN：回退到 `raw query` 作为 rerank query。

## 6. 风险评估与缓解

- 过拟合风险（手写用例覆盖窄）：训练/验证/测试需按设备或房间维度拆分，避免“同模板同设备”泄漏。
- 文本捷径风险（capability_id 被模型当作硬规则）：保留“去掉 capability_id 段”的消融评估开关，用离线指标决定是否保留。
- 工程风险（时延/可用性）：仅在候选 <= 10 时执行；失败即回退，保证可用性不下降。

## 7. 待确认问题（进入实施前）

- Stage 1 是否先限定在 `quantifier=one` 的单设备场景，多设备/批量场景保持现有逻辑不动？

