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

## 6. 提示词、全链路验收与量词策略

- [x] 6.1 对齐 action 中文化与降级策略
  - 更新默认 system prompt：要求 `action` 必须为中文意图短语（不包含英文字母）；无法判断时省略或返回空值
  - 增加 action 合法性校验：当 `action` 包含英文字母时视为无效，并降级为使用原始 query 进行 embedding 检索（同时记录调试日志）
  - 验证：更新/新增单元测试覆盖 action 校验与降级逻辑

- [x] 6.2 量词（quantifier）批量语义：capability 选择 + 兼容性 group + batch 分片
  - 增加 bulk mode：`quantifier in (all, except)` 时进入批量语义路径
  - capability_id 选择（先选命令，再扩展集合）：
    - 基于命令级向量召回证据聚合得到 top-N capability 选项（`N=5`）
      - 使用更大的候选窗口获取证据（例如 `OPTIONS_SEARCH_K=50~100`），避免 `top_k=5` 证据过少导致置信度虚高
      - 为避免“支持设备数多 → 证据累计更高”的偏置，对每个 `capability_id` 仅保留 top-M 条证据参与聚合（例如 `M=3`）
    - 置信度判定不只看相对排序，也看覆盖度：
      - `top1_ratio` / `margin`：由聚合得分归一化得到分布 `p_i` 后计算
      - `coverage = supports(capability_id) / len(filtered_devices)`：bulk 语义下用于检测“选中的命令无法覆盖全集”
    - 低置信度时的处理（两条路径二选一，需在实现前明确约束）：
      - **默认推荐（不增加 LLM 调用次数）**：不自动选定；返回 `hint=need_clarification` + top-2/3 选项摘要，让用户闭集选择（例如返回 `choice_index`）；最多 1 轮澄清，用户回答后重跑全链路
      - **可选（允许额外 1 次 LLM 调用）**：在 `ENABLE_BULK_ARBITRATION_LLM=1` 时触发 LLM 闭集仲裁；输出最小协议（`0-based`）二选一：`{"choice_index": 2}` 或 `{"question": "..."}`；若仍低置信度，降级为非 bulk（返回 top-k 代表候选并提示用户更具体）
    - 覆盖度不足的处理：当 `coverage` 低于阈值时返回 `hint=partial_coverage`（携带支持/不支持数量），避免 silent drop
  - 兼容性 group（可执行单位）：
    - 以“所选 capability_id 的 CommandSpec 参数契约”作为 compatibility signature（建议显式排除 `description`，只保留结构与取值域）：
      - `type`
      - `value_range`（`minimum/maximum/unit`）
      - `value_list`（按 `value` 排序后的值集合；避免受翻译文案影响）
    - signature 完全一致的设备可合并为一组；保证对该组执行 capability_id 时组内设备均有有效 CommandSpec 映射
  - batch 分片（并发控制与爆炸防护）：
    - 明确区分两件事：
      - **输出压缩**：对外尽量用少量 group 覆盖全集（避免候选数量失控）
      - **执行并发**：对内按固定大小切分 batch（用于下游并发控制）
    - 执行 batch：对每个 compatibility group 再按固定大小切分 batch：`BATCH_SIZE=20`（不依赖 room 分组，room 可能为空/不可用）
    - 爆炸防护：定义系统上限（例如 `MAX_TARGETS` / `MAX_GROUPS`），超过上限时返回 `hint=too_many_targets` 并提示用户缩小范围或确认继续（避免返回不可控规模的候选列表）
  - 验证：新增/更新单元测试覆盖 capability 选择与低置信度触发、LLM 仲裁输出校验、分组兼容性、batch 切分行为

- [x] 6.3 全链路验收：按 pipeline 执行检索并输出逐用例关键日志
  - 更新 `tests/test_dashscope_integration.py`：
    - 新增/改造测试用例为全链路：LLM 解析 QueryIR → 调用 `pipeline.retrieve()` → 断言 top-N 命中率（以 pipeline 最终输出为准）
    - 覆盖 bulk mode：包含 `quantifier=all/except` 的用例，验证输出 group 聚合行为与爆炸防护 hint
    - 每条用例输出关键日志：query、QueryIR(action/type_hint/scope_include/scope_exclude/quantifier)、mapped_category、是否触发 gating、候选规模变化、Top-5 候选（含分数与理由）、expected、HIT/MISS
  - 增强有效性校验：
    - pipeline 最终输出默认约 5 个候选（`top_k=5`）
    - device 候选：`device_id` 可解析到 `(id, name, room)`；`capability_id` 可映射到有效 `CommandSpec`
    - group 候选：`group_id` 可解析到 `device_ids`；组内每个设备都可解析到 `(id, name, room)`；`capability_id` 对组内设备均有效
  - 验证：集成测试日志可用于逐用例定位误召回/漏召回的链路环节

## 依赖关系

```
1.1 ──┬──► 3.1
1.2 ──┤
      │
2.1 ──┴──► 3.3 ──► 4.1
2.2 ──────────────► 4.2
      │
3.2 ──────────────► 4.3

4.2 ──────────────► 6.1
6.1 ──────────────► 6.2
6.2 ──────────────► 6.3
```

## 可并行工作

- 1.1 和 1.2 可并行
- 2.1 和 2.2 可并行（依赖 1.2 完成）
- 4.1/4.2/4.3 可并行（依赖 3.x 完成）
- 6.1/6.2/6.3 需要按依赖顺序推进
