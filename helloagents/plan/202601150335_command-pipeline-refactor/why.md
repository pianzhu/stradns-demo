# 变更提案: 命令数组解析与检索管线重构

## 需求背景

LLM 输出已稳定为 JSON 命令数组（`a/s/n/t/q/c`），但现有检索流程仍依赖 QueryIR JSON 对象，且 `command_parser` 通过字符串桥接造成解析偏差与维护负担。需要统一协议入口、移除冗余提示词，并支持多命令逐条检索。

## 变更内容
1. 重写 `command_parser`，直接解析 JSON 数组对象，严格校验并可降级。
2. 移除 `ir_compiler` 的内置 system prompt，改为调用侧注入。
3. 引入“命令 → QueryIR”映射层，支持多命令独立检索。
4. 调整检索管线与模型层结构，更新测试覆盖。

## 影响范围
- **模块:** command_parser, context_retrieval
- **文件:** src/command_parser/*, src/context_retrieval/*, tests/*
- **API:** pipeline.retrieve 返回结构可能调整
- **数据:** 无持久化变更

## 核心场景

### 需求: 命令数组解析
**模块:** command_parser
解析 LLM 输出的 JSON 数组对象并产出结构化命令。

#### 场景: 单命令对象解析
- 输入为单条命令对象数组
- 期望解析结果包含 action/scope/name/type/quantifier/count

### 需求: Scope 排除解析
**模块:** command_parser
支持 `s` 的通配、包含与排除语义。

#### 场景: 解析通配与排除
- 输入 `s="*,!卧室"`
- 期望 include 视为通配，exclude 包含“卧室”

### 需求: 多命令检索拆分
**模块:** context_retrieval
按命令顺序逐条构建 QueryIR 并检索。

#### 场景: 多命令逐条检索
- 输入包含多个命令
- 期望每条命令单独检索且结果顺序一致

## 风险评估
- **风险:** 检索接口返回结构变化影响调用方
- **缓解:** 提供兼容开关或包装结构，配套更新测试与文档
