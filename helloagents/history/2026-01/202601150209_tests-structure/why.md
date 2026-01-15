# 变更提案: 测试目录分层整理

## 需求背景
tests 根目录文件过多，查找与维护成本上升；需要按测试类型分层整理，并确保 JSON/JSONL 夹具与使用它们的测试文件同级。

## 变更内容
1. 按测试类型整理 tests 子目录：tests/unit（单元测试集中放置）与 tests/integration（集成测试与夹具）。
2. 将 DashScope 集成测试与相关 JSON/JSONL 夹具移动到 tests/integration，并与测试文件保持同级。
3. 更新测试文件中的路径引用与文档中的测试路径说明。

## 影响范围
- **模块:** 测试与文档
- **文件:** tests/*, tests/improve_embedding_recall/*, tests/README_dashscope_integration.md, helloagents/wiki/data.md
- **API:** 无
- **数据:** 测试夹具路径调整

## 核心场景

### 需求: 测试文件可维护性
**模块:** tests
测试文件按模块/类型分层组织，便于定位与批量执行。

#### 场景: 调用集成测试
运行集成测试时，夹具文件与测试文件同目录，路径引用保持稳定。
- 预期结果: 集成测试仍可通过 FIXTURE_DIR 相对路径加载 JSON/JSONL。

## 风险评估
- **风险:** 测试路径变更导致文档或命令失效。
- **缓解:** 同步更新相关文档与路径引用，保留可执行的测试命令示例。
