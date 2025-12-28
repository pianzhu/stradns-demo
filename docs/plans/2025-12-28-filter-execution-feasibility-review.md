# 方案可行性评审：基于逻辑筛选的指令执行

> **评审目标**：挖掘 "Filter-Based Execution" (逻辑筛选法) 的潜在风险、失败场景及应对策略。
> **结论前置**：该方案在**延迟**和**泛化性**上优势明显，但对**元数据质量**和**DSL 设计**有极高要求。

---

## 1. 核心风险矩阵

| 风险维度 | 严重性 | 发生概率 | 描述 |
| :--- | :--- | :--- | :--- |
| **元数据缺失 (Metadata Gap)** | 高 | 高 | 用户指令涉及的属性（如“适合阅读”、“角落里的”）在设备元数据中不存在，导致 Filter 无法编写。 |
| **逻辑幻觉 (Logic Hallucination)** | 中 | 中 | LLM 生成了符合语法但逻辑错误的 Filter，或者使用了不存在的字段/函数。 |
| **指代消解失败 (Reference Resolution)** | 中 | 高 | "把它关了"、"这里太暗了" —— 这种依赖视觉或多轮对话上下文的指令，单纯靠 Filter 难以表达。 |
| **混合意图解析 (Mixed Intent)** | 中 | 低 | 一句话包含多种互斥的操作，导致 JSON 生成结构错误或逻辑冲突。 |
| **过度执行 (Over-Execution)** | 高 | 低 | 逻辑写得太宽泛（如 `device.id != null`），导致全屋设备误动作。 |

---

## 2. 深度场景推演 (Pre-Mortem)

### 场景 A：非结构化/主观描述的滑铁卢
*   **用户指令**：“把**氛围感**好一点的灯打开。”
*   **失败模式**：
    *   设备表中只有 `room`, `type`, `brightness` 等硬字段。
    *   LLM 可能会瞎编：`tags contains 'atmosphere'` 或 `name contains '氛围'`。
    *   **结果**：Python 执行结果为空，用户觉得“根本听不懂人话”。
*   **缓解策略**：
    *   **语义标签 (Semantic Tagging)**：在离线阶段，利用 LLM 为每个设备自动打上丰富的 Tag（如 `cozy`, `reading`, `party`）。
    *   **Embedding 辅助**：保留轻量级的 Embedding 检索作为 Filter 的一种特殊算子。例如：`semantic_match(device.desc, '氛围感') > 0.8`。这实际上是把 Layer 1 的能力做成了一个函数。

### 场景 B：复杂的空间关系与指代
*   **用户指令**：“把**我房间**的空调关了。”（假设系统不知道哪个是“我”的房间）
*   **失败模式**：
    *   LLM 输出 `room == 'my_room'`。
    *   Python 执行报错或为空。
*   **缓解策略**：
    *   **上下文注入**：Prompt 中必须包含 explicit 的用户画像或当前状态（如 `user_location='master_bedroom'`）。
    *   **交互式回退**：当 Filter 返回空集时，不要直接报错，而是由 Agent 反问：“请问您的房间是指主卧吗？”

### 场景 C：逻辑语法的复杂性边界
*   **用户指令**：“除了主卧的灯，和客厅的空调，其他的都关掉。”
*   **失败模式**：
    *   这是一个复杂的集合运算：`ALL - ({ListingSet} U {LivingAC})`。
    *   LLM 可能会写出逻辑错误的表达式：`room != 'master' and room != 'living'` (这样会把客厅的灯也排除了，如果原意是只排除客厅空调)。
    *   **正确逻辑**：`not ( (room=='master' and type=='light') or (room=='living' and type=='ac') )`。
*   **缓解策略**：
    *   **Few-Shot 覆盖**：在 System Prompt 中提供复杂的集合运算案例。
    *   **Chain-of-Thought**：让 LLM 先输出自然语言的逻辑解释，再输出代码，提高准确率。

### 场景 D：安全性 —— "一键毁灭"
*   **用户指令**：用户可能恶意或无意输入“把所有东西打开/关掉”。
*   **失败模式**：
    *   Filter: `True` (选中所有设备)。
    *   结果：全屋 100 个设备同时响应，瞬间功率激增，或者产生惊吓。
*   **缓解策略**：
    *   **安全阀 (Safety Valve)**：Python 执行层增加限制，如果单次操作设备数 > N (如 10)，必须触发二次确认（语音播报：“确认要操作 25 个设备吗？”）。

---

## 3. 技术实施的关键成败点

### 3.1 DSL (领域特定语言) 的选择
*   **不要发明新语言**：不要让 LLM 学习自定义的 JSON DSL。
*   **推荐方案**：使用 **Pandas Query 语法** 或 **Python 表达式** (限制子集)。LLM 训练数据里有海量的 Python/SQL 代码，它天生精通。
    *   Good: `type == 'light' and room in ['living', 'kitchen']`
    *   Bad: `{"op": "and", "conditions": [...]}` (JSON 树结构极其消耗 Token 且容易错)

### 3.2 Prompt 不仅是 Schema，更是文档
Prompt 中不能只给设备列表，必须给 **Metadata Schema 定义**。
*   告诉 LLM 有哪些字段：`id`, `name`, `type`, `room`, `tags`, `state`。
*   告诉 LLM 具体的枚举值：`type` 包括 `[light, ac, curtain, switch]`。

---

## 4. 结论与建议

**该方案可行，且是 Smart Home 场景下的最优解 (State of the Art)**，前提是必须做好以下两点：

1.  **数据治理 (Data Governance)**：不仅要有设备表，还要有高质量的标签体系。设备的 Description 必须足够丰富。
2.  **安全执行器 (Safe Executor)**：Python 侧必须要有一个健壮的 Query 引擎，并且有熔断机制。

**下一步建议**：
先实现一个 MVP，只支持 `room` 和 `type` 的筛选，验证 LLM 生成 Filter 的准确率。不要一开始就试图支持“氛围感”这种高级语义。
