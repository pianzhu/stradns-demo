# 项目技术约定

---

## 技术栈
- **核心:** Python >=3.13
- **主要依赖:** strands-agents, mcp, anthropic, dashscope, numpy, pyyaml, rapidfuzz

---

## 开发约定
- **代码规范:** 以现有模块风格为准，保持清晰的类型注解与模块分层
- **命名约定:** 变量与函数使用 snake_case，类使用 PascalCase

---

## 错误与日志
- **策略:** 解析失败与降级路径需记录错误原因
- **日志:** 使用标准库 logging

---

## 测试与流程
- **测试:** unittest 为主，按模块覆盖关键路径与退化路径
- **测试命令:** 见 `tests/TESTING.md`
- **提交:** 未发现统一提交规范，按团队约定补充
