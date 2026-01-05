# dashscope 集成测试说明

## 概述

使用真实的 dashscope API（qwen-flash + text-embedding-v4）进行端到端验证，覆盖 **LLM 解析 QueryIR → 使用 QueryIR.action.text 做 embedding 检索** 的主路径。

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
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopeLLMIntegration -v

# 仅运行 embedding 召回测试
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopeEmbeddingIntegration -v

# 仅运行端到端测试
RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.test_dashscope_integration.TestDashScopePipelineIntegration -v
```

## 可配置参数

通过环境变量配置：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DASHSCOPE_API_KEY` | - | dashscope API Key（必需） |
| `RUN_DASHSCOPE_IT` | - | 设置为 `1` 启用测试（必需） |
| `DASHSCOPE_TOP_N` | `10` | embedding 召回 top-N 数量 |
| `DASHSCOPE_MAX_QUERIES` | 无限制 | 最大测试用例数（用于快速试跑） |
| `DASHSCOPE_LLM_MODEL` | `qwen-flash` | LLM 模型名称 |
| `DASHSCOPE_EMBEDDING_MODEL` | `text-embedding-v4` | embedding 模型名称 |

## 测试用例

测试用例定义在 `tests/dashscope_integration_queries.json`，包含 34 条真实中文 query，每条用例包含：

- `query`: 用户输入文本
- `expected_capability_ids`: 期望命中的命令 ID 列表
- `expected_fields`: 期望的 QueryIR 字段（scope_include/scope_exclude/quantifier/type_hint 等）

## 测试内容

### 1. LLM 解析测试 (TestDashScopeLLMIntegration)

- `test_llm_parse_action_text_coverage`: 验证 action.text 非空覆盖率（阈值 60%）
- `test_llm_parse_scope_include`: 验证 scope_include 解析准确率（阈值 60%）

### 2. Embedding 召回测试 (TestDashScopeEmbeddingIntegration)

- `test_embedding_recall_with_action_text`: 使用 QueryIR.action.text 进行召回（主路径）
- `test_embedding_recall_with_raw_query`: 使用原始 query 进行召回（对照组）

召回流程：
1. 调用 LLM 得到 QueryIR
2. 优先使用 `QueryIR.action.text`，为空则 fallback 到原始 query
3. 执行 embedding 检索
4. 验证期望命令 ID 出现在 top-N 中

### 3. Pipeline 端到端测试 (TestDashScopePipelineIntegration)

- `test_end_to_end_pipeline`: 验证完整 LLM + embedding 流程

## 断言阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| action.text 覆盖率 | ≥ 60% | LLM 输出可用于召回的意图短语 |
| scope_include 准确率 | ≥ 60% | LLM 解析房间/范围 |
| top-N 召回命中率 | ≥ 60% | embedding 检索命中 |

阈值设置较宽松，允许模型微调/网络波动带来的偏差。

## 数据来源

- 命令库: `src/spec.jsonl` 中的 profile/capabilities
- 命令文档: `capability.id + capability.description`

## 注意事项

1. **配额消耗**: 每次测试会消耗 dashscope API 配额，建议使用 `DASHSCOPE_MAX_QUERIES` 限制用例数
2. **网络延迟**: 测试包含 `time.sleep(0.1)` 避免请求过快
3. **CI 环境**: CI 默认跳过，避免引入外部依赖
4. **稳定性**: 使用 top-N 命中而非精确分数断言，降低波动影响
