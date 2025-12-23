#!/usr/bin/env python3
"""
服务端调试 - 输出详细的请求解析信息

用增强的日志来追踪请求从接收到解析的完整流程
"""
import uvicorn
import json
from typing import Any
from mcp.server.fastmcp import FastMCP, Context
from mcp.shared.context import RequestContext


# 创建 MCP 服务器实例
mcp = FastMCP("debug-meta-server")


@mcp.tool()
def debug_meta(ctx: Context) -> str:
    """详细调试 meta 解析过程"""
    
    rc = ctx.request_context
    
    results = []
    results.append("=" * 50)
    results.append("服务端 Meta 解析详细信息")
    results.append("=" * 50)
    
    # 1. 检查 rc 对象
    results.append(f"\n[1] RequestContext 基本信息:")
    results.append(f"    rc type: {type(rc)}")
    results.append(f"    rc.request_id: {rc.request_id}")
    
    # 2. 检查 rc.meta
    results.append(f"\n[2] rc.meta 分析:")
    results.append(f"    rc.meta: {rc.meta}")
    results.append(f"    rc.meta type: {type(rc.meta)}")
    
    if rc.meta is not None:
        results.append(f"    rc.meta.__dict__: {rc.meta.__dict__}")
        results.append(f"    rc.meta.progressToken: {getattr(rc.meta, 'progressToken', 'N/A')}")
        
        # 检查 __pydantic_extra__
        extra = getattr(rc.meta, '__pydantic_extra__', None)
        results.append(f"    rc.meta.__pydantic_extra__: {extra}")
        results.append(f"    rc.meta.__pydantic_extra__ type: {type(extra)}")
        
        if extra:
            results.append(f"    ===> Method 2 可以获取数据!")
            for k, v in extra.items():
                results.append(f"         {k}: {v}")
        else:
            results.append(f"    ===> Method 2 失败 (__pydantic_extra__ 为空)")
        
        # 尝试 model_dump
        if hasattr(rc.meta, 'model_dump'):
            dump = rc.meta.model_dump()
            results.append(f"    rc.meta.model_dump(): {dump}")
    else:
        results.append(f"    rc.meta is None!")
    
    # 3. 检查 rc.request (原始请求)
    results.append(f"\n[3] rc.request 分析:")
    results.append(f"    rc.request: {rc.request}")
    results.append(f"    rc.request type: {type(rc.request)}")
    
    if hasattr(rc, 'request') and rc.request is not None:
        # 检查是否有 _body
        if hasattr(rc.request, '_body'):
            body = rc.request._body
            results.append(f"    rc.request._body exists: {body is not None}")
            if body:
                results.append(f"    rc.request._body (first 500 chars): {body[:500]}")
                try:
                    parsed = json.loads(body)
                    results.append(f"    Parsed body: {json.dumps(parsed, indent=2)[:500]}")
                    
                    # 提取 _meta
                    params = parsed.get('params', {})
                    _meta = params.get('_meta')
                    meta_without_underscore = params.get('meta')
                    
                    results.append(f"    params._meta: {_meta}")
                    results.append(f"    params.meta: {meta_without_underscore}")
                    
                    if _meta:
                        results.append(f"    ===> Method 3 可以从 _meta 获取数据!")
                    elif meta_without_underscore:
                        results.append(f"    ===> Method 3 可以从 meta 获取数据!")
                    else:
                        results.append(f"    ===> Method 3 也失败!")
                except Exception as e:
                    results.append(f"    Parse error: {e}")
        else:
            results.append(f"    rc.request 没有 _body 属性")
            results.append(f"    rc.request attrs: {dir(rc.request)}")
    else:
        results.append(f"    rc.request is None or not available")
    
    # 4. 检查 params.meta (通过 request.params)
    results.append(f"\n[4] 检查 request.params.meta:")
    if hasattr(rc, 'request') and rc.request is not None:
        if hasattr(rc.request, 'params'):
            params = rc.request.params
            results.append(f"    request.params: {params}")
            if hasattr(params, 'meta'):
                params_meta = params.meta
                results.append(f"    params.meta: {params_meta}")
                if params_meta:
                    extra = getattr(params_meta, '__pydantic_extra__', None)
                    results.append(f"    params.meta.__pydantic_extra__: {extra}")
    
    # 打印到服务器控制台
    output = "\n".join(results)
    print(output)
    
    return output


def main():
    print("=" * 60)
    print("启动调试 MCP 服务器")
    print("=" * 60)
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
