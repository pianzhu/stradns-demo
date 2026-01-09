# 设计：dashscope 集成测试

## 范围与模型
- LLM：`qwen-flash`，使用现有 `DashScopeLLM`，系统提示沿用当前 schema（action、name_hint、scope/type_hint、quantifier、references、confidence）。
- Embedding：`text-embedding-v4`，通过 `DashScopeEmbeddingModel` → `InMemoryVectorSearcher`，输入命令描述。
- 数据：
  - `src/spec.jsonl`（内容为 JSON 数组）中的 profile/capabilities 作为命令库
  - 独立维护真实中文 query 用例集（默认不少于 30 条），每条用例包含 query 与期望命令 ID（capability.id）及可选的期望解析字段

## 测试形态
- 类型：集成测试（标记 slow/optional），需 `DASHSCOPE_API_KEY`；无 key 则 skip。
- LLM 解析测试：对每个 query 调用 qwen，校验输出字段是否命中预期（action；name_hint；scope/type_hint；quantifier）；并输出覆盖率统计（例如 action 非空比例）。
- Embedding 测试：
  - 主路径：先用 LLM 得到 QueryIR，优先使用 `QueryIR.action`（为空则 fallback 原始 query）作为 embedding 查询文本
  - 断言口径：以“期望 capability.id 命中 top-N”为准（默认 N=10，可调），并输出 top-N 命中率
- Pipeline 端到端（可选）：通过 dashscope LLM + embedding 构造一个完整检索，断言设备候选 top5 内包含期望设备（若具备映射），reason 含 semantic_match。

## 运行策略
- 入口：单独的集成测试文件，使用 env flag（如 `RUN_DASHSCOPE_IT=1`）控制执行，避免默认跑慢/耗费配额。
- 环境：依赖 `DASHSCOPE_API_KEY`；可选自定义模型名/阈值通过 env 或测试常量。
- 规模控制：支持通过 env 控制最大用例数、top-N、索引规模（例如限制 profile 数量）以便快速试跑或扩量压测。
- 稳定性：
  - 尽量使用确定性推理参数（如 temperature=0）降低随机性
  - 对网络/解析失败提供有限重试
  - 断言采用 top-N 命中而非精确分数，降低不同时间/模型微调带来的波动
