#!/usr/bin/env python3
"""
精确模拟 Strands MCPClient 的调用模式

Strands MCPClient 的关键特点：
1. 后台线程持有一个长期运行的事件循环
2. 会话在后台线程中建立并保持
3. 调用通过 run_coroutine_threadsafe 跨线程执行

这个脚本精确复制这种模式来定位问题。
"""
import asyncio
import threading
from concurrent import futures
from typing import Any, cast
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession


class SimulatedStrandsMCPClient:
    """精确模拟 Strands MCPClient 的行为"""
    
    def __init__(self, server_url: str, meta: dict[str, Any] | None = None):
        self.server_url = server_url
        self._meta = meta
        
        # 后台线程相关
        self._background_thread: threading.Thread | None = None
        self._background_thread_event_loop: asyncio.AbstractEventLoop | None = None
        self._background_thread_session: ClientSession | None = None
        
        # 同步事件
        self._init_future: futures.Future = futures.Future()
        self._close_future: asyncio.Future | None = None
        
        # 连接上下文管理器
        self._transport_cm = None
        self._session_cm = None
    
    def start(self):
        """启动后台线程"""
        print("[SimClient] Starting background thread...")
        self._background_thread = threading.Thread(target=self._background_task, daemon=True)
        self._background_thread.start()
        
        # 等待初始化完成
        self._init_future.result(timeout=10.0)
        print("[SimClient] Background thread ready!")
        return self
    
    def stop(self):
        """停止后台线程"""
        print("[SimClient] Stopping...")
        if self._close_future:
            self._background_thread_event_loop.call_soon_threadsafe(
                self._close_future.set_result, None
            )
        if self._background_thread:
            self._background_thread.join(timeout=5.0)
        print("[SimClient] Stopped.")
    
    def _background_task(self):
        """后台线程任务 - 精确复制 Strands 模式"""
        print("[BgThread] Setting up event loop...")
        self._background_thread_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._background_thread_event_loop)
        self._background_thread_event_loop.run_until_complete(self._async_background_thread())
    
    async def _async_background_thread(self):
        """异步后台线程 - 保持会话活跃"""
        print("[BgThread] Establishing connection...")
        
        try:
            # 建立连接
            self._transport_cm = streamable_http_client(self.server_url)
            read, write, _ = await self._transport_cm.__aenter__()
            
            # 建立会话
            self._session_cm = ClientSession(read, write)
            self._background_thread_session = await self._session_cm.__aenter__()
            await self._background_thread_session.initialize()
            
            print("[BgThread] Session established!")
            
            # 设置关闭 future
            self._close_future = asyncio.get_event_loop().create_future()
            
            # 通知主线程初始化完成
            self._init_future.set_result(True)
            
            # 等待关闭信号
            await self._close_future
            
        except Exception as e:
            print(f"[BgThread] Error: {e}")
            self._init_future.set_exception(e)
        finally:
            # 清理
            if self._session_cm:
                await self._session_cm.__aexit__(None, None, None)
            if self._transport_cm:
                await self._transport_cm.__aexit__(None, None, None)
            print("[BgThread] Cleaned up.")
    
    def _invoke_on_background_thread(self, coro) -> futures.Future:
        """在后台线程的事件循环中执行协程"""
        return asyncio.run_coroutine_threadsafe(
            coro, 
            self._background_thread_event_loop
        )
    
    def call_tool_sync(self, name: str, arguments: dict[str, Any] | None = None):
        """同步调用工具 - 使用 meta"""
        print(f"[MainThread] Calling tool '{name}' with meta={self._meta}")
        
        async def _call_tool_async():
            # 这是关键：在后台线程中调用 session.call_tool
            result = await cast(ClientSession, self._background_thread_session).call_tool(
                name, arguments, meta=self._meta
            )
            return result
        
        future = self._invoke_on_background_thread(_call_tool_async())
        return future.result(timeout=30.0)
    
    async def call_tool_async(self, name: str, arguments: dict[str, Any] | None = None):
        """异步调用工具 - 使用 meta"""
        print(f"[MainThread/Async] Calling tool '{name}' with meta={self._meta}")
        
        async def _call_tool_async():
            result = await cast(ClientSession, self._background_thread_session).call_tool(
                name, arguments, meta=self._meta
            )
            return result
        
        future = self._invoke_on_background_thread(_call_tool_async())
        return await asyncio.wrap_future(future)


async def test_simulated_strands():
    """测试模拟的 Strands MCPClient"""
    print("\n" + "=" * 60)
    print("测试: 模拟 Strands MCPClient (带 meta)")
    print("=" * 60)
    
    meta = {"counter": 999, "run_id": "simulated-strands", "source": "sim"}
    
    client = SimulatedStrandsMCPClient(
        "http://localhost:8002/mcp",
        meta=meta
    )
    
    try:
        client.start()
        
        # 测试同步调用
        print("\n--- 同步调用测试 ---")
        result = client.call_tool_sync("meta_test", {})
        print(f"结果: {result.content[0].text if result.content else 'None'}")
        
        # 测试异步调用
        print("\n--- 异步调用测试 ---")
        result = await client.call_tool_async("meta_test", {})
        print(f"结果: {result.content[0].text if result.content else 'None'}")
        
    finally:
        client.stop()


async def main():
    await test_simulated_strands()


if __name__ == "__main__":
    asyncio.run(main())
