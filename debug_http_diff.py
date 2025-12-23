#!/usr/bin/env python3
"""
深入调试：对比直接 MCP Client 和 CustomMCPClient 的请求差异

目标：找出为什么直接调用 Method 2 成功，而通过 Strands 调用 Method 2 失败
"""
import asyncio
import json
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession
from mcp.types import RequestParams, CallToolRequest, CallToolRequestParams, ClientRequest

import sys
sys.path.insert(0, 'src')


async def inspect_request_construction():
    """检查请求构造过程"""
    print("\n" + "=" * 60)
    print("检查 MCP 请求构造过程")
    print("=" * 60)
    
    meta = {"counter": 99, "run_id": "test", "custom": "value"}
    
    # 模拟 ClientSession.call_tool 的请求构造过程
    # 来自 mcp/client/session.py:378-391
    
    # 步骤 1: 创建 RequestParams.Meta
    _meta = RequestParams.Meta(**meta)
    print(f"\n1. RequestParams.Meta(**meta):")
    print(f"   _meta = {_meta}")
    print(f"   _meta.model_dump() = {_meta.model_dump()}")
    print(f"   _meta.__pydantic_extra__ = {getattr(_meta, '__pydantic_extra__', 'N/A')}")
    
    # 步骤 2: 创建 CallToolRequestParams
    params = CallToolRequestParams(name="meta_test", arguments={}, _meta=_meta)
    print(f"\n2. CallToolRequestParams(name='meta_test', arguments={{}}, _meta=_meta):")
    print(f"   params = {params}")
    print(f"   params.model_dump() = {params.model_dump()}")
    print(f"   params.model_dump(by_alias=True) = {params.model_dump(by_alias=True)}")
    
    # 步骤 3: 创建 CallToolRequest
    request = CallToolRequest(params=params)
    print(f"\n3. CallToolRequest(params=params):")
    print(f"   request = {request}")
    print(f"   request.model_dump() = {request.model_dump()}")
    print(f"   request.model_dump(by_alias=True) = {request.model_dump(by_alias=True)}")
    
    # 步骤 4: 创建 ClientRequest
    client_request = ClientRequest(request)
    print(f"\n4. ClientRequest(request):")
    print(f"   client_request = {client_request}")
    
    # 检查 JSON 序列化
    print(f"\n5. JSON 序列化:")
    json_str = request.model_dump_json(by_alias=True)
    print(f"   model_dump_json(by_alias=True) = {json_str}")
    
    # 解析回来检查
    parsed = json.loads(json_str)
    print(f"\n6. 解析后的 JSON:")
    print(f"   {json.dumps(parsed, indent=2)}")


async def compare_actual_requests():
    """对比实际发送的请求"""
    print("\n" + "=" * 60)
    print("对比实际发送的 HTTP 请求")
    print("=" * 60)
    
    from mcp.client.session import ClientSession
    
    # Monkey-patch send_request 来捕获请求
    original_send_request = ClientSession.send_request
    
    async def patched_send_request(self, request, result_type, **kwargs):
        print(f"\n[CAPTURED REQUEST]")
        print(f"  request = {request}")
        print(f"  request.root = {request.root}")
        if hasattr(request.root, 'params'):
            params = request.root.params
            print(f"  params = {params}")
            print(f"  params.model_dump() = {params.model_dump()}")
            print(f"  params.model_dump(by_alias=True) = {params.model_dump(by_alias=True)}")
            if hasattr(params, 'meta') and params.meta:
                print(f"  params.meta = {params.meta}")
                print(f"  params.meta.__pydantic_extra__ = {getattr(params.meta, '__pydantic_extra__', 'N/A')}")
        return await original_send_request(self, request, result_type, **kwargs)
    
    ClientSession.send_request = patched_send_request
    
    try:
        meta = {"counter": 123, "run_id": "captured", "extra_field": "test"}
        
        print("\n--- 直接 MCP Client 请求 ---")
        async with streamable_http_client("http://localhost:8002/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("meta_test", {}, meta=meta)
        
        # 恢复原始方法后测试 CustomMCPClient
        # (CustomMCPClient 使用相同的 ClientSession，所以也会被捕获)
        
    finally:
        ClientSession.send_request = original_send_request


async def main():
    await inspect_request_construction()
    await asyncio.sleep(0.5)
    await compare_actual_requests()


if __name__ == "__main__":
    asyncio.run(main())
