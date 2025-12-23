#!/usr/bin/env python3
"""
直接测试 CustomMCPClient

不使用 Agent，只测试 MCPClient 的 meta 传递
"""
import asyncio
from mcp.client.streamable_http import streamable_http_client

# 从 main.py 导入 CustomMCPClient
import sys
sys.path.insert(0, 'src')
from main import CustomMCPClient


async def test_custom_client_directly():
    """直接测试 CustomMCPClient，不通过 Agent"""
    print("\n" + "=" * 60)
    print("测试: CustomMCPClient 直接调用")
    print("=" * 60)
    
    mcp_server_url = "http://localhost:8002/mcp"
    
    # 创建带有 meta 的 CustomMCPClient
    meta = {"counter": 42, "run_id": "custom-direct", "source": "test"}
    
    mcp_client = CustomMCPClient(
        lambda: streamable_http_client(mcp_server_url),
        meta=meta
    )
    
    with mcp_client:
        print(f"[Test] Client started, meta={mcp_client._meta}")
        
        # 直接调用 call_tool_async
        print("\n--- 测试 call_tool_async ---")
        result = await mcp_client.call_tool_async(
            tool_use_id="test-001",
            name="meta_test",
            arguments={}
        )
        print(f"结果: {result}")
        
        # 更新 meta 后再次调用
        print("\n--- 更新 meta 后再次调用 ---")
        mcp_client.set_meta({"counter": 100, "run_id": "custom-updated"})
        result = await mcp_client.call_tool_async(
            tool_use_id="test-002",
            name="meta_test",
            arguments={}
        )
        print(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(test_custom_client_directly())
