#!/usr/bin/env python3
"""
完整对比测试：直接 MCP Client vs CustomMCPClient

同时观察服务器日志来确认使用了哪个 Method
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
    
    meta = {"counter": 1, "run_id": "direct-client", "test_type": "direct"}
    
    async with streamable_http_client("http://localhost:8002/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("meta_test", {}, meta=meta)
            print(f"结果: {result.content[0].text}")


async def test_custom_client():
    """CustomMCPClient"""
    print("\n" + "=" * 60)
    print("测试 2: CustomMCPClient (继承自 Strands MCPClient)")
    print("=" * 60)
    
    meta = {"counter": 2, "run_id": "custom-client", "test_type": "custom"}
    
    mcp_client = CustomMCPClient(
        lambda: streamable_http_client("http://localhost:8002/mcp"),
        meta=meta
    )
    
    with mcp_client:
        result = await mcp_client.call_tool_async(
            tool_use_id="test-001",
            name="meta_test",
            arguments={}
        )
        # 从 ToolResult 中提取文本
        content = result.get('content', [])
        if content:
            print(f"结果: {content[0].get('text', 'N/A')}")


async def main():
    print("请观察 MCP 服务器日志，查看使用了 Method 2 还是 Method 3")
    print("服务器应该在另一个终端运行: python src/mcp_server.py")
    
    await test_direct_client()
    await asyncio.sleep(0.5)
    
    await test_custom_client()
    
    print("\n" + "=" * 60)
    print("测试完成！请检查服务器日志中的 [DEBUG META] 输出")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
