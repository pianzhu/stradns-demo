# 技术设计: 测试目录分层整理

## 技术方案
### 核心技术
- Python unittest 目录发现
- pathlib Path 相对路径管理

### 实现要点
- 新建 tests/unit 与 tests/integration 子目录。
- 将全部单元测试移动到 tests/unit（含 improve_embedding_recall 下的用例）。
- 将 DashScope 集成测试与 JSON/JSONL 夹具移至 tests/integration，并与测试文件同级。
- 修正集成测试中 spec.jsonl 的路径计算逻辑，避免目录层级变化导致路径错误。
- 同步更新相关文档与知识库数据路径说明。

## 安全与性能
- **安全:** 仅调整测试目录与文档，不触及生产运行路径。
- **性能:** 目录整理对运行性能无影响。

## 测试与部署
- **测试:** 运行关键 unittest 用例，覆盖集成测试与核心模块测试路径。
- **部署:** 无需部署步骤。
