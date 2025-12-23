#!/usr/bin/env python3
"""
深入调试 Meta 参数传递流程

目标：对比以下两种调用方式：
1. 直接使用 ClientSession.call_tool (Method 2 成功)
2. 通过自定义包装调用 (Method 2 失败?)

测试假设：问题可能与以下因素有关：
- 异步上下文管理
- 连接生命周期
- HTTP 请求差异
"""
import asyncio
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession
from mcp.types import RequestParams, CallToolRequest, CallToolRequestParams


async def test_method_a_direct():
    """方式A: 完全直接调用 - 基准测试"""
    print("\n" + "=" * 60)
    print("方式 A: 完全直接调用 ClientSession.call_tool")
    print("=" * 60)
    
    server_url = "http://localhost:8002/mcp"
    meta = {"counter": 1, "run_id": "method-a", "source": "direct"}
    
    async with streamable_http_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("meta_test", {}, meta=meta)
            print(f"结果: {result.content[0].text if result.content else 'None'}")


async def test_method_b_wrapped():
    """方式B: 包装一层函数调用"""
    print("\n" + "=" * 60)
    print("方式 B: 包装一层函数调用")
    print("=" * 60)
    
    server_url = "http://localhost:8002/mcp"
    meta = {"counter": 2, "run_id": "method-b", "source": "wrapped"}
    
    async def wrapped_call_tool(session: ClientSession, name: str, args: dict, meta_data: dict):
        """简单包装函数"""
        return await session.call_tool(name, args, meta=meta_data)
    
    async with streamable_http_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await wrapped_call_tool(session, "meta_test", {}, meta)
            print(f"结果: {result.content[0].text if result.content else 'None'}")


async def test_method_c_class_wrapper():
    """方式C: 使用类包装，模拟 MCPClient 结构"""
    print("\n" + "=" * 60)
    print("方式 C: 使用类包装 (模拟 MCPClient)")
    print("=" * 60)
    
    class SimpleWrapper:
        def __init__(self, server_url: str, meta: dict):
            self.server_url = server_url
            self._meta = meta
            self._session: ClientSession | None = None
        
        async def call_tool_async(self, name: str, args: dict):
            """模拟 MCPClient.call_tool_async"""
            if self._session is None:
                raise RuntimeError("Session not initialized")
            print(f"[DEBUG] Calling with meta: {self._meta}")
            return await self._session.call_tool(name, args, meta=self._meta)
    
    server_url = "http://localhost:8002/mcp"
    meta = {"counter": 3, "run_id": "method-c", "source": "class-wrapped"}
    
    wrapper = SimpleWrapper(server_url, meta)
    
    async with streamable_http_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            wrapper._session = session
            result = await wrapper.call_tool_async("meta_test", {})
            print(f"结果: {result.content[0].text if result.content else 'None'}")


async def test_method_d_separate_connection():
    """方式D: 分离连接和调用（模拟 Strands 模式）"""
    print("\n" + "=" * 60)
    print("方式 D: 分离连接生命周期")
    print("=" * 60)
    
    server_url = "http://localhost:8002/mcp"
    meta = {"counter": 4, "run_id": "method-d", "source": "separate-conn"}
    
    # 保存连接组件
    read_stream = None
    write_stream = None
    session = None
    
    try:
        # 手动进入上下文
        cm = streamable_http_client(server_url)
        read_stream, write_stream, _ = await cm.__aenter__()
        
        session_cm = ClientSession(read_stream, write_stream)
        session = await session_cm.__aenter__()
        await session.initialize()
        
        # 在外部调用
        async def external_call():
            return await session.call_tool("meta_test", {}, meta=meta)
        
        result = await external_call()
        print(f"结果: {result.content[0].text if result.content else 'None'}")
        
    finally:
        if session:
            await session_cm.__aexit__(None, None, None)
        if read_stream:
            await cm.__aexit__(None, None, None)


async def test_method_e_thread_simulation():
    """方式E: 模拟跨线程调用（类似 Strands）"""
    print("\n" + "=" * 60)
    print("方式 E: 模拟跨线程调用 (asyncio.run_coroutine_threadsafe)")
    print("=" * 60)
    
    import threading
    from concurrent.futures import Future
    
    server_url = "http://localhost:8002/mcp"
    meta = {"counter": 5, "run_id": "method-e", "source": "thread-sim"}
    
    result_holder = {"result": None, "error": None}
    
    def background_thread_task():
        """在后台线程中运行事件循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_session():
            async with streamable_http_client(server_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool("meta_test", {}, meta=meta)
        
        try:
            result = loop.run_until_complete(run_session())
            result_holder["result"] = result
        except Exception as e:
            result_holder["error"] = e
        finally:
            loop.close()
    
    # 在后台线程中运行
    thread = threading.Thread(target=background_thread_task)
    thread.start()
    thread.join()
    
    if result_holder["error"]:
        print(f"错误: {result_holder['error']}")
    else:
        result = result_holder["result"]
        print(f"结果: {result.content[0].text if result.content else 'None'}")


async def main():
    print("=" * 60)
    print("Meta 参数传递深度调试")
    print("=" * 60)
    
    await test_method_a_direct()
    await asyncio.sleep(0.3)
    
    await test_method_b_wrapped()
    await asyncio.sleep(0.3)
    
    await test_method_c_class_wrapper()
    await asyncio.sleep(0.3)
    
    await test_method_d_separate_connection()
    await asyncio.sleep(0.3)
    
    await test_method_e_thread_simulation()
    
    print("\n" + "=" * 60)
    print("调试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
