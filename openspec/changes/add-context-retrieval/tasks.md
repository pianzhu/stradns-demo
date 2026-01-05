# 任务列表：智能家居上下文检索

## 任务概览

| 任务 | 描述 | 状态 | 备注 |
|------|------|------|------|
| T1 | 建立测试脚手架 | ✅ 完成 | |
| T2 | 定义核心数据模型 | ✅ 完成 | 移除 ClarificationOption/ClarificationRequest |
| T3 | 文本归一化与 ngram | ✅ 完成 | |
| T4 | Keyword 检索 | ✅ 完成 | |
| T5 | 向量检索接口 | ✅ 完成 | |
| T6 | 统一融合与评分 | ✅ 完成 | |
| T7 | 候选筛选与排序 | ✅ 完成 | **设计变更**：简化为 top-k + hint，澄清交给大模型 |
| T8 | LLM 语义编译 | ✅ 完成 | **设计变更**：使用 LLM 而非规则 |
| T9 | 会话状态接口 | ✅ 完成 | 只定义接口，待系统整合 |
| T10 | Scope 过滤 | ✅ 完成 | **待优化**：条件依赖扩展暂未实现 |
| T11 | 命令一致性校验 | ✅ 完成 | **设计变更**：使用向量相似度匹配 |
| T12 | 安全上下文注入 | ✅ 完成 | |
| T13 | Pipeline 组装 | ✅ 完成 | |
| T14 | Demo 数据 | ✅ 完成 | **待完成**：cli_demo.py 待后续 |

## 待优化项

### 🔧 T7: 澄清机制
- **当前状态**：检索只返回候选列表 + `hint`（如 `multiple_close_matches`）
- **设计决策**：是否需要澄清由后续大模型判断，避免硬编码阈值
- **待确认**：大模型如何使用 hint 信息

### 🔧 T10: 条件依赖扩展
- **当前状态**：只实现 `apply_scope_filters`（包含/排除房间）
- **未实现**：`expand_dependencies`（温度条件触发传感器依赖）
- **待设计**：条件判断逻辑的整体方案

### 🔧 T14: CLI 演示
- **当前状态**：只有 `demo_data.py`（演示设备 + FakeLLM 预设）
- **未实现**：`cli_demo.py`
- **依赖**：需要先解决其他待优化项

## 设计变更记录

### 门控机制简化（T7）
- **原设计**：分差不足时返回 `ClarificationRequest`
- **新设计**：只返回 `hint` 提示，澄清由大模型决定
- **原因**：
  1. 大模型可结合语义上下文做更好判断
  2. 避免硬编码 epsilon 阈值
  3. 最小化信息设计，避免影响大模型注意力

### 语义编译改用 LLM（T8）
- **原设计**：规则版 IR 编译（正则匹配）
- **新设计**：调用 LLM 解析为 QueryIR（JSON）
- **原因**：
  1. 泛化性更好
  2. 能处理复杂自然语言表达
  3. 不需要维护规则

### 命令一致性改用向量相似度（T11）
- **原设计**：关键词映射（action → keywords）
- **新设计**：动作意图与 CommandSpec.description 向量相似度匹配
- **原因**：更灵活，能处理语义相似但措辞不同的情况

---

## 详细任务

### T1: 建立测试脚手架（unittest + discover）✅

**文件**：
- `tests/test_smoke.py`

**验证**：`PYTHONPATH=src python -m unittest discover -s tests -v` → OK

---

### T2: 定义核心数据模型 ✅

**文件**：
- `src/context_retrieval/__init__.py`
- `src/context_retrieval/models.py`
- `tests/test_models.py`

**数据模型**：
- `ValueOption`, `ValueRange`
- `CommandSpec`, `Device`, `Group`
- `Condition`, `ActionIntent`, `QueryIR`
- `Candidate`, `RetrievalResult`（简化版，含 hint）

**变更**：移除 `ClarificationOption`, `ClarificationRequest`

---

### T3: 文本归一化与索引字段 ✅

**文件**：
- `src/context_retrieval/text.py`
- `tests/test_text.py`

---

### T4: Keyword 检索 ✅

**文件**：
- `src/context_retrieval/keyword_search.py`
- `tests/test_keyword_search.py`

---

### T5: 向量检索接口 + Stub 实现 ✅

**文件**：
- `src/context_retrieval/vector_search.py`
- `tests/test_vector_search.py`

---

### T6: 统一融合与评分 ✅

**文件**：
- `src/context_retrieval/scoring.py`
- `tests/test_scoring.py`

---

### T7: 候选筛选与排序 ✅

**文件**：
- `src/context_retrieval/gating.py`
- `tests/test_gating.py`

**实现**：
- `select_top(candidates, top_k)` → `SelectionResult(candidates, hint)`
- `hint`: `None` 或 `"multiple_close_matches"`

**设计变更**：澄清判断交给大模型

---

### T8: LLM 语义编译 ✅

**文件**：
- `src/context_retrieval/ir_compiler.py`
- `tests/test_ir_compiler.py`

**实现**：
- `LLMClient` 协议接口
- `FakeLLM` 用于测试/离线 demo
- `compile_ir(text, llm)` → `QueryIR`
- `QUERY_IR_SCHEMA` JSON schema 参考

**设计变更**：使用 LLM 而非规则

---

### T9: 会话状态接口 ✅

**文件**：
- `src/context_retrieval/state.py`
- `tests/test_state.py`

**实现**：
- `ConversationState` 接口定义
- `resolve_reference(ref)` / `update_mentioned(device)`

**备注**：只定义接口，待系统整合

---

### T10: Scope 过滤 ✅

**文件**：
- `src/context_retrieval/logic.py`
- `tests/test_logic.py`

**实现**：
- `apply_scope_filters(devices, ir)` - 包含/排除房间

**待优化**：`expand_dependencies` 条件依赖扩展暂未实现

---

### T11: 命令一致性校验 ✅

**文件**：
- `src/context_retrieval/capability.py`
- `tests/test_capability.py`

**实现**：
- `SimilarityFunc` 类型定义
- `capability_filter(devices, ir, similarity_func, threshold)`

**设计变更**：使用向量相似度匹配

---

### T12: 安全的上下文注入（YAML 格式）✅

**文件**：
- `src/context_retrieval/injection.py`
- `tests/test_injection.py`

**实现**：
- `summarize_devices_for_prompt(devices)` → YAML 字符串
- 名称清理：截断 + 危险字符移除

---

### T13: Pipeline 组装 ✅

**文件**：
- `src/context_retrieval/pipeline.py`
- `tests/test_pipeline.py`

**Pipeline 流程**：
1. IR 编译（LLM）
2. Scope 预过滤
3. Keyword 召回
4. 融合评分
5. Top-K 筛选
6. 更新会话状态

**待整合**：
- 条件依赖扩展
- 能力一致性过滤（需传入 similarity_func）
- 向量召回

---

### T14: Demo 数据 ✅

**文件**：
- `src/context_retrieval/demo_data.py`

**包含**：
- `DEMO_DEVICES` - 6 个样例设备
- `DEMO_LLM_PRESETS` - FakeLLM 预设响应

**待完成**：`cli_demo.py`

---

## 测试验证

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
# 112 tests, OK
```
