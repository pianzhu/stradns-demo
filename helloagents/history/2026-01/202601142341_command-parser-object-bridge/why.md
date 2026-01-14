# 变更提案: 提示词对象输出的下游兼容与测试更新

## 需求背景
指令解析提示词已改为输出 JSON 对象数组（字段 a/s/n/t/q/c），需要同步更新解析入口、回归用例与文档，保证解析稳定性与召回率，并避免新旧格式切换时的回归风险。

## 变更内容
1. 在解析入口增加对象数组的预处理转换，保持现有字符串解析逻辑不变。
2. 更新 prompt 回归用例与单元测试，覆盖对象输出与兼容场景。
3. 同步更新协议与测试文档，避免契约描述滞后。

## 影响范围
- **模块:** command_parser
- **文件:** src/command_parser/parser.py, src/command_parser/prompt.py, tests/test_command_parser.py, tests/README_dashscope_integration.md, docs/plans/2026-01-09-command-parser-system-prompt-plan.md, openspec/changes/improve-command-parser/*
- **API:** parse_command_output 的输入格式支持扩展
- **数据:** 无

## 核心场景

### 需求: 对象输出兼容解析
**模块:** command_parser
将 JSON 对象数组转换为既有三段式字符串后再解析，保持降级与校验逻辑。

#### 场景: 单条对象输出
给定提示词返回 `[{"a":"打开","s":"卧室","n":"顶灯","t":"Light","q":"one"}]`  
解析结果应与旧字符串一致，生成一条 ParsedCommand，且不影响降级机制。

### 需求: 回归与文档同步
**模块:** command_parser / tests / docs
更新 PROMPT_REGRESSION_CASES 与集成测试说明，确保输出契约与提示词一致。

#### 场景: 文档契约一致
在说明文档中明确对象数组输出与字段含义，并标注兼容旧字符串数组的策略。

## 风险评估
- **风险:** 对象输出字段缺失或包含分隔符导致解析失败  
- **缓解:** 预处理阶段补默认值并清理非法分隔符；对非法条目降级处理
