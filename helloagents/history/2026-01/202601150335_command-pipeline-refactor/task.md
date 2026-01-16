# 任务清单: 命令数组解析与检索管线重构

目录: `helloagents/plan/202601150335_command-pipeline-refactor/`

---

## 1. command_parser
- [√] 1.1 在 `src/command_parser/parser.py` 中实现 JSON 对象数组解析与 `s` 范围规则，移除 legacy 字符串输入与对象→字符串桥接，验证 why.md#需求-命令数组解析-场景-单命令对象解析
- [√] 1.2 在 `tests/unit/test_command_parser.py` 中重构测试用例并补齐 scope 通配与排除场景，验证 why.md#需求-scope-排除解析-场景-解析通配与排除

## 2. 模型与编译层
- [√] 2.1 在 `src/context_retrieval/models.py` 中新增 MultiRetrievalResult/CommandRetrieval 等结构，并在 `src/context_retrieval/ir_compiler.py` 中实现命令映射层，验证 why.md#需求-多命令检索拆分-场景-多命令逐条检索
- [√] 2.2 在 `tests/unit/test_ir_compiler.py` 中重构映射测试用例，覆盖 `@last/*/q/c` 与降级路径

## 3. 检索管线
- [√] 3.1 在 `src/context_retrieval/pipeline.py` 中改造检索主路径以支持多命令逐条检索，并新增 `retrieve_single` 兼容入口，验证 why.md#需求-多命令检索拆分-场景-多命令逐条检索
- [√] 3.2 在 `tests/unit/test_pipeline.py` 与 `tests/unit/test_bulk_mode.py` 中重构测试用例：单命令改用 `retrieve_single`，新增多命令返回结构与量词场景

## 4. 集成测试与契约
- [√] 4.1 在 `tests/integration/test_dashscope_integration.py` 中重构命令数组输出契约与主路径断言
- [√] 4.2 在 `tests/integration/test_bulk_pipeline_integration.py` 中更新批量模式解析与多命令返回验证
- [√] 4.3 在 `tests/integration/README_dashscope_integration.md` 中同步命令数组协议与运行说明

## 5. 安全检查
- [√] 5.1 校验 JSON 输入的容错与降级路径，记录日志并避免抛出未处理异常

## 6. 文档更新
- [√] 6.1 更新 `helloagents/wiki/modules/command_parser.md` 与 `helloagents/wiki/modules/context_retrieval.md` 以反映新协议
- [√] 6.2 更新 `helloagents/CHANGELOG.md` 与 `helloagents/history/index.md`

## 7. 测试
- [-] 7.1 运行单元测试：`PYTHONPATH=src python -m unittest tests.unit.test_command_parser tests.unit.test_ir_compiler tests.unit.test_pipeline tests.unit.test_bulk_mode`
  > 备注: 未执行
- [-] 7.2 运行集成测试（如有密钥）：`RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.integration.test_dashscope_integration tests.integration.test_bulk_pipeline_integration`
  > 备注: 未执行
