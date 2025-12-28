# 智能家居控制 Agent 延迟优化设计方案

> 创建日期: 2025-12-27
> 状态: 设计讨论完成，待实施

---

## 1. 背景与目标

### 1.1 问题描述

智能家居控制 Agent 需要完成以下任务链：
1. **识别设备** - 从用户自然语言中识别目标设备
2. **获取规格** - 查询设备命令的 Schema 规格
3. **生成命令** - 根据 Schema 生成正确的命令参数并执行

**用户操作特点：**
- 一次操作可能包含多个设备、多个命令
- 语言中存在指代词（"它"、"那个"）
- 可能关联上一轮对话的设备

### 1.2 约束条件

| 类型 | 约束 |
|------|------|
| **核心目标** | 最小化端到端延迟 |
| **硬约束** | 准确率不降、不换模型、保留推理能力 |

### 1.3 当前瓶颈

```
用户输入 → [LLM: 筛选设备] → [查 Schema] → [LLM: 生成命令] → 执行
              RTT 1             RTT 2           RTT 3

总延迟 ≈ 10000ms+ (3 次串行 LLM/网络调用)
```

---

## 2. 现状分析

| 项目 | 现状 |
|------|------|
| 设备管理 | 静态配置，部署时确定 |
| 设备数量 | 50-100 个 |
| Schema 特点 | 已做精简，包含必要的 description |
| 设备筛选 | 通过 LLM 从设备列表中挑选 |

---

## 3. 优化方案：分层架构

### 3.1 架构总览

```
┌─────────────────────────────────────────────────────┐
│                    用户输入                          │
└─────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│  Layer 1: Embedding 粗召回 (Top-20)                 │  ~50ms
│  目标：不漏，宁多勿少                                 │
└─────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: 8B 小模型精筛选                            │  ~100ms
│  输入：20 个候选 + 上下文设备 + 最近对话              │
│  输出：最终 3-5 个目标设备                           │
└─────────────────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3: 主模型生成命令参数                         │  ~500ms
│  输入：目标设备的精简 Schema                         │
└─────────────────────────────────────────────────────┘

总延迟：~650ms (vs 原来 ~1500ms，提升约 2.3 倍)
```

### 3.2 Layer 1: Embedding 粗召回

**目的：** 替代第一个 LLM 调用，用向量相似度在本地毫秒级召回候选设备。

**离线阶段：**
```python
# 为每个设备构造丰富的语义描述
device_text = f"{device_name} {别名} {房间} {功能关键词}"

# 示例
"客厅空调 大厅空调 客厅 制冷 制热 温度 冷气 风速 风"
"卧室灯 主卧灯 卧室 照明 开灯 关灯 调光 亮度"

# 生成 Embedding 向量存储
device_embedding = embed_model.encode(device_text)
```

**在线阶段：**
```python
# 1. 用户输入分句（处理多设备场景）
segments = split_into_segments(user_input)
# ["把客厅灯关了", "空调调到26度"]

# 2. 拼接上下文（处理多轮对话）
context = recent_turns + current_input

# 3. 对每个片段召回 Top-K
candidates = set()
for seg in segments:
    candidates.update(embedding_recall(seg, top_k=10))

# 4. 强制注入上轮提及的设备
candidates.update(recent_mentioned_devices)
```

**关键设计点：**

| 问题 | 解决方案 |
|------|----------|
| 一句话多设备 | Query 分解 → 分段召回 → 合并去重 |
| 语言省略/俗语 | 设备描述预埋同义词、功能词 |
| 上下文依赖 | 拼接历史对话 + 强制注入最近设备 |

### 3.3 Layer 2: 8B 小模型精筛选

**目的：** 从 Embedding 召回的候选设备中精确筛选目标设备。

**为什么需要这一层：**
- Embedding 召回是"宁多勿少"，会有误召回
- 需要 LLM 能力处理复杂指代（"它"、"那个凉快的东西"）
- 8B 模型处理 20 个候选设备足够准确

