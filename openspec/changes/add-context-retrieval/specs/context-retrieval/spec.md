# 功能：上下文检索

## 概述

智能家居设备上下文检索系统，支持混合召回（Keyword + Vector）、语义编译、评分融合。

## 新增需求

### 需求：混合召回

系统必须支持 Keyword 和 Vector 两路并行召回，并将结果融合。

#### 场景：Keyword 召回匹配设备名称

- 给定：设备列表包含名为"老伙计"的设备
- 当：用户查询"打开老伙计"
- 则：Keyword 召回应返回该设备
- 且：keyword_score 应为 1.0（精确匹配）

#### 场景：Keyword 召回匹配房间

- 给定：设备列表包含房间为"卧室"的设备
- 当：用户查询"打开卧室的灯"
- 则：Keyword 召回应返回该设备
- 且：reasons 应包含 "room_hit"

#### 场景：Vector 召回返回相似设备

- 给定：向量索引包含设备向量
- 当：使用查询向量搜索
- 则：应返回 cosine 相似度最高的设备

### 需求：评分融合

系统必须将 Keyword 和 Vector 召回结果融合，计算统一的 total_score。

#### 场景：Keyword 和 Vector 结果合并

- 给定：Keyword 召回返回设备 A（score=1.0）
- 且：Vector 召回返回设备 A（score=0.2）
- 当：执行评分融合
- 则：设备 A 的 total_score = 1.0 * 1.0 + 0.2 * 0.3 = 1.06

### 需求：IR 语义编译

系统必须将用户查询编译为中间表示（QueryIR），支持动作、量词、排除、指代、条件。

#### 场景：识别打开动作

- 给定：用户查询"打开那个"
- 当：编译 IR
- 则：action.kind 应为 "open"

#### 场景：识别排除语义

- 给定：用户查询"打开除卧室以外的灯"
- 且：已知房间列表包含"卧室"
- 当：编译 IR
- 则：quantifier 应为 "except"
- 且：scope_exclude 应包含"卧室"

#### 场景：识别指代

- 给定：用户查询"打开那个"
- 当：编译 IR
- 则：references 应包含 "last-mentioned"

### 需求：Scope 预过滤

系统必须在召回前根据 IR 的 scope_include 和 scope_exclude 过滤设备。

#### 场景：排除指定房间

- 给定：设备列表包含卧室灯和客厅灯
- 且：IR 的 scope_exclude 包含"卧室"
- 当：执行 scope 过滤
- 则：结果应只包含客厅灯

### 需求：命令一致性校验

系统必须根据用户意图过滤无法执行该动作的设备。

#### 场景：高置信时硬过滤

- 给定：设备列表包含窗帘（可打开）和温度传感器（不可打开）
- 且：IR confidence >= 0.8
- 且：action.kind = "open"
- 当：执行能力过滤（hard=true）
- 则：结果应只包含窗帘

## 相关功能

- [gating](../gating/spec.md)
- [injection](../injection/spec.md)
