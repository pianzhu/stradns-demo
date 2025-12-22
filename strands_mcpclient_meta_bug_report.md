# Strands MCPClient Meta 参数传递 Bug 报告

## 概述

在使用 [strands-agents](https://github.com/strands-agents/sdk-python) SDK 的 `MCPClient` 与 MCP 服务器通信时，发现 **meta 参数无法正确传递到服务器端**。

| 测试方式 | Meta 传递结果 |
|---------|--------------|
| 直接使用 MCP SDK | ✅ 成功 |
| 通过 strands MCPClient | ❌ 失败 |

---

## 问题描述

### 预期行为
当通过 `ClientSession.call_tool(name, arguments, meta={...})` 调用 MCP 工具时，服务器端应该能够在 `ctx.request_context.meta` 中获取到客户端传递的自定义字段。

### 实际行为
通过 strands `MCPClient` 调用工具时，服务器端收到的 `meta` 对象只包含默认的 `progressToken=None`，自定义字段（如 `counter`、`run_id`）丢失。

```python
# 服务器端收到的 meta
meta.model_dump()        # {'progressToken': None}
meta.__pydantic_extra__  # {}  ← 应该包含自定义字段，但为空
```

---

## 环境信息

- **strands-agents**: 最新版本
- **mcp**: Python SDK
- **Python**: 3.13
- **传输协议**: Streamable HTTP

---

## 问题定位过程

### 阶段 1: 初始验证

创建了自定义 `CustomMCPClient` 类，重写 `call_tool_async` 方法以传递 `meta` 参数：

```python
class CustomMCPClient(MCPClient):
    def __init__(self, *args, meta: dict[str, Any] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._meta = meta
    
    async def call_tool_async(self, tool_use_id, name, arguments, read_timeout_seconds):
        async def _call_tool_async():
            return await session.call_tool(
                name, arguments, read_timeout_seconds, meta=self._meta  # 传递 meta
            )
        # ...
```

**结果**: 服务器仍然只收到 `progressToken=None`。

### 阶段 2: 客户端调试

添加客户端调试日志确认 meta 值：

```
[CLIENT DEBUG] self._meta = {'counter': 0, 'run_id': 'run-0'}
[CLIENT DEBUG] Calling session.call_tool with meta={'counter': 0, 'run_id': 'run-0'}
```

**结论**: 客户端 `CustomMCPClient.call_tool_async` 被正确调用，`self._meta` 值正确。

### 阶段 3: 服务端调试

在 FastMCP 服务器端添加详细日志：

```python
@mcp.tool()
def meta_test(ctx: Context) -> str:
    meta = ctx.request_context.meta
    print(f"meta.__pydantic_extra__: {meta.__pydantic_extra__}")
    # 输出: {}  ← 空！
```

**结论**: 服务器确实收到了 `meta` 对象，但 extra 字段为空。

### 阶段 4: MCP SDK 序列化验证

验证 MCP SDK 的序列化/反序列化是否正确：

```python
# 模拟客户端创建请求
meta_dict = {'counter': 0, 'run_id': 'run-0'}
_meta = types.RequestParams.Meta(**meta_dict)
params = types.CallToolRequestParams(name='test', arguments={}, _meta=_meta)

# 序列化
serialized = params.model_dump(by_alias=True, mode='json', exclude_none=True)
# 输出: {'_meta': {'counter': 0, 'run_id': 'run-0'}, 'name': 'test', ...}  ✅

# 反序列化
parsed = types.CallToolRequestParams.model_validate(serialized)
# parsed.meta.__pydantic_extra__: {'counter': 0, 'run_id': 'run-0'}  ✅
```

**结论**: MCP SDK 的序列化/反序列化完全正确。

### 阶段 5: 直接 MCP 测试（关键）

创建绕过 strands 的独立测试：

```python
async def test_meta_directly():
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool('meta_test', {}, meta={'counter': 42})
            # 结果: counter=42  ✅ 成功！
```

**结论**: 直接使用 MCP SDK 时，meta 参数**正确传递**。

---

## 根本原因分析

问题出在 strands `MCPClient` 的**后台线程机制**。

### strands MCPClient 架构

```
主线程                          后台线程
   │                              │
   ├── CustomMCPClient           │
   │      │                      │
   │      ├── call_tool_async()  │
   │      │      │               │
   │      │      └── _invoke_on_background_thread()
   │      │              │       │
   │      │              └───────├── _call_tool_async()
   │      │                      │      │
   │      │                      │      └── session.call_tool(meta=...)
   │      │                      │
   └──────┼──────────────────────┘
          │
          └── self._background_thread_session
```

strands 在后台线程中创建 `ClientSession`，然后通过 `asyncio.run_coroutine_threadsafe()` 跨线程调度协程。

### 可能的 Bug 位置

1. **后台线程的 Session 初始化方式** - strands 传递了额外的 `message_handler` 和 `elicitation_callback`
2. **跨线程状态传递问题** - 某些状态可能在跨线程时没有正确保留
3. **协程调度问题** - `_invoke_on_background_thread` 可能影响了参数传递

---

## 问题验证方法

### 验证脚本 1: 直接 MCP 测试（成功）

```bash
uv run src/direct_mcp_test.py
```

预期输出：
```
Result: counter=0, run_id=direct-test-0
Result: counter=1, run_id=direct-test-1
```

### 验证脚本 2: 通过 strands（失败）

```bash
uv run src/main.py
```

预期输出：
```
[CLIENT DEBUG] Calling session.call_tool with meta={'counter': 0, 'run_id': 'run-0'}
Result: counter=NOT_FOUND, run_id=NOT_FOUND
```

---

## 临时解决方案

在 strands SDK 修复之前，可以绕过 `MCPClient` 直接使用 MCP SDK：

```python
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

async with streamable_http_client(url) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool('tool_name', args, meta={'key': 'value'})
```

---

## 建议

1. **向 strands-agents 提交 Issue** - 附上本报告和复现步骤
2. **检查 strands 源码** - 特别是 `mcp_client.py` 中的 `_invoke_on_background_thread` 和后台线程 Session 初始化逻辑
3. **考虑 PR 修复** - 如果能定位到具体代码问题

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `src/main.py` | 使用 strands MCPClient 的测试代码 |
| `src/direct_mcp_test.py` | 直接使用 MCP SDK 的测试代码（成功） |
| `src/mcp_server.py` | FastMCP 测试服务器 |

---

*报告生成时间: 2025-12-23*
