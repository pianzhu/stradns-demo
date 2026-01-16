# 变更提案: bulk-retrieval-fallback

## 需求背景
批量/非批量检索在量词为 all 时直接进入 bulk 流程，缺少向量检索器或 spec_index 时提前返回，导致候选为空；同时向量检索查询文本拼接泛化 name_hint，使得 bulk 能力选项为空，相关单元测试失败。

## 变更内容
1. 当 bulk 前置条件不足时退化到常规检索流程。
2. 向量检索查询文本使用原始问题清洗后的动作片段，避免泛化 name_hint 干扰。
3. 同步更新知识库与变更记录。

## 影响范围
- **模块:** context_retrieval
- **文件:** src/context_retrieval/pipeline.py, helloagents/wiki/modules/context_retrieval.md, helloagents/CHANGELOG.md, helloagents/history/index.md
- **API:** 无
- **数据:** 无

## 核心场景

### 需求: 批量检索兜底
**模块:** context_retrieval
当量词为 all/except 但缺少向量检索器或 spec_index 时，仍能返回常规检索候选。

#### 场景: 无向量检索器
关闭卧室的灯时，候选包含卧室灯与客厅灯。
- 预期结果: 候选不为空，命中包含灯具设备。

### 需求: 批量能力选项可用
**模块:** context_retrieval
当量词为 all 且向量检索可用时，能构建 capability options 并完成仲裁/分组。

#### 场景: 亮度批量调节
把所有灯调到50时，按 capability signature 分组。
- 预期结果: 生成分组与批次，不返回 no_capability_options。

## 风险评估
- **风险:** 查询清洗可能误删设备名，降低语义检索召回。
- **缓解:** 仅在 bulk 量词场景清洗，并保留 action/raw fallback。
