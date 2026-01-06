# 上下文检索规范增量

## 新增需求

### 需求：Category Gating 预过滤

系统必须在 embedding 检索前，优先根据 `QueryIR.type_hint` 进行 category 过滤。

#### 场景：type_hint 映射成功

- **当** QueryIR.type_hint 为 "灯"
- **那么** 系统将 type_hint 映射为 category "Light"
- **并且** 仅保留 category 为 "Light" 的设备进入 embedding 检索

#### 场景：type_hint 映射失败

- **当** QueryIR.type_hint 为 "智能设备"（无对应 category）
- **那么** 系统跳过 category 过滤
- **并且** 全量设备进入 keyword 检索路径

#### 场景：type_hint 为空

- **当** QueryIR.type_hint 为 None
- **那么** 系统跳过 category 过滤
- **并且** 优先使用 keyword 模糊匹配 name/room

### 需求：scope_include 评分加权

系统必须将 `QueryIR.scope_include` 作为评分加权因素，而非硬过滤条件，以避免遗漏自定义名称中包含房间信息的设备。

#### 场景：房间匹配加分

- **当** QueryIR.scope_include 包含 "客厅"
- **并且** 设备 room 字段为 "客厅"
- **那么** 该设备在融合评分时获得额外加权

#### 场景：自定义名称包含房间词

- **当** 设备名为 "客厅老伙计"，room 字段为空或其他值
- **并且** QueryIR.scope_include 包含 "客厅"
- **那么** 设备不会被硬过滤排除
- **并且** keyword 检索可通过名称模糊匹配召回该设备

### 需求：文档富化

系统必须使用 spec.jsonl 中的 capability 描述构建语义丰富的 embedding 文档。

#### 场景：构建富化文档

- **当** 设备 profile.id 在 spec.jsonl 中存在
- **那么** 系统为每个 capability 构建独立文档
- **并且** 文档包含 category、capability_id、description 和同义词扩展

#### 场景：spec 不存在时降级

- **当** 设备 profile.id 在 spec.jsonl 中不存在
- **那么** 系统使用设备原始信息（name/room/type）构建文档
- **并且** 记录警告日志

#### 场景：带参数命令的文档构建

- **当** capability 包含 value_list（如空调模式）
- **那么** 系统将 value_list 中所有参数的 description 拼接到命令文档
- **并且** 文档格式为 "{命令描述} {参数1描述} {参数2描述} ..."

#### 场景：参数描述语义匹配

- **当** 用户查询 "空调制冷"
- **并且** 命令文档为 "设置空调模式 制冷 制热"
- **那么** 该命令能被召回
- **因为** "制冷" 出现在文档中

### 需求：同义词归一化

系统必须对 capability description 进行同义词扩展，以提高查询覆盖率。

#### 场景：动词同义词扩展

- **当** capability description 为 "电源启用"
- **那么** 系统扩展为 "电源启用 打开 开 开启 启动 on"

#### 场景：无匹配同义词

- **当** capability description 无匹配的同义词规则
- **那么** 系统保持原始 description 不变

### 需求：命令级索引

系统必须以命令（capability）为粒度构建 embedding 索引，而非设备级。

#### 场景：命令级检索结果

- **当** 用户查询 "打开灯"
- **那么** 检索结果包含 `(device_id, capability_id)` 元组
- **并且** 每个结果对应具体命令而非设备

#### 场景：同设备多命令匹配

- **当** 设备有 switch-on 和 switchLevel-setLevel 两个命令
- **并且** 用户查询 "调亮度"
- **那么** switchLevel-setLevel 命令排名高于 switch-on

## 修改需求

### 需求：混合召回

系统必须支持 Keyword 和 Vector 混合召回，根据 category gating 结果调整策略。

#### 场景：category gating 有效时

- **当** type_hint 成功映射为 category
- **那么** keyword 权重为 1.0，vector 权重为 0.5
- **并且** 在过滤后的候选集上执行 embedding 检索

#### 场景：category gating 无效时

- **当** type_hint 为空或映射失败
- **那么** keyword 权重为 1.5，vector 权重为 0.2
- **并且** keyword 检索优先使用 name/room 模糊匹配
