# 数据模型

## 概述
项目以本地 JSON/JSONL 文件作为输入数据与测试样本，不依赖持久化数据库。

---

## 数据表/集合

### spec.jsonl
**描述:** 设备能力与规格索引，用于检索与匹配。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 能力或文档标识 |
| name | string | 名称 |
| content | string | 规格内容 |

### tests/integration/*.jsonl / tests/integration/*.json
**描述:** 集成测试与回归用例。
