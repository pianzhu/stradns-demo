#!/usr/bin/env python3
"""
对比测试：调用 debug_meta 工具，观察两种客户端的差异

运行前请先启动调试服务器：python debug_server.py
"""
import asyncio
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

import sys
sys.path.insert(0, 'src')
from main import CustomMCPClient


async def test_direct_client():
    """直接 MCP Client"""
    print("\n" + "=" * 60)
    print("测试 1: 直接 MCP Client (ClientSession)")
    print("=" * 60)
    
    meta = {"counter": 111, "run_id": "direct", "source": "direct-client"}
    
    async with streamable_http_client("http://localhost:8002/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("debug_meta", {}, meta=meta)
            print(f"\n>>> 客户端收到的响应:")
            print(result.content[0].text if result.content else "None")


async def test_custom_client():
    """CustomMCPClient (继承自 Strands)"""
    print("\n" + "=" * 60)
    print("测试 2: CustomMCPClient (继承自 Strands MCPClient)")
    print("=" * 60)
    
    meta = {"counter": 222, "run_id": "custom", "source": "custom-client"}
    
    mcp_client = CustomMCPClient(
        lambda: streamable_http_client("http://localhost:8002/mcp"),
        meta=meta
    )
    
    with mcp_client:
        result = await mcp_client.call_tool_async(
            tool_use_id="test-001",
            name="debug_meta",
            arguments={}
        )
        content = result.get('content', [])
        if content:
            print(f"\n>>> 客户端收到的响应:")
            print(content[0].get('text', 'N/A'))


async def main():
    print("=" * 60)
    print("请确保调试服务器正在运行: python debug_server.py")
    print("=" * 60)
    
    await test_direct_client()
    await asyncio.sleep(1)
    
    await test_custom_client()
    
    print("\n" + "=" * 60)
    print("对比完成！")
    print("请查看服务器日志中的详细差异")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
