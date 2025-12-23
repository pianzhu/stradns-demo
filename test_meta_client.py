#!/usr/bin/env python3
"""
Test MCP Client for Meta Parameter Testing

This script demonstrates how to send meta parameters to an MCP server
and verifies the server's ability to receive and process them.
"""
import asyncio
import uuid
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession


async def test_meta_transmission():
    """Test meta parameter transmission to MCP server."""
    # 服务器地址 - MCP协议使用/mcp路径
    server_url = "http://localhost:8002/mcp"
    
    # 测试meta数据
    test_meta = {
        "counter": 42,
        "run_id": str(uuid.uuid4()),
        "app_name": "test-client",
        "progressToken": "test-token-123"
    }
    
    print(f"[CLIENT] Connecting to server: {server_url}")
    print(f"[CLIENT] Sending meta: {test_meta}")
    
    try:
        async with streamable_http_client(server_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # 调用测试工具，传递meta参数
                print("\n[CLIENT] Calling meta_test tool...")
                result = await session.call_tool(
                    "meta_test",
                    {},  # 无参数
                    meta=test_meta  # 传递meta数据
                )
                
                print(f"[CLIENT] Received response: {result}")
                print(f"[CLIENT] Response status: {'ERROR' if result.isError else 'SUCCESS'}")
                
                if result.content:
                    print("[CLIENT] Response content:")
                    for content in result.content:
                        if hasattr(content, 'text'):
                            print(f"  - {content.text}")
    
    except Exception as e:
        print(f"[CLIENT] Error: {e}")
        import traceback
        traceback.print_exc()


async def test_multiple_meta_calls():
    """Test multiple meta parameter calls to ensure consistency."""
    server_url = "http://localhost:8002/mcp"
    
    async with streamable_http_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 测试多次调用，每次使用不同的meta数据
            for i in range(3):
                test_meta = {
                    "counter": i,
                    "run_id": f"test-run-{i}",
                    "app_name": "test-client",
                    "iteration": i
                }
                
                print(f"\n[CLIENT] Calling meta_test with counter={i}...")
                result = await session.call_tool(
                    "meta_test",
                    {},
                    meta=test_meta
                )
                
                if result.content and hasattr(result.content[0], 'text'):
                    print(f"[CLIENT] Response: {result.content[0].text}")


if __name__ == "__main__":
    print("=== MCP Meta Parameter Test ===\n")
    
    # 运行单次测试
    print("1. Running single meta test...")
    asyncio.run(test_meta_transmission())
    
    # 运行多次测试
    print("\n2. Running multiple meta tests...")
    asyncio.run(test_multiple_meta_calls())
    
    print("\n=== Test Complete ===")
