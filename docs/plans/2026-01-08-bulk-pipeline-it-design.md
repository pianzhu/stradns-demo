# Bulk Pipeline 集成测试设计

## 目标

- 用真实 SmartThings 设备/房间数据验证 bulk mode + pipeline 的端到端效果。
- 允许多筛，但不允许漏筛：期望设备与 capability 必须覆盖。
- 对需要澄清的情况提供可接受的通过判定与统计。

## 数据与用例

- 设备与房间数据：`tests/smartthings_devices.jsonl`、`tests/smartthings_rooms.jsonl`。
- 设备能力规范：`src/spec.jsonl`。
- 用例文件：`tests/dashscope_bulk_pipeline_cases.jsonl`。
- 用例规模：simple 约 30 条，complex 约 20 条。

### 用例 schema

- `id`: 用例编号（字符串）。
- `query`: 用户输入。
- `complexity`: `simple` 或 `complex`。
- `expected_device_ids`: 期望设备 ID 列表（可选）。
- `expected_devices`: 期望设备描述列表（可选）。
- `expected_capability_ids`: 期望 capability 列表。
- `expected_quantifier`: 可选量词（用于标识 bulk 语义）。
- `notes`: 可选说明。

### 用例示例

```jsonl
{"id":"s-001","complexity":"simple","query":"打开客厅的落地灯","expected_devices":["客厅/落地灯"],"expected_capability_ids":["switch"]}
{"id":"c-004","complexity":"complex","query":"除了卧室，其他房间的灯都关掉","expected_devices":[{"room":"客厅","name":"主灯","category":"Light"}],"expected_capability_ids":["switch"],"expected_quantifier":"except"}
```

## 解析与预校验

- 构建 `room+name(+category)` 到 `device_id` 的映射。
- 若同一房间内存在“同名且同类”设备，直接报错并提示改名，以避免歧义。
- 若同一房间内同名但类别不同，要求用例在 `expected_devices` 中显式提供 `category`。
- `expected_devices` 解析成功后统一合并为 `expected_device_ids`。

## 执行流程

1. 初始化 DashScope LLM 与 embedding（使用 DashScope 真实 API）。
2. 读取房间与设备数据，构建设备列表与索引。
3. 加载 spec，构建 `spec_index` 与向量索引。
4. 逐条执行 `pipeline.retrieve`，记录耗时与结果。
5. 生成实际命中集合、capability 命中集合与 bulk 结构信息。

## 判定规则

- 设备命中：`expected_device_ids` 必须是 `actual_device_ids` 的子集（不可漏）。
- capability 命中：
  - 非 bulk：从 `candidates.capability_id` 收集。
  - bulk：使用 `selected_capability_id`；若需要澄清，则允许 `options` 命中。
- `hint` 为 `need_clarification` 或 `too_many_targets` 时：
  - 只要 `question` 非空或 `options/selected` 命中期望 capability，即记为 `CLARIFY_PASS`。
  - 否则为失败。

## 日志与统计

- 每条用例输出：`query`、耗时、`hint`、`expected/actual`、缺失设备、
  `selected_capability_id`、`options` 摘要、`groups/batches` 统计。
- 汇总按 `simple/complex` 分组：`PASS/CLARIFY_PASS/FAIL`、漏筛率、澄清率。
- 输出前 N 条失败样例，便于回溯。

## 运行方式

- 依赖环境变量：`RUN_DASHSCOPE_IT=1`、`DASHSCOPE_API_KEY`。
- 可选参数：`DASHSCOPE_PIPELINE_TOP_K`、`DASHSCOPE_LLM_MODEL`、`DASHSCOPE_EMBEDDING_MODEL`、`DASHSCOPE_IT_PROGRESS`。
- 建议命令：

```bash
RUN_DASHSCOPE_IT=1 DASHSCOPE_API_KEY=... pytest tests/test_bulk_pipeline_integration.py -s
```
