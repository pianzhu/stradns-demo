# 变更：改进 Embedding 召回率

## 为什么

当前 embedding 召回率在集成测试中仅 40%，目标 ≥60%。根因分析：

1. **Action 语义歧义**：LLM 输出泛化动词（"open"、"adjust"），无法区分「打开灯」vs「打开窗帘」
2. **候选集无预过滤**：所有设备的所有命令进入候选池，语义相似的命令互相干扰
3. **文档信息量不足**：当前只用 `id + description` 构建 embedding 文档，缺乏结构化语义
4. **短文本相似度退化**：在语义相似的短描述上（"打开设备" vs "打开窗帘"），余弦排序退化为噪声

## 变更内容

- **Category Gating**：利用 SmartThings API 返回的 category（Light/Blind/AirConditioner）在 embedding 检索前过滤候选集
- **约束 type_hint**：更新 LLM system prompt，要求 `type_hint` 只能从 README 列举的 categories 中选择；无法判断时输出 `Unknown`
- **文档富化**：通过 `profileId → spec.jsonl` 构建语义丰富的命令文档
- **同义词归一化**：扩展 capability description 的动词同义词覆盖
- **Fallback 策略**：当 `type_hint` 缺失或非法时，使用 keyword 模糊匹配 name/room
- **评估与统计**：统计 category 覆盖率/缺失率、mapping 命中率、gating 触发率，并离线对比硬 gating vs 软 gating 的召回曲线

## 影响

- 受影响规范：`context-retrieval`（如存在）
- 受影响代码：
  - `src/context_retrieval/pipeline.py` - 增加 gating 逻辑分支
  - `src/context_retrieval/vector_search.py` - 文档构建重构
  - `src/context_retrieval/keyword_search.py` - fallback 模糊匹配增强
  - 新增 `src/context_retrieval/category_gating.py` - category 过滤模块
  - 新增 `src/context_retrieval/doc_enrichment.py` - 文档富化模块（读取 spec.jsonl）
- 外部依赖：
  - SmartThings API：`GET /v1/devices?locationId=...` 返回设备 category
  - `src/spec.jsonl`：profileId → capabilities 映射