**Prompt 设计：**
```
[系统]
你是设备筛选助手。根据用户指令，从候选设备列表中选出用户想要操作的设备。

[上下文]
最近操作的设备：客厅空调
最近对话：
- 用户：把客厅空调打开
- 系统：已打开客厅空调

[当前指令]
再调高一点温度

[候选设备]
1. 客厅空调
2. 客厅灯
3. 卧室空调
4. 卧室灯
...

[输出格式]
请输出涉及的设备编号，用逗号分隔。例如：1,3
```

**模型选择：**

| 模型 | 延迟 | 适用设备数 |
|------|------|-----------|
| Qwen2-7B / Llama3-8B 本地 | ~100ms | 20 个候选 |
| GPT-3.5 Turbo | ~300ms | 50+ 候选（如需） |
| Gemini 1.5 Flash | ~200ms | 50+ 候选（如需） |

### 3.4 Layer 3: 主模型命令生成

**目的：** 根据目标设备的 Schema 生成精确的命令参数。

**Prompt 设计：**
```
[用户指令]
把客厅空调调到26度，风速调大

[目标设备及命令规格]
[ac_living_room] 客厅空调
- set_temperature(value: int, 范围 16-30, 设置目标温度)
- set_fan_speed(speed: low|medium|high|auto, 设置风速)
- power_on() / power_off()

[输出格式]
请输出 JSON 数组：
[
  {"device_id": "xxx", "command": "xxx", "params": {...}},
  ...
]
```

---

## 4. 兜底策略

| 场景 | 检测条件 | 兜底措施 |
|------|----------|----------|
| Embedding 召回置信度低 | Top-1 相似度 < 0.5 | 降级到 LLM 筛选 |
| 小模型输出格式错误 | JSON 解析失败 | Retry 一次，仍失败则用主模型 |
| 命令生成失败 | Schema 校验不通过 | 返回友好错误，请用户确认 |

---

## 5. 预期收益

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 端到端延迟 | ~1500ms | ~650ms | **2.3x** |
| LLM 调用次数 | 2-3 次（大模型） | 1 次大模型 + 1 次小模型 | 成本降低 |
| RTT 数量 | 3 | 1-2 | 减少串行依赖 |

---

## 6. 多轮对话上下文管理

### 6.1 设计原则

- **不使用 LLM 做总结**：避免在关键路径上增加延迟
- **结构化存储**：用代码直接提取和保存关键信息
- **异步更新**：状态更新不阻塞用户响应

### 6.2 ConversationState 数据结构

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Command:
    device_id: str
    action: str
    params: dict
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class Turn:
    user_input: str
    commands: List[Command]
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ConversationState:
    # 最近操作的设备 ID（最多 5 个，按时间倒序）
    recent_devices: List[str] = field(default_factory=list)
    
    # 最近提及的房间（最多 3 个）
    recent_rooms: List[str] = field(default_factory=list)
    
    # 上一轮执行的命令（用于"再来一次"场景）
    last_commands: List[Command] = field(default_factory=list)
    
    # 最近 N 轮原始对话（保留 3-5 轮，用于兜底）
    recent_turns: List[Turn] = field(default_factory=list)
    
    # 会话 ID
    session_id: str = ""
```

### 6.3 状态更新逻辑

```python
def update_state(state: ConversationState, 
                 user_input: str,
                 result: ExecutionResult,
                 device_registry: DeviceRegistry) -> None:
    """
    每轮对话结束后更新状态（纯代码逻辑，无 LLM 调用）
    耗时：< 1ms
    """
    
    # 1. 更新 recent_devices
    executed_devices = [cmd.device_id for cmd in result.commands]
    for dev_id in executed_devices:
        if dev_id in state.recent_devices:
            state.recent_devices.remove(dev_id)
        state.recent_devices.insert(0, dev_id)
    state.recent_devices = state.recent_devices[:5]
    
    # 2. 更新 recent_rooms（从设备元数据查询）
    rooms = []
    for dev_id in state.recent_devices:
        room = device_registry.get_room(dev_id)
        if room and room not in rooms:
            rooms.append(room)
    state.recent_rooms = rooms[:3]
    
    # 3. 保存 last_commands
    state.last_commands = result.commands
    
    # 4. 追加到 recent_turns
    turn = Turn(
        user_input=user_input,
        commands=result.commands,
        success=result.success
    )
    state.recent_turns.append(turn)
    state.recent_turns = state.recent_turns[-5:]  # 只保留最近 5 轮
