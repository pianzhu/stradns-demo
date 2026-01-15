# 变更：重构指令解析与检索管线（命令数组协议）

## 为什么

当前检索管线直接依赖 LLM 输出 QueryIR JSON 对象，但实际的 LLM 输出协议已统一为命令数组（`a/s/n/t/q/c`）。现有 `command_parser` 通过“对象 → 字符串 → 解析”的桥接方式增加了错误率，且 `ir_compiler` 仍内置 system prompt，导致提示词分散与维护成本上升。

## 变更内容

- 移除 `ir_compiler` 内置 system prompt，统一由调用侧提供命令数组提示词。
- 重写 `command_parser`：直接解析 JSON 数组对象，完善 `s` 范围规则与降级逻辑。
- 引入“命令 → QueryIR”映射层，支持多命令独立检索。
- 调整检索管线与模型层结构以适配多命令返回。
- 更新单元/集成测试以覆盖新协议与多命令路径。

## 影响

- 受影响规范：`context-retrieval`
- 受影响代码：`src/command_parser/`、`src/context_retrieval/`、`tests/`
- 依赖：命令数组输出协议（参考变更 `improve-command-parser`）
