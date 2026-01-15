# 任务清单: 测试目录分层整理

目录: `helloagents/plan/202601150209_tests-structure/`

---

## 1. 测试目录与文件迁移
- [√] 1.1 创建 `tests/unit` 与 `tests/integration` 目录，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.2 移动 `tests/test_command_parser.py`、`tests/test_dashscope.py`、`tests/test_smoke.py` 到 `tests/unit/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.3 移动 `tests/test_models.py`、`tests/test_state.py`、`tests/test_text.py` 到 `tests/unit/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.4 移动 `tests/test_keyword_search.py`、`tests/test_logic.py`、`tests/test_capability.py` 到 `tests/unit/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.5 移动 `tests/test_scoring.py`、`tests/test_gating.py`、`tests/test_pipeline.py` 到 `tests/unit/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.6 移动 `tests/test_ir_compiler.py`、`tests/test_bulk_mode.py`、`tests/test_injection.py` 到 `tests/unit/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.7 移动 `tests/improve_embedding_recall/test_doc_enrichment.py`、`tests/improve_embedding_recall/test_category_metrics.py`、`tests/improve_embedding_recall/test_category_gating.py` 到 `tests/unit/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.8 删除 `tests/improve_embedding_recall/__init__.py` 并移除空目录，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.9 移动 `tests/test_dashscope_integration.py`、`tests/test_bulk_pipeline_integration.py` 到 `tests/integration/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.10 移动 `tests/dashscope_integration_queries.json`、`tests/dashscope_command_parser_cases.json`、`tests/dashscope_bulk_pipeline_cases.jsonl` 到 `tests/integration/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.11 移动 `tests/smartthings_rooms.jsonl`、`tests/smartthings_devices.jsonl` 到 `tests/integration/`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.12 移动 `tests/README_dashscope_integration.md` 到 `tests/integration/README_dashscope_integration.md`，验证 why.md#需求-测试文件可维护性-场景-调用集成测试
- [√] 1.13 更新 `tests/integration/test_dashscope_integration.py` 与 `tests/integration/test_bulk_pipeline_integration.py` 中 spec.jsonl 路径计算，验证 why.md#需求-测试文件可维护性-场景-调用集成测试

## 2. 文档与知识库更新
- [√] 2.1 更新 `tests/integration/README_dashscope_integration.md` 中的测试路径与命令示例。
- [√] 2.2 更新 `helloagents/wiki/data.md` 中测试夹具路径说明。
- [√] 2.3 更新 `helloagents/CHANGELOG.md` 记录本次目录调整。

## 3. 安全检查
- [√] 3.1 执行安全检查（按 G9: 输入验证、敏感信息处理、权限控制、EHRB 风险规避）。

## 4. 测试
- [-] 4.1 运行 `PYTHONPATH=src python -m unittest tests.unit.test_models -v` 验证模块测试路径。
  > 备注: 未执行，需要手动运行。
- [-] 4.2 运行 `PYTHONPATH=src python -m unittest tests.unit.test_command_parser -v` 验证解析测试路径。
  > 备注: 未执行，需要手动运行。
- [-] 4.3 运行 `RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.integration.test_dashscope_integration -v` 验证集成测试路径（需环境变量）。
  > 备注: 未执行，需要手动运行。
