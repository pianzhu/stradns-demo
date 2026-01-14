# API 手册

## 概述
本项目暂无对外 HTTP API，以下记录核心内部接口，便于模块协作与测试。

---

## 接口列表

### command_parser

#### parse_command_output
**描述:** 解析大模型输出文本为结构化命令列表。

**输入:** 原始文本（字符串，JSON array<object> 或 array<string>）
**输出:** ParseResult（命令列表、错误列表、降级状态）

---

### context_retrieval

#### compile_ir
**描述:** 将自然语言编译为 QueryIR。

#### retrieve
**描述:** 基于 QueryIR 执行检索与排序，返回候选设备/动作。
