## 1. 实施
- [ ] 1.1 重写 `command_parser` 的对象数组解析与 `s` 范围规则，补齐降级逻辑
- [ ] 1.2 在 `context_retrieval` 增加命令到 QueryIR 的映射层，移除 `ir_compiler` 内置 prompt
- [ ] 1.3 重构检索管线以支持多命令逐条检索，并更新返回结构
- [ ] 1.4 更新单元测试与集成测试（command_parser/ir_compiler/pipeline）