```

### 6.4 在 Prompt 中注入上下文

```python
def build_context_prompt(state: ConversationState, 
                         device_registry: DeviceRegistry) -> str:
    """
    构建注入到 Prompt 中的上下文信息
    """
    lines = ["[对话上下文]"]
    
    # 最近操作的设备
    if state.recent_devices:
        device_names = [device_registry.get_name(d) for d in state.recent_devices]
        lines.append(f"最近操作的设备：{', '.join(device_names)}")
    
    # 最近的房间
    if state.recent_rooms:
        lines.append(f"最近提及的房间：{', '.join(state.recent_rooms)}")
    
    # 上一轮命令摘要
    if state.last_commands:
        last_cmd_desc = format_commands_brief(state.last_commands)
        lines.append(f"上一轮操作：{last_cmd_desc}")
    
    # 最近 2 轮对话（精简版）
    if state.recent_turns:
        lines.append("\n最近对话：")
        for turn in state.recent_turns[-2:]:
            lines.append(f"- 用户：{turn.user_input[:50]}...")
            lines.append(f"- 结果：{'成功' if turn.success else '失败'}")
    
    return "\n".join(lines)
```

### 6.5 处理连续快速输入

```python
import asyncio

class ConversationManager:
    def __init__(self):
        self.state = ConversationState()
        self._update_lock = asyncio.Lock()
    
    async def handle_request(self, user_input: str) -> Response:
        # 1. 读取当前状态（不需要锁，读取 committed 状态）
        current_state = self.state
        
        # 2. 执行主流程
        result = await self.execute(user_input, current_state)
        
        # 3. 异步更新状态（不阻塞响应）
        asyncio.create_task(self._async_update(user_input, result))
        
        return result.response
    
    async def _async_update(self, user_input: str, result: ExecutionResult):
        async with self._update_lock:
            update_state(self.state, user_input, result, self.device_registry)
```

### 6.6 典型场景示例

**场景 1：连续操作同一设备**
```
用户：把客厅空调打开
→ state.recent_devices = ["ac_living_room"]

用户：调到 26 度
→ Prompt 注入：最近操作的设备：客厅空调
→ 模型正确理解"调到 26 度"指的是客厅空调
```

**场景 2：使用指代词**
```
用户：把卧室灯打开
→ state.recent_devices = ["light_bedroom"]

用户：把它调暗一点
→ Prompt 注入：最近操作的设备：卧室灯
→ 模型正确理解"它"指的是卧室灯
```

**场景 3：房间级指代**
```
用户：把客厅空调打开
→ state.recent_rooms = ["客厅"]

用户：这个房间的灯也打开
→ Prompt 注入：最近提及的房间：客厅
→ 模型正确理解"这个房间"指的是客厅
```

---

## 7. 待确定事项

1. **Embedding 模型选择**
   - 本地：BGE-M3 / text2vec-chinese
   - API：OpenAI text-embedding-3-small
   
2. **8B 模型选择**
   - 本地部署：Qwen2-7B / Llama3-8B
   - 需验证中文设备筛选准确率

3. **上下文窗口长度**
   - 保留最近 N 轮对话（建议 N=3-5）

4. 单次批量推理 —— "一个 Prompt 塞多个设备多个命令，LLM 能理解吗？格式不会乱吗？"
 
5. 指代消解 —— "'把它关了' 这种话，不先跑一轮 LLM 怎么知道 '它' 是什么？"

6. 整体可行性 —— "我的场景比你假设的复杂，想先对齐一下现状"

## 7. 下一步行动

- [ ] 验证 Embedding 召回准确率（构造测试集）
- [ ] 验证 8B 模型筛选准确率（复杂语言场景）
- [ ] 设计 Prompt 模板并测试
- [ ] 实现分层架构原型
- [ ] 端到端延迟测试
