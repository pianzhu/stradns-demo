# 功能：上下文检索

## 概述

智能家居设备上下文检索系统：先用**大模型**将用户请求解析为结构化 QueryIR（动作、量词、排除、指代等），再基于设备元数据（`type`/`room`/`name`）与动作-能力匹配，在本地设备列表中召回并筛选最少且必要的实体用于 prompt 注入。

## 设计原则

- **澄清判断交给大模型**：检索只返回候选列表 + 轻量 hint，是否澄清由后续大模型决定
- **语义解析使用 LLM**：调用大模型解析自然语言为 QueryIR，不使用规则匹配
- **向量相似度匹配**：命令一致性校验使用向量相似度而非关键词映射

## 新增需求

### 需求：语义解析（LLM）

系统必须使用大模型将用户查询解析为结构化 QueryIR，并保证输出满足约定的 JSON schema（仅字段，不含自由文本推理），且返回解析置信度。

#### 场景：解析动作与名称

- 给定：用户查询"打开老伙计"
- 当：进行 LLM 语义解析
- 则：action.text 应为 "打开"
- 且：name_hint 应为 "老伙计"

#### 场景：解析量词与范围

- 给定：用户查询"关闭所有卧室的灯"
- 当：进行 LLM 语义解析
- 则：action.text 应为 "关闭"
- 且：quantifier 应为 "all"
- 且：scope_include 应包含 "卧室"
- 且：type_hint 应为 "light"

#### 场景：解析排除语义

- 给定：用户查询"打开除卧室以外的灯"
- 且：已知房间列表包含"卧室"
- 当：进行 LLM 语义解析
- 则：quantifier 应为 "except"
- 且：scope_exclude 应包含 "卧室"

#### 场景：解析指代

- 给定：用户查询"打开那个"
- 当：进行 LLM 语义解析
- 则：references 应包含 "last-mentioned"

### 需求：按 type/room/name 召回候选

系统必须根据 QueryIR 中的 `name_hint`、`room`（scope include/exclude）与 `type_hint` 在设备元数据上召回候选，并为候选提供可解释的 reasons（例如：name_hit、room_hit、type_hit）。

#### 场景：名称精确命中优先

- 给定：设备列表包含名为"老伙计"的设备
- 当：用户查询"打开老伙计"
- 且：QueryIR.name_hint="老伙计"
- 则：候选应包含该设备
- 且：reasons 应包含 "name_hit"

#### 场景：房间 + 类型组合命中

- 给定：设备列表包含卧室灯与客厅灯
- 当：用户查询"打开卧室的灯"
- 且：QueryIR.scope_include 包含"卧室"
- 且：QueryIR.type_hint="light"
- 则：候选应只包含卧室灯
- 且：reasons 应包含 "room_hit"
- 且：reasons 应包含 "type_hit"

### 需求：命令一致性校验（向量相似度）

系统必须根据 QueryIR.action 识别目标动作，并使用**向量相似度**将动作意图与设备的 CommandSpec.description 进行匹配，用于候选筛选与排序。

**设计变更**：使用向量相似度匹配而非关键词映射，以获得更好的泛化性。

#### 场景：动作与命令描述相似度匹配

- 给定：设备有命令 description="打开设备"
- 且：action 查询为"打开"
- 当：计算相似度
- 则：相似度应高于阈值（如 0.5）

#### 场景：无匹配命令被过滤

- 给定：设备只有命令 description="读取温度"
- 且：action.text = "打开"
- 且：提供了 similarity_func
- 当：执行能力过滤
- 则：该设备应被过滤

### 需求：Scope 预过滤

系统必须在召回前根据 IR 的 scope_include 和 scope_exclude 过滤设备。

#### 场景：排除指定房间

- 给定：设备列表包含卧室灯和客厅灯
- 且：IR 的 scope_exclude 包含"卧室"
- 当：执行 scope 过滤
- 则：结果应只包含客厅灯

#### 场景：仅包含指定房间

- 给定：设备列表包含卧室灯、客厅灯、厨房灯
- 且：IR 的 scope_include 包含"客厅"
- 当：执行 scope 过滤
- 则：结果应只包含客厅灯

## 相关功能

- [gating](../gating/spec.md)
- [injection](../injection/spec.md)
