# 任务清单: 命令数组驱动的检索管线重构（含房间 scope 硬过滤回退与设备名兜底）

目录: `helloagents/history/2026-01/202601151001_command-array-pipeline-room-scope/`

---

## 1. command_parser
- [√] 1.1 在 `src/command_parser/parser.py` 中实现对象数组的直接解析（避免对象→字符串桥接），验证 why.md#需求-命令数组解析与降级-场景-单命令对象数组
- [√] 1.2 在 `tests/unit/test_command_parser.py` 中补齐对象数组与多命令顺序用例，验证 why.md#需求-命令数组解析与降级-场景-多命令对象数组

## 2. 命令入口与映射层
- [√] 2.1 在 `src/context_retrieval/pipeline.py` 中改造 `retrieve()` 为“命令数组入口 → 逐条检索 → 列表返回”，验证 why.md#需求-按命令逐条检索并返回列表-场景-多命令逐条检索
- [√] 2.2 在 `src/context_retrieval/pipeline.py` 中实现命令→QueryIR 映射（a/s/n/t/q/c），验证 why.md#需求-命令数组解析与降级-场景-单命令对象数组
- [√] 2.3 在 `src/context_retrieval/pipeline.py` 中实现向量索引与 spec lookup 复用，避免多命令重复构建

## 3. scope 过滤与设备名兜底
- [√] 3.1 在 `src/context_retrieval/logic.py` 或 `src/context_retrieval/pipeline.py` 中实现“include 硬过滤 + 空结果回退 + exclude 硬过滤”流程，验证 why.md#需求-scope-的硬过滤回退（include）与排除硬过滤（exclude）-场景-include-硬过滤生效
- [√] 3.2 在 `src/context_retrieval/logic.py` 或 `src/context_retrieval/pipeline.py` 中实现设备名房间提取（最长匹配、多命中不确定），并仅在“冲突/未知”场景启用，验证 why.md#需求-scope-的硬过滤回退（include）与排除硬过滤（exclude）-场景-include-硬过滤误杀时回退
- [√] 3.3 在 `src/context_retrieval/pipeline.py` 中将回退与兜底信息写入 `RetrievalResult.meta`，便于观测回归
- [√] 3.4 在 `tests/unit/test_pipeline.py` 中补齐 include 回退、未知房间命令、设备名兜底命中与多命中不确定用例，验证 why.md#需求-scope-的硬过滤回退（include）与排除硬过滤（exclude）-场景-命令房间词未知

## 4. bulk 与多命令适配
- [√] 4.1 在 `tests/unit/test_bulk_mode.py` 中调整返回结构与断言逻辑（列表返回），验证 why.md#需求-按命令逐条检索并返回列表-场景-多命令逐条检索

## 5. 集成测试与契约
- [√] 5.1 在 `tests/integration/test_dashscope_integration.py` 中更新 pipeline 回归断言以适配列表返回
- [√] 5.2 在 `tests/integration/test_bulk_pipeline_integration.py` 中更新批量路径断言与结构验证

## 6. 安全检查
- [√] 6.1 校验 JSON 输入容错与降级路径，避免未处理异常并记录必要日志

## 7. 文档更新
- [√] 7.1 更新 `helloagents/wiki/modules/command_parser.md` 与 `helloagents/wiki/modules/context_retrieval.md` 以反映新协议入口与 scope 策略
- [√] 7.2 更新 `helloagents/CHANGELOG.md` 与 `helloagents/history/index.md`

## 8. 测试
- [-] 8.1 运行单元测试：`PYTHONPATH=src python -m unittest tests.unit.test_command_parser tests.unit.test_pipeline tests.unit.test_bulk_mode`
  > 备注: 未运行，需在本地执行。
- [-] 8.2 运行集成测试（如有密钥）：`RUN_DASHSCOPE_IT=1 PYTHONPATH=src python -m unittest tests.integration.test_dashscope_integration tests.integration.test_bulk_pipeline_integration`
  > 备注: 未配置密钥/未运行，需在本地执行。

---

## 任务状态符号
- `[ ]` 待执行
- `[√]` 已完成
- `[X]` 执行失败
- `[-]` 已跳过
- `[?]` 待确认
