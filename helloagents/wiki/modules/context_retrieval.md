# context_retrieval

## 目的
将解析后的语义信息用于设备检索与排序，输出可执行的候选结果。

## 模块概述
- **职责:** 命令映射、范围过滤、关键词/向量检索、评分融合
- **状态:** ✅稳定
- **最后更新:** 2026-01-16

## 规范

### 需求: 语义检索流水线
**模块:** context_retrieval
根据命令映射出的 QueryIR 与设备列表输出候选结果。

#### 场景: 设备召回
在给定设备清单与用户指令时，输出匹配的设备与命令能力。
- 先做语义编译与房间过滤
- 结合关键词与向量检索排序

### 注意事项
- 根因: bulk 查询文本拼接泛化 name_hint，且缺少向量检索器/spec_index 时提前返回，导致候选为空。
- 修复: 增加 bulk 可用性判定，查询文本改为基于原始问题清洗后的动作片段。
- 预防: 以单元测试覆盖 bulk 兜底与查询清洗路径。

## API接口
### compile_ir
**描述:** 将结构化命令映射为 QueryIR

### retrieve
**描述:** 组合检索策略并返回多命令结果（MultiRetrievalResult）

### retrieve_single
**描述:** 单命令兼容入口，返回 RetrievalResult

## 数据模型
### QueryIR
| 字段 | 类型 | 说明 |
|------|------|------|
| action | string | 动作意图 |
| name_hint | string | 设备名称提示 |
| scope_include | list | 包含房间 |
| scope_exclude | list | 排除房间 |
| quantifier | string | 量词 |
| type_hint | string | 设备类型 |
| meta | object | 附加元信息（如 count） |

### MultiRetrievalResult
| 字段 | 类型 | 说明 |
|------|------|------|
| commands | list | 按命令顺序的检索结果 |
| errors | list | 命令解析错误 |
| degraded | bool | 命令解析是否降级 |

### CommandRetrieval
| 字段 | 类型 | 说明 |
|------|------|------|
| command | ParsedCommand | 命令解析结果 |
| ir | QueryIR | 映射后的检索 IR |
| result | RetrievalResult | 单条命令检索结果 |

## 依赖
- dashscope
- rapidfuzz
- numpy

## 变更历史
- 初始化知识库
- 2026-01-16 修复 bulk 查询清洗与兜底策略
- 2026-01-16 补充检索流水线与批量逻辑的函数注释
