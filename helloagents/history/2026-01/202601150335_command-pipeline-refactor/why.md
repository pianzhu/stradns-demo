# 变更提案: 命令数组解析与检索管线重构

## 需求背景

LLM 输出已稳定为 JSON 命令数组（`a/s/n/t/q/c`），但现有检索流程仍依赖 QueryIR JSON 对象，且 `command_parser` 通过字符串桥接造成解析偏差与维护负担。需要统一协议入口、移除冗余提示词，并支持多命令逐条检索。

## 变更内容
1. 重写 `command_parser`：仅接受 JSON 命令对象数组，移除 legacy 字符串输入与对象→字符串桥接；解析失败统一降级为 UNKNOWN 并记录 errors。
2. 移除 `ir_compiler` 的内置 system prompt，改为调用侧注入。
3. 引入“命令 → QueryIR”映射层，支持多命令逐条检索与 `s/n/t/q/c` 的严格映射。
4. `pipeline.retrieve` 统一返回多命令结果（MultiRetrievalResult），新增 `retrieve_single` 作为显式单命令兼容入口。
5. 全面重构测试用例：以命令数组协议为准，清理历史 slop code 与隐式分支。

## 影响范围
- **模块:** command_parser, context_retrieval
- **文件:** src/command_parser/*, src/context_retrieval/*, tests/*
- **API:** `pipeline.retrieve` 返回结构调整；新增 `retrieve_single`
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

### 需求: 多命令返回结构
**模块:** context_retrieval
统一输出多命令检索结果并保留单命令兼容入口。

#### 场景: 单命令兼容检索
- 输入为单命令数组
- 期望 `retrieve_single` 返回原 `RetrievalResult`，`retrieve` 返回单条 Multi 结果

## 风险评估
- **风险:** 检索接口返回结构变化影响调用方
- **缓解:** 提供 `retrieve_single` 显式兼容入口，配套更新测试与文档
