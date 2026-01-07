# 上下文检索规范增量

## 新增需求

### 需求：Category Gating 预过滤

系统必须在 embedding 检索前，优先根据 `QueryIR.type_hint` 进行 category 过滤。

#### 场景：type_hint 映射成功

- **当** QueryIR.type_hint 为 "Light"
- **那么** 系统将 category 识别为 "Light"
- **并且** 仅保留 category 为 "Light" 的设备进入 embedding 检索

#### 场景：type_hint 映射失败

- **当** QueryIR.type_hint 为 "UnknownCategory"（不在允许的 category 集合内）
- **那么** 系统跳过 category 过滤
- **并且** 全量设备进入 keyword 检索路径

#### 场景：type_hint 为 Unknown

- **当** QueryIR.type_hint 为 "Unknown"
- **那么** 系统跳过 category 过滤
- **并且** 优先使用 keyword 模糊匹配 name/room

#### 场景：type_hint 为空

- **当** QueryIR.type_hint 为 None
- **那么** 系统跳过 category 过滤
- **并且** 优先使用 keyword 模糊匹配 name/room

### 需求：scope_exclude 预过滤

系统必须在 category gating 与检索前，根据 `QueryIR.scope_exclude` 排除不应参与候选的设备。

#### 场景：scope_exclude 排除指定房间

- **当** QueryIR.scope_exclude 包含 "客厅"
- **并且** 设备 room 字段为 "客厅"
- **那么** 该设备不会进入后续 category gating、keyword 检索与 embedding 检索

### 需求：action 语言一致性

系统必须保证用于向量检索的 `QueryIR.action` 为中文意图短语，避免英文 action 导致语义相似度退化。

#### 场景：中文 action 优先用于向量检索

- **当** 用户查询为 "打开客厅的灯"
- **并且** QueryIR.action 为 "打开"
- **那么** 系统使用 QueryIR.action 作为 embedding 检索文本

#### 场景：英文 action 时降级为原始 query

- **当** QueryIR.action 为 "turn on"（包含英文字母）
- **那么** 系统将该 action 视为无效
- **并且** 系统使用 QueryIR.raw（原始 query）作为 embedding 检索文本
- **并且** 记录调试日志以便定位（包含原 action 与降级原因）

#### 场景：action 为空时降级为原始 query

- **当** QueryIR.action 为 None 或空字符串
- **那么** 系统使用 QueryIR.raw（原始 query）作为 embedding 检索文本

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
- **并且** 文档仅包含 description、同义词扩展和 value_descriptions
- **并且** 文档不包含 category 和 capability_id（避免中英混合干扰向量化）

#### 场景：spec 不存在时降级

- **当** 设备 profile.id 在 spec.jsonl 中不存在
- **那么** 系统使用设备原始信息（name/room）构建文档
- **并且** 文档不包含 type 字段（避免英文类型干扰向量化）
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

### 需求：检索结果输出上限与有效性

系统必须返回数量受控且可解析为真实设备信息的检索结果。

#### 场景：默认输出约 5 个候选

- **当** 系统执行上下文检索
- **并且** 未显式指定 top_k
- **那么** 系统默认返回约 5 个候选（上限为 5）
- **并且** 候选可以为 device 或 group（用于量词批量语义压缩输出）

#### 场景：device 候选必须引用有效设备信息

- **当** 系统返回 device 候选 `(device_id, capability_id)`
- **那么** 该 `device_id` 必须存在于当前设备列表中
- **并且** 系统能够解析得到对应的 `(device_id, device_name, room_name)`

#### 场景：group 候选必须引用有效 group 信息

- **当** 系统返回 group 候选 `(group_id, capability_id)`
- **那么** 系统必须同时返回该 `group_id` 对应的 group 元信息（至少包含 `device_ids` 列表）
- **并且** `device_ids` 中的每个设备都必须存在于当前设备列表中
- **并且** 系统能够解析得到每个设备对应的 `(device_id, device_name, room_name)`

#### 场景：device 候选的 capability_id 必须能映射到有效 CommandSpec

- **当** 候选包含 `capability_id`
- **那么** 该 `capability_id` 必须能映射到该设备的有效 `CommandSpec`
- **并且** 若无法映射，系统不得返回该候选（避免输出无效命令）

#### 场景：group 候选的 capability_id 必须对组内所有设备有效

- **当** group 候选包含 `capability_id`
- **那么** 该 `capability_id` 必须能映射到组内每个设备的有效 `CommandSpec`
- **并且** 若任一设备无法映射，系统不得将其纳入该 group（避免批量执行时出现不兼容设备）

### 需求：量词（quantifier）批量语义与 Group 聚合

系统必须在批量语义下兼顾召回与输出可控性，使用 group 聚合避免集合爆炸。

#### 场景：all + type_hint 命中时返回覆盖全集的 group

- **当** QueryIR.quantifier 为 "all"
- **并且** QueryIR.type_hint 为 "Light"
- **那么** 系统识别目标集合为 “所有满足过滤条件的 Light 设备”
- **并且** 系统使用 group 聚合输出，且 group 覆盖该全集（不因 top_k 代表性截断而遗漏目标设备）

#### 场景：except + scope_exclude 时返回排除后的 group

- **当** QueryIR.quantifier 为 "except"
- **并且** QueryIR.scope_exclude 包含 "LivingRoom"
- **并且** QueryIR.type_hint 为 "Light"
- **那么** 系统识别目标集合为 “所有 Light 设备中 room 不为 LivingRoom 的设备”
- **并且** 系统使用 group 聚合输出并覆盖排除后的全集

#### 场景：按命令集一致性分组

- **当** 两个设备的命令集（capability_id 集合）完全一致
- **那么** 系统可以将它们合并为同一个 group
- **并且** 系统保证对该 group 执行某个 `capability_id` 时，组内所有设备都支持该命令

#### 场景：集合爆炸时的输出控制

- **当** 批量语义下匹配到的目标设备数量超过系统上限
- **那么** 系统不得返回不可控规模的候选列表
- **并且** 系统返回裁剪后的 group 列表（数量受控）
- **并且** 系统提供明确的 hint，提示用户缩小范围或确认继续

## 修改需求

### 需求：混合召回

系统必须支持 Keyword 和 Vector 混合召回，根据 category gating 结果调整策略。

#### 场景：category gating 有效时

- **当** type_hint 为有效 category 且不为 "Unknown"
- **那么** keyword 权重为 1.0，vector 权重为 0.5
- **并且** 在过滤后的候选集上执行 embedding 检索

#### 场景：category gating 无效时

- **当** type_hint 为 "Unknown"、为空或非法
- **那么** keyword 权重为 1.5，vector 权重为 0.2
- **并且** keyword 检索优先使用 name/room 模糊匹配
