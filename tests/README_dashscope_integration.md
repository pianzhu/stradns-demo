# dashscope 集成测试说明

## 概述

使用真实的 dashscope API（qwen-flash + text-embedding-v4）进行端到端验证，覆盖 **LLM 解析 QueryIR → 使用 QueryIR.action 做 embedding 检索** 的主路径。

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

- `test_llm_parse_action_text_coverage`: 验证 action 非空覆盖率（阈值 60%）
- `test_llm_parse_scope_include`: 验证 scope_include 解析准确率（阈值 60%）

### 2. Embedding 召回测试 (TestDashScopeEmbeddingIntegration)

- `test_embedding_recall_with_action_text`: 使用 QueryIR.action 进行召回（主路径）
- `test_embedding_recall_with_raw_query`: 使用原始 query 进行召回（对照组）

召回流程：
1. 调用 LLM 得到 QueryIR
2. 优先使用 `QueryIR.action`，为空则 fallback 到原始 query
3. 执行 embedding 检索
4. 验证期望命令 ID 出现在 top-N 中

### 3. Pipeline 端到端测试 (TestDashScopePipelineIntegration)

- `test_end_to_end_pipeline`: 验证完整 LLM + embedding 流程

## 断言阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| action 覆盖率 | ≥ 60% | LLM 输出可用于召回的意图短语 |
| scope_include 准确率 | ≥ 60% | LLM 解析房间/范围 |
| top-N 召回命中率 | ≥ 60% | embedding 检索命中 |

阈值设置较宽松，允许模型微调/网络波动带来的偏差。

## 最新测试结果

### 测试运行记录（2026-01-06）

**运行命令**：
```bash
DASHSCOPE_MAX_QUERIES=5 RUN_DASHSCOPE_IT=1 PYTHONPATH=src uv run python -m unittest tests.test_dashscope_integration -v
```

**运行时间**：36.283 秒
**测试数量**：5 个测试
**结果**：4 通过，1 失败

#### LLM 解析测试结果 ✅

| 指标 | 结果 | 阈值 | 状态 |
|------|------|------|------|
| action 覆盖率 | 100% (5/5) | ≥60% | ✅ 通过 |
| scope_include 准确率 | 100% (3/3) | ≥60% | ✅ 通过 |

**LLM 输出示例**：
- `打开客厅的灯` → action: "打开" / "open"
- `关闭卧室所有灯光` → action: "close"
- `把客厅灯光调到50%` → action: "adjust"
- `调整灯光亮度` → action: "调整"
- `设置灯光色温为暖白色` → action: "设置"

#### Embedding 召回测试结果 ⚠️

| 指标 | 结果 | 阈值 | 状态 |
|------|------|------|------|
| action → top-10 命中率 | 40% (2/5) | ≥60% | ❌ 未达标 |
| raw query → top-10 命中率 | 40% (2/5) | - | 对照组 |

**未命中用例分析**：

1. **打开客厅的灯**
   - search_text: `open`
   - 期望命令: `main-switch-on`
   - 实际 top-3: `main-windowShade-open`（窗帘打开）
   - 问题：英文动词 "open" 与窗帘命令语义更接近

2. **把客厅灯光调到50%**
   - search_text: `adjust`
   - 期望命令: `main-switchLevel-setLevel`
   - 实际 top-3: `main-windowShadeTiltLevel-setShadeTiltLevel`（窗帘调节）
   - 问题：英文动词 "adjust" 过于泛化

3. **调整灯光亮度**
   - search_text: `adjust`
   - 期望命令: `main-switchLevel-setLevel`
   - 实际 top-3: `main-windowShadeTiltLevel-setShadeTiltLevel`（窗帘调节）
   - 问题：同上

#### Pipeline 端到端测试结果

| 指标 | 结果 |
|------|------|
| action 覆盖率 | 100.00% |
| action fallback 率 | 0.00% |
| top-10 召回命中率 | 20.00% |
| action 非空且召回命中率 | 20.00% |

### 关键问题发现

#### 1. LLM 返回英文动词而非中文意图短语

**问题描述**：LLM 在解析中文查询时，部分返回英文单词（如 "open", "close", "adjust"）而非中文短语（如 "打开", "关闭", "调整"）。

**影响**：
- 英文动词过于泛化，导致语义歧义
- 与中文命令描述匹配度低
- 降低 embedding 召回准确率

**示例**：
```
输入：打开客厅的灯
期望 action：打开
实际 action：open
结果：误匹配到 windowShade-open（窗帘）而非 switch-on（开关）
```

#### 2. 命令描述语义相似导致误匹配

**问题描述**：不同设备类型的命令使用相似的动词（如 open, adjust），缺乏上下文区分。

**影响**：
- "open" 同时匹配灯开关和窗帘打开
- "adjust" 同时匹配灯光亮度和窗帘角度

**示例**：
```
命令 A: main-switch-on (description: 打开设备)
命令 B: main-windowShade-open (description: 打开窗帘)
查询 action: "open" → 更接近命令 B
```

### 优化建议

#### 短期优化（Prompt 工程）

1. **强化中文输出约束**
   - 在系统提示中明确要求使用中文动词短语
   - 添加示例："打开"、"关闭"、"调整"、"设置"

2. **增加上下文提示**
   - 引导 LLM 输出更具体的意图短语
   - 例如："调整亮度" 而非 "adjust"

3. **优化 JSON Schema**
   - 在 action 字段添加描述说明
   - 明确中文短语的期望格式

#### 中期优化（数据质量）

1. **改进命令描述**
   - 为命令添加设备类型前缀
   - 例如："打开灯光开关" vs "打开窗帘"

2. **扩展测试用例**
   - 增加更多边界情况
   - 覆盖不同设备类型的相似命令

3. **混合检索策略**
   - 结合原始中文查询和提取的 action
   - 使用设备类型信息辅助过滤

#### 长期优化（架构改进）

1. **多阶段检索**
   - 第一阶段：粗召回（使用原始查询）
   - 第二阶段：精排序（使用 action + 设备类型）

2. **上下文感知 Embedding**
   - 训练或微调针对智能家居领域的 embedding 模型
   - 增强对设备类型的区分能力

3. **动态阈值调整**
   - 根据查询复杂度自适应调整召回策略
   - 简单查询使用精确匹配，复杂查询使用语义召回

## 数据来源

- 命令库: `src/spec.jsonl` 中的 profile/capabilities
- 命令文档: `capability.id + capability.description`

## 注意事项

1. **配额消耗**: 每次测试会消耗 dashscope API 配额，建议使用 `DASHSCOPE_MAX_QUERIES` 限制用例数
2. **网络延迟**: 测试包含 `time.sleep(0.1)` 避免请求过快
3. **CI 环境**: CI 默认跳过，避免引入外部依赖
4. **稳定性**: 使用 top-N 命中而非精确分数断言，降低波动影响
