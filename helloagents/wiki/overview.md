# strands-demo

> 本文件包含项目级别的核心信息。详细的模块文档见 `modules/` 目录。

---

## 1. 项目概述

### 目标与背景
本项目用于演示智能家居指令解析与召回流程，将自然语言转换为可执行的结构化命令与设备候选。

### 范围
- **范围内:** 指令解析、结构化输出校验、设备检索与排序、集成测试
- **范围外:** 真实设备控制、账号与权限体系、持久化配置管理

### 干系人
- **负责人:** Xuanwo

---

## 2. 模块索引

| 模块名称 | 职责 | 状态 | 文档 |
|---------|------|------|------|
| command_parser | 解析大模型输出为结构化命令 | ✅稳定 | [modules/command_parser.md](modules/command_parser.md) |
| context_retrieval | 语义解析与设备检索流水线 | ✅稳定 | [modules/context_retrieval.md](modules/context_retrieval.md) |

---

## 3. 快速链接
- [技术约定](../project.md)
- [架构设计](arch.md)
- [API 手册](api.md)
- [数据模型](data.md)
- [变更历史](../history/index.md)
