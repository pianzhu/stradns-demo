# command_parser

## 目的
将大模型输出解析为结构化命令，提供可校验的动作、范围与目标槽位。

## 模块概述
- **职责:** 解析 JSON 输出、校验字段、降级与兜底
- **状态:** ✅稳定
- **最后更新:** 2026-01-14

## 规范

### 需求: 指令解析协议
**模块:** command_parser
解析大模型输出，支持对象数组与旧字符串数组的兼容解析与降级处理。

#### 场景: 结构化输出解析
输入为 JSON 数组（对象字段 a/s/n/t/q/c 或旧字符串），输出为 ParsedCommand 列表。
- 若条目非法，记录错误并降级
- 若全部无效，输出 UNKNOWN 兜底

## API接口
### parse_command_output
**描述:** 解析原始输出为结构化命令
**输入:** 字符串输出
**输出:** ParseResult

## 数据模型
### ParsedCommand
| 字段 | 类型 | 说明 |
|------|------|------|
| action | string | 动作 |
| scope | ScopeSlot | 包含/排除房间 |
| target | TargetSlot | 目标槽位 |
| raw | string | 原始命令表示 |

## 依赖
- context_retrieval.category_gating

## 变更历史
- 初始化知识库
- [202601142341_command-parser-object-bridge](../../history/2026-01/202601142341_command-parser-object-bridge/) - 提示词对象输出兼容与测试更新
