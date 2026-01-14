# context_retrieval

## 目的
将解析后的语义信息用于设备检索与排序，输出可执行的候选结果。

## 模块概述
- **职责:** 语义编译、范围过滤、关键词/向量检索、评分融合
- **状态:** ✅稳定
- **最后更新:** 2025-01-14

## 规范

### 需求: 语义检索流水线
**模块:** context_retrieval
根据 QueryIR 与设备列表输出候选结果。

#### 场景: 设备召回
在给定设备清单与用户指令时，输出匹配的设备与命令能力。
- 先做语义编译与房间过滤
- 结合关键词与向量检索排序

## API接口
### compile_ir
**描述:** 调用大模型将文本解析为 QueryIR

### retrieve
**描述:** 组合检索策略并返回候选结果

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

## 依赖
- dashscope
- rapidfuzz
- numpy

## 变更历史
- 初始化知识库
