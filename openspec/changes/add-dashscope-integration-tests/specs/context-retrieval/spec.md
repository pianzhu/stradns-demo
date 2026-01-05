## 新增需求
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
