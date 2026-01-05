# 提案：dashscope LLM/Embedding 集成测试

## 为什么

- 目前仅有 Fake/Mock 覆盖，缺少真实 dashscope（qwen-flash + text-embedding-v4）端到端验证，无法发现提示词/相似度阈值/真实中文语料的偏差。
- 需要在本地可重复地验证“真实 LLM 解析 QueryIR + 真实 embedding 搜索命令”的效果，提前暴露问题，指导参数与提示优化。

## 变更内容

- 新增基于 dashscope 在线模型的集成测试用例（本地手动运行），覆盖 **LLM 解析 QueryIR → 使用 QueryIR.action.text 做 embedding 检索** 的主路径。
- 复用 `src/spec.jsonl` 的真实命令描述作为 embedding 侧的基准数据，并以“可扩展”的真实中文 query 用例集驱动测试（默认不少于 30 条，可配置规模）。
- 通过标准以“命令 ID 命中 top-N”为主（默认 top10，可配置），避免“命令或设备”混合口径导致断言不明确。
- 提供可跳过/可配置的测试入口：依赖 `DASHSCOPE_API_KEY`，并使用运行开关（如 `RUN_DASHSCOPE_IT=1`）避免默认执行带来的耗时/耗费配额。

## 影响

- 仅新增测试与测试依赖说明，不修改运行时逻辑。
- 需要在本地具备 dashscope 访问能力；CI 默认跳过，避免引入外部依赖。
