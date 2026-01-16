# 变更提案: 命令数组驱动的检索管线重构（含房间 scope 硬过滤回退与设备名兜底）

## 需求背景
当前系统同时存在两套“LLM 输出协议”：
- `src/command_parser/prompt.py` 定义的 **JSON 命令数组**（字段 `a/s/n/t/q/c`），并已有对应解析器；
- `src/context_retrieval/ir_compiler.py` 定义的 **QueryIR JSON 对象**，`pipeline.retrieve()` 仍以此为入口。

这导致：
1. 协议入口不统一，调用链与测试分裂，长期维护成本高。
2. scope（房间）语义落地不稳定：结构化 `Device.room` 不一定可靠，设备名中可能含房间词；若直接做包含房间的硬过滤，容易“误杀”本该命中的设备。

目标是以命令数组作为唯一协议入口，按命令顺序逐条复用现有检索流程，并在 scope 上引入“硬过滤但可回退 + 冲突时设备名兜底”的可控策略。

## 变更内容
1. 将 `pipeline.retrieve()` 重构为：使用 `src/command_parser/prompt.py` 的系统提示词生成 JSON 命令数组 → 解析 → 按命令顺序逐条检索。
2. 强化 `command_parser`：对提示词输出的 JSON **对象数组**进行正确解析（不再依赖对象→字符串→再解析的桥接）。
3. 新增“命令 → QueryIR”映射层：将 `a/s/n/t/q/c` 映射到检索侧需要的字段。
4. scope 语义重构：
   - `exclude` 永远硬过滤；
   - `include` 尝试硬过滤，但如果过滤结果为空则回退为“不过滤，仅保留 exclude 的过滤”；
   - 仅在“房间不可信/冲突”时启用从设备名提取房间词的兜底匹配，避免常态误匹配扩大范围。
5. 更新单元测试、集成测试与模块文档，使其以命令数组协议为准。

## 影响范围
- **模块:**
  - command_parser
  - context_retrieval（pipeline / scope 逻辑）
- **文件:**
  - `src/command_parser/parser.py`
  - `src/context_retrieval/pipeline.py`
  - `src/context_retrieval/logic.py`（或在 pipeline 内部承接 scope 过滤策略）
  - `tests/unit/test_command_parser.py`
  - `tests/unit/test_pipeline.py`
  - `tests/unit/test_bulk_mode.py`
  - `tests/integration/test_dashscope_integration.py`
  - `tests/integration/test_bulk_pipeline_integration.py`
- **API:**
  - `context_retrieval.pipeline.retrieve()` 返回类型调整为 `list[RetrievalResult]`（按命令顺序）
- **数据:** 无持久化变更

## 核心场景

### 需求: 命令数组解析与降级
**模块:** command_parser
以 `src/command_parser/prompt.py` 的输出为契约，解析 JSON 数组（元素为对象）并产出结构化命令序列；解析失败可降级为 UNKNOWN。

#### 场景: 单命令对象数组
输入为单条命令对象数组。
- 预期：action/scope/name/type/quantifier/count 字段被正确解析到结构化命令

#### 场景: 多命令对象数组
输入包含多个命令对象。
- 预期：按数组顺序输出命令列表（顺序不可交换）

### 需求: scope 的硬过滤回退（include）与排除硬过滤（exclude）
**模块:** context_retrieval

#### 场景: include 硬过滤生效
命令 `s="卧室"`，设备房间字段可信。
- 预期：仅卧室相关设备进入后续召回

#### 场景: include 硬过滤误杀时回退
命令 `s="卧室"`，但目标设备 `Device.room` 缺失/错误，设备名中含“卧室”。
- 预期：优先用设备名兜底命中；若仍过滤为空则回退（避免输出空集合）

#### 场景: 命令房间词未知（不在任何 Device.room 中）
命令 `s="次卧"`，但设备的结构化房间字段集合中没有“次卧”，而设备名存在“次卧台灯”。
- 预期：尝试用设备名命中 include；若无任何命中则触发回退（不进入澄清）

### 需求: 按命令逐条检索并返回列表
**模块:** context_retrieval

#### 场景: 多命令逐条检索
输入为多命令数组。
- 预期：返回 `list[RetrievalResult]`，长度与命令数一致且顺序一致

## 风险评估
- **风险:** API 破坏性变更（retrieve 返回类型变化）影响调用方与测试
  - **缓解:** 同步更新全部单元测试与集成测试；在文档中明确新入口协议与返回结构
- **风险:** 设备名房间兜底匹配误判，导致包含房间硬过滤选入/剔除错误
  - **缓解:** 兜底仅在冲突/未知场景启用；采用“最长匹配 + 多命中视为不确定”；include 过滤为空时强制回退并记录 meta
- **风险:** 多命令下向量索引重复构建导致性能回退
  - **缓解:** 将 `vector_searcher.index(devices)` 提升到外层，仅构建一次并复用

