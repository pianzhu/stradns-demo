# dashscope 集成测试说明

## 概述

使用真实的 dashscope API（qwen-flash + text-embedding-v4）进行端到端验证，覆盖 **LLM 解析 QueryIR → pipeline.retrieve() 全链路检索** 的主路径。

设备数据来源：
- 使用 `tests/smartthings_devices.jsonl` 与 `tests/smartthings_rooms.jsonl` 构造虚拟设备与房间数据（字段可为空）
- 不依赖 SmartThings Token 或真实设备接口

## 运行条件

测试默认跳过，需同时满足以下条件才会执行：

1. 设置 `DASHSCOPE_API_KEY` 环境变量
2. 设置 `RUN_DASHSCOPE_IT=1` 环境变量

## 运行方式

```bash
# 基础运行
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration -v

# 快速试跑（限制用例数）
RUN_DASHSCOPE_IT=1 DASHSCOPE_MAX_QUERIES=5 PYTHONPATH=src python -m unittest tests.test_dashscope_integration -v

# 仅运行 LLM 解析测试
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopeLLMExtraction -v

# 仅运行 command parser 输出契约测试
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopeCommandParserContract -v

# 仅运行 pipeline 全链路测试
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopePipelineRetrieve -v

# 仅运行 bulk pipeline 集成测试
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_bulk_pipeline_integration -v
```

## 可配置参数

通过环境变量配置：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DASHSCOPE_API_KEY` | - | dashscope API Key（必需） |
| `RUN_DASHSCOPE_IT` | - | 设置为 `1` 启用测试（必需） |
| `DASHSCOPE_PIPELINE_TOP_K` | `5` | pipeline.retrieve() 输出 top-k |
| `DASHSCOPE_MAX_QUERIES` | 无限制 | 最大测试用例数（用于快速试跑） |
| `DASHSCOPE_LLM_MODEL` | `qwen-flash` | LLM 模型名称 |
| `DASHSCOPE_EMBEDDING_MODEL` | `text-embedding-v4` | embedding 模型名称 |
| `DASHSCOPE_BULK_IT_MAX_CASES` | 无限制 | bulk 集成测试最大用例数 |
| `DASHSCOPE_CMD_PARSER_MAX_CASES` | 无限制 | command parser 集成测试最大用例数 |

> 说明：设备数据使用本地 JSONL 夹具构造，不需要 SmartThings 相关环境变量。

## 测试用例

测试用例定义在 `tests/dashscope_integration_queries.json`，包含 34 条真实中文 query，每条用例包含：

- `query`: 用户输入文本
- `expected_capability_ids`: 期望命中的命令 ID 列表
- `expected_fields`: 期望的 QueryIR 字段（scope_include/scope_exclude/quantifier/type_hint 等）

Bulk pipeline 集成测试用例定义在 `tests/dashscope_bulk_pipeline_cases.jsonl`，包含 simple/complex 用例：

- `query`: 用户输入文本
- `expected_devices`: 期望设备（支持 `房间/设备名` 或 `{room,name,category}`）
- `expected_device_ids`: 可选设备 ID 列表
- `expected_capability_ids`: 期望 capability 列表
- `expected_quantifier`: 可选量词

Command parser 集成测试用例定义在 `tests/dashscope_command_parser_cases.json`，由 bulk 用例派生：

- `query`: 用户输入文本
- `expected_fields`: 期望的解析字段（action/scope/target 槽位）

## 测试内容

### 1. LLM 解析测试 (TestDashScopeLLMExtraction)

- `test_llm_extraction_accuracy`: 验证 action（中文、无英文字母）覆盖率与 scope_include 解析准确率（阈值 60%）

### 2. Pipeline 全链路测试 (TestDashScopePipelineRetrieve)

- `test_pipeline_recall_rate`: 以 `pipeline.retrieve()` 最终输出为准验证召回与有效性（主路径）

覆盖点：
1. LLM 解析 QueryIR（action/type_hint/scope/quantifier）
2. scope_exclude 过滤、category gating、keyword/vector 混合召回与融合评分
3. bulk mode（quantifier=all/except）group 聚合与爆炸防护 hint
4. 输出有效性：device/group 候选可解析且 capability_id 必须可映射到有效 CommandSpec

### 3. Command parser 输出契约测试 (TestDashScopeCommandParserContract)

- 严格 JSON array<string> 输出与结构解析
- 至少一条命令匹配派生用例中的 expected_fields

## 断言阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| action 覆盖率 | ≥ 60% | LLM 输出可用于召回的中文意图短语（不含英文字母） |
| scope_include 准确率 | ≥ 60% | LLM 解析房间/范围 |
| top-k 召回命中率 | ≥ 60% | pipeline.retrieve() 最终输出命中（含 need_clarification 的 option 命中） |

阈值设置较宽松，允许模型微调/网络波动带来的偏差。
