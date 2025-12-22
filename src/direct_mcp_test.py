"""
直接 MCP 客户端 - 绕过 strands 的后台线程机制来验证 meta 传递
"""
import asyncio
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession


async def test_meta_directly():
    """直接使用 MCP SDK 测试 meta 参数传递"""
    
    mcp_server_url = "http://localhost:8002/mcp"
    
    print("=" * 60)
    print("直接 MCP 客户端测试 - 验证 meta 参数传递")
    print("=" * 60)
    
    async with streamable_http_client(mcp_server_url) as (read, write, get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"Session initialized! Session ID: {get_session_id()}")
            
            # 测试多次 meta 传递
            for i in range(3):
                meta = {
                    'counter': i,
                    'run_id': f'direct-test-{i}',
                    'custom_field': f'value-{i}'
                }
                
                print(f"\n--- Run {i + 1} ---")
                print(f"Sending meta: {meta}")
                
                result = await session.call_tool('meta_test', {}, meta=meta)
                
                # 提取结果文本
                if result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            print(f"Result: {content.text}")
                
                print(f"isError: {result.isError}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_meta_directly())
