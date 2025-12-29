# 智能家居 Agent 上下文检索策略：设备筛选与精准注入架构

**日期:** 2025-12-29
**状态:** 待审核 (Draft)
**目标:** 优化上下文效率 (Context Efficiency)，在最大限度减少 Token 占用的同时，确保高召回率 (High Recall) 和泛化能力，解决“找得准”与“传得少”的矛盾。

---

## 1. 背景与核心挑战

在构建智能家居 Agent 时，我们面临一个核心困境：
*   **Token 限制与延迟**: 将家庭中所有设备（可能 100+ 个）的详细状态注入到 LLM 上下文中会导致延迟爆炸和成本激增。
*   **准确性要求**: 用户指令往往模糊（"打开那个"）或高度个性化（"打开大白"）。如果为了节省 Token 而过度过滤，导致目标设备未被注入，任务将直接失败。

**核心问题**: 如何从海量设备中筛选出 *最少且必要* 的设备子集，既不漏掉用户那个起名为 "XYZ" 的台灯，又不把无关的传感器塞进 Prompt？

---

## 2. 方案演进与决策

### 初始假设：基于类型的预过滤 (Pre-Filtering)
*   *思路*: 先根据用户指令中的地点（如“客厅”）和设备类型（如“灯”）进行 SQL 过滤，再交给 LLM。
*   *结论*: **否决 (Rejected)**。
*   *原因*: 数据定义过于僵化，无法处理现实世界的复杂性。
    *   **智能插座悖论**: 用户把台灯插在智能插座上。系统认为它是 `Outlet`，当用户说“开灯”时，过滤器 `Type='Light'` 会直接剔除它，导致任务失败。

### 最终推荐：基于能力的混合检索漏斗 (Capability-Based Hybrid Funnel)
*   *思路*: 放弃单一的检索方式，采用 **混合检索 (Hybrid Search)** 兼顾语义和字面匹配，并使用 **能力 (Capability)** 而非类型作为安全过滤网。

---

## 3. 推荐架构流程图

```mermaid
flowchart TD
    UserInput["用户指令: '打开 XYZ 并且把那个调暖一点'"] --> Analysis{意图分析}
    
    subgraph "第一阶段：混合检索 (保障召回率 - Recall)"
        Analysis -->|向量语义| VectorSearch["向量检索 (ANN)<br/>'调暖一点' -> 召回 Heater, AC, Light"]
        Analysis -->|关键字提取| KeywordSearch["关键字/模糊匹配 (BM25)<br/>Name/Alias LIKE '%XYZ%'"]
    end
    
    VectorSearch & KeywordSearch --> Merger[结果融合 (取并集)]
    
    subgraph "第二阶段：后置过滤 (保障精确度 - Precision)"
        Merger --> CapFilter{能力/接口校验}
        
        CapFilter -->|通过| Candidates["最终上下文列表 (3-5 个设备)"]
        CapFilter -->|剔除| Trash["无关设备<br/>(如虽然都在客厅，但不能控制的传感器)"]
        
        style CapFilter fill:#f9f,stroke:#333
    end
    
    Candidates --> LLM[Agent 推理与执行]
```

---

## 4. 风险分析与解决方案 (事前验尸)

基于 **Phase 5 Inversion** 方法论，我们假设系统上线 6 个月后出现严重故障，以下是识别出的致命缺陷及本方案的修复策略。

### 风险 A: "XYZ" 命名问题 (自定义名称)
*   **场景**: 用户给老式台灯起名 "老伙计" (XYZ)。用户说 "打开老伙计"。
*   **失效模式**:
    *   **纯向量检索失效**: "老伙计" 和 "灯" 在语义空间无关联，Embedding 找不到它。
    *   **类型过滤失效**: "老伙计" 不是标准类型，也不是地点。
*   **解决方案**: **混合检索 (路径 B)**。
    *   系统包含一路 **关键字检索 (Keyword Search)**。它不进行“理解”，只是机械地匹配 `Alias` 或 `Name` 字段。只要名字里有 "XYZ"，无视类型和语义，强制召回。

### 风险 B: 智能插座悖论 (类型僵化)
*   **场景**: 普通台灯接在智能插座上，系统记录类型为 `Outlet`。
*   **失效模式**: 过滤器执行 `WHERE Type='Light'`，插座被剔除。
*   **解决方案**: **能力优先 (Capability Over Type)**。
    *   不管是插座还是灯，只要具备 `Switch.On` (开关) 能力，且符合语义/关键字检索，就保留。
    *   让最终的 LLM 去判断这个 "插座" 在当前语境下是否充当了 "灯" 的角色。

