# context-retrieval Specification

## Purpose
TBD - created by archiving change add-context-retrieval. Update Purpose after archive.
## 需求
### 需求：语义解析（LLM）

系统必须使用大模型将用户查询解析为结构化 QueryIR，并保证输出满足约定的 JSON schema（仅字段，不含自由文本推理），且返回解析置信度。

#### 场景：解析动作与名称

- 给定：用户查询"打开老伙计"
- 当：进行 LLM 语义解析
- 则：action 应为 "打开"
- 且：name_hint 应为 "老伙计"

#### 场景：解析量词与范围

- 给定：用户查询"关闭所有卧室的灯"
- 当：进行 LLM 语义解析
- 则：action 应为 "关闭"
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
- 且：action = "打开"
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

### 需求：dashscope 集成测试（LLM + Embedding）
必须提供可在本地手动运行的 dashscope 在线模型集成测试，用于验证 QueryIR 解析与命令语义召回，缺失密钥或网络不可用时应跳过而非失败。

#### 场景：LLM 解析 QueryIR
- 给定：真实中文查询（包含动作、名称/房间/类型等信息）
- 当：使用 dashscope `qwen-flash` 调用 `DashScopeLLM` 解析
- 则：输出应包含 action
- 且：应提取与查询匹配的 name_hint 或 scope/type_hint 或 quantifier 中的至少一项

#### 场景：LLM → Embedding 的主路径联通
- 给定：真实中文查询
- 当：先使用 dashscope `qwen-flash` 解析为 QueryIR
- 且：使用 QueryIR.action（为空则 fallback 使用原始 query）作为 embedding 查询文本
- 且：使用 dashscope `text-embedding-v4` 在命令库上进行相似度检索
- 则：检索流程应可完成且返回非空候选列表

#### 场景：命令 embedding top-N 命中（以命令 ID 为准）
- 给定：`src/spec.jsonl` 中的命令描述构建的 embedding 索引
- 且：提供与命令语义匹配的中文查询
- 当：使用 dashscope `text-embedding-v4` 进行相似度检索
- 则：期望的 capability.id 出现在 top10 候选内（top-N 可配置）

#### 场景：无密钥时跳过
- 给定：环境变量缺失 `DASHSCOPE_API_KEY`
- 当：运行集成测试
- 则：相关测试应被标记跳过而非失败

