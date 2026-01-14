# 任务清单: 提示词对象输出的下游兼容与测试更新

目录: `helloagents/plan/202601142341_command-parser-object-bridge/`

---

## 1. command_parser 兼容改造
- [√] 1.1 在 `src/command_parser/parser.py` 中增加对象数组预处理，转换为三段式字符串后复用现有解析逻辑，验证 why.md#需求-对象输出兼容解析-场景-单条对象输出
- [√] 1.2 更新 `src/command_parser/prompt.py` 的 `PROMPT_REGRESSION_CASES` 为对象数组期望值，补充/校正泛指类型与默认值，验证 why.md#需求-对象输出兼容解析-场景-单条对象输出

## 2. 测试与回归
- [√] 2.1 更新 `tests/test_command_parser.py` 以覆盖对象数组输出与兼容字符串数组路径，验证 why.md#需求-对象输出兼容解析-场景-单条对象输出
- [√] 2.2 校正文档中的契约描述与测试说明，验证 why.md#需求-回归与文档同步-场景-文档契约一致

## 3. 文档与规范同步
- [√] 3.1 更新 `docs/plans/2026-01-09-command-parser-system-prompt-plan.md` 描述为对象数组输出
- [√] 3.2 更新 `tests/README_dashscope_integration.md` 中的输出契约说明
- [√] 3.3 更新 `openspec/changes/improve-command-parser/specs/command-parser/spec.md` 与相关变更文档以匹配对象输出

## 4. 安全检查
- [√] 4.1 检查对象字段的分隔符清理与降级路径，避免解析注入与崩溃

## 5. 测试
- [√] 5.1 运行 `python -m unittest tests.test_command_parser`（预期全部通过）
