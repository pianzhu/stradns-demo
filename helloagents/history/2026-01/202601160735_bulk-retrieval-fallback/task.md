# 任务清单: bulk-retrieval-fallback

目录: `helloagents/history/2026-01/202601160735_bulk-retrieval-fallback/`

---

## 1. context_retrieval
- [√] 1.1 在 `src/context_retrieval/pipeline.py` 中实现 bulk 可用性判定与查询清洗，验证 why.md#需求-批量检索兜底-场景-无向量检索器
- [√] 1.2 在 `src/context_retrieval/pipeline.py` 中调整 bulk 查询 name_hint 追加逻辑，验证 why.md#需求-批量能力选项可用-场景-亮度批量调节

## 2. 文档更新
- [√] 2.1 更新 `helloagents/wiki/modules/context_retrieval.md` 记录 bulk 兜底与查询清洗说明
- [√] 2.2 更新 `helloagents/CHANGELOG.md` 与 `helloagents/history/index.md` 记录本次修复

## 3. 安全检查
- [√] 3.1 执行安全检查（输入验证、敏感信息处理、权限控制、EHRB风险规避）

## 4. 测试
- [ ] 4.1 运行 `pytest -q tests/unit/test_bulk_mode.py tests/unit/test_pipeline.py`

---

## 任务状态符号
- `[ ]` 待执行
- `[√]` 已完成
- `[X]` 执行失败
- `[-]` 已跳过
- `[?]` 待确认
