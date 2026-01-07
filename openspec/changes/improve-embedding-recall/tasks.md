# 任务清单：改进 Embedding 召回率

## 1. 基础设施

- [x] 1.1 创建 `category_gating.py` 模块
  - 定义 `ALLOWED_CATEGORIES`（与 README 保持一致）
  - 实现 `map_type_to_category(type_hint: str | None) -> str | None`（归一化 + 合法性校验）
  - 实现 `filter_by_category(devices: list[Device], category: str) -> list[Device]`
  - 验证：单元测试覆盖归一化和过滤逻辑

- [x] 1.2 创建 `doc_enrichment.py` 模块
  - 定义 `VERB_SYNONYMS` 同义词表
  - 实现 `load_spec_index(spec_path: str) -> dict[str, list[CapabilityDoc]]`
  - 实现 `enrich_description(desc: str) -> str`
  - 实现 `build_enriched_doc(device: Device, spec_index: dict) -> list[str]`
    - 文档格式：`{description} {synonyms} {value_descriptions}`
    - 不含 category/capability_id（避免中英混合干扰向量化）
  - 处理 `value_list`：将参数描述拼接到命令文档
  - Fallback：仅用 name/room（不含 type）
  - 验证：单元测试确认文档构建正确（含带参数命令）

## 2. 向量检索改造

- [x] 2.1 重构为 `DashScopeVectorSearcher`
  - 合并 `InMemoryVectorSearcher` 和 `DashScopeEmbeddingModel` 为单一类
  - 继承 `VectorSearcher` 抽象基类
  - 构造函数接收 `spec_index` 参数
  - 使用 `build_command_corpus()` 构建富化文档
  - 索引结构改为 `(device_id, capability_id) → embedding`
  - 保留 `encode()` 公共方法用于直接 embedding 访问
  - 验证：确认向量维度和余弦相似度计算正确

- [x] 2.2 删除冗余代码
  - 删除 `SentenceTransformerSearcher`（不再使用）
  - 删除 `InMemoryVectorSearcher`（已合并到 DashScopeVectorSearcher）
  - 删除 `EmbeddingModel` Protocol（不再需要）
  - 保留 `StubVectorSearcher` 用于测试

## 3. Pipeline 集成

- [x] 3.1 集成 category gating 到 `retrieve()` 函数
  - 在 scope 预过滤后、混合召回前执行 category gating
  - 判断逻辑：`type_hint` 合法且不为 `Unknown` → 执行 gating
  - 验证：日志输出 gating 前后候选数量

- [x] 3.2 实现 fallback 策略
  - `type_hint` 缺失/非法或为 `Unknown` 时跳过 gating
  - 调整 keyword/vector 权重比例（keyword 权重提升）
  - 验证：无有效 type_hint 场景走 keyword 主路径

- [x] 3.3 修改融合评分
  - 候选从设备级改为命令级
  - 调整 `Candidate` 结构（新增 `capability_id` 字段）
  - 验证：确认评分逻辑适配新结构

- [x] 3.4 实现 scope_include 评分加权
  - scope_include 作为评分加权因素（非硬过滤）
  - 设备 room 匹配 scope_include 时增加 `ROOM_MATCH_BONUS`
  - 验证：自定义名称包含房间词的设备不被遗漏

## 4. 测试验证

- [x] 4.1 更新单元测试
  - `test_category_gating.py`：映射和过滤测试
  - `test_doc_enrichment.py`：文档构建和同义词扩展测试
  - `test_dashscope.py`：DashScopeVectorSearcher 单元测试
  - 删除 `test_vector_search.py`（测试已删除的类）
  - 删除 `test_vector_search_command_index.py`（测试已删除的类）
  - 删除 `test_dashscope_enriched_embedding.py`（测试已删除的类）

- [x] 4.2 更新集成测试
  - 修改 `test_dashscope_integration.py` 使用 `DashScopeVectorSearcher`
  - 验证 top-10 召回命中率 ≥60%

- [x] 4.3 回归测试
  - 确认现有 keyword 检索路径不受影响
  - 确认 scope 过滤逻辑不受影响

## 5. 文档与可观测性

- [x] 5.1 更新 `tests/README_dashscope_integration.md`
  - 记录新架构下的测试结果
  - 对比改进前后召回率

- [x] 5.2 添加调试日志
  - category gating 前后候选数
  - type_hint → category 映射结果
  - 最终排序前 top-5 候选及分数

## 依赖关系

```
1.1 ──┬──► 3.1
1.2 ──┤
      │
2.1 ──┴──► 3.3 ──► 4.1
2.2 ──────────────► 4.2
      │
3.2 ──────────────► 4.3
```

## 可并行工作

- 1.1 和 1.2 可并行
- 2.1 和 2.2 可并行（依赖 1.2 完成）
- 4.1/4.2/4.3 可并行（依赖 3.x 完成）