### 风险 C: 动词多义性陷阱 (Polysemy)
*   **场景**: 用户说 "打开 (Open) 那个东西"。
*   **失效模式**: 系统将 "Open" 僵硬地映射为 `Switch.On`。窗帘只有 `Cover.Open` 能力，因此被过滤器误杀。
*   **解决方案**: **广义动作映射 (Broadcasting Actions)**。
    *   意图 "Open" 映射到一个能力簇：`[Switch.On, Cover.Open, Lock.Unlock, Valve.Open]`。
    *   只要设备支持其中 *任意一种* "打开" 的方式，就允许通过。

---

## 5. 泛化能力压力测试 (Phase 5 Inversion - Advanced)

为了确保系统能适应复杂的真实语义（集合、逻辑、隐式条件），我们针对方案进行了极限压力测试，并增加了以下补丁。

### 💀 Kill Shot 1: 集合操作溢出 (The Set Operation Overflow)
*   **攻击指令**: "把楼上所有的灯都关掉。" (假设楼上有 30 盏灯，用户 Top-K=10)
*   **崩溃模式**: Vector Search 只能召回相关度最高的 10 个设备，漏掉剩余 20 个。Keyword 无法匹配 "所有灯"。
*   **修复补丁 (Patch)**: **区域/组实体索引 (Entity Grouping)**。
    *   建立 "Group" 实体 (如 "Upstairs", "Living Room")。
    *   检索层直接返回 `Group(id='upstairs')`，而非 30 个独立的 `Device` 对象。由执行层负责展开设备列表。

### 💀 Kill Shot 2: 隐式依赖盲区 (Implicit Dependency Blindness)
*   **攻击指令**: "如果现在室温超过 26 度，就打开空调。"
*   **崩溃模式**: 检索层只关注 "打开空调" (Action Target)，忽略了 "室温" (Condition)。上下文中没有温度传感器数据，LLM 无法决策。
*   **修复补丁 (Patch)**: **语义依赖扩展 (Semantic Dependency Expansion)**。
    *   识别条件句 (Conditional Logic)。
    *   基于共现规则或 CoT 检索：`Intent contains "Temperature" -> Retrieve "Thermometer/Sensor"`。

### 💀 Kill Shot 3: 否定与排除陷阱 (The Negation Paradox)
*   **攻击指令**: "打开除卧室以外所有的灯。"
*   **崩溃模式**: 向量空间中 "Bedroom" 与 "Not Bedroom" 高度相似，导致 "Bedroom Lights" 反而被高优召回，挤占了真正需要的设备空间。
*   **修复补丁 (Patch)**: **元数据预过滤 (Query Pre-parsing)**。
    *   在向量检索前增加轻量级 Query Parser。
    *   提取逻辑词 (`Except`, `Not`, `Outside`) 并转化为向量数据库的 Filter 条件: `Location != 'Bedroom'`。

---

## 6. 实现逻辑 (伪代码)

为了实现上述鲁棒性，查询逻辑应接近以下伪 SQL 结构：

```sql
/* 
   用户指令: "打开 XYZ" 
   目标: 找到名字叫 'XYZ' 的设备，或者语义上能被 '打开' 的设备
*/

SELECT * FROM devices 
WHERE 
  id IN (
    -- 路径 A: 关键字匹配 (解决 "XYZ" 自定义命名)
    -- 优先级最高，不仅查 Name 也要查 Alias
    SELECT id FROM devices WHERE alias LIKE '%xyz%' OR name LIKE '%xyz%'
    
    UNION
    
    -- 路径 B: 向量语义匹配 (解决模糊指令 "太暗了", "热一点")
    SELECT id FROM vector_search('Open', limit=10)
  )
AND 
  -- 路径 C: 安全过滤 (广义能力校验)
  -- 只要支持任意一种 "打开" 相关的能力即可，不限制设备类型
  (
    capabilities CONTAINS 'Switch.On' OR 
    capabilities CONTAINS 'Cover.Open' OR
    capabilities CONTAINS 'Lock.Unlock'
  )
```

## 7. 结论

传统的“先按类型过滤，再语义搜索”的方案在智能家居环境中极其脆弱。

我们推荐采用 **“宽口径检索，严口径校验” (Broad Retrieval, Strict Validation)** 的策略。通过将 **设备名称 (XYZ)** 提升为检索的第一等公民，并使用 **能力接口 (Capabilities)** 而非物理类型 (Type) 作为过滤标准，我们可以在保证 95%+ 准确率的前提下，实现上下文的极致压缩。
