"""
MCP Server with Meta Parameter Support

This module demonstrates how to properly access meta parameters
passed from MCP clients in FastMCP tool handlers.
"""
import uvicorn
import json
from typing import Any
from mcp.server.fastmcp import FastMCP, Context


# 创建 MCP 服务器实例
mcp = FastMCP("meta-test-server")


def get_meta_from_context(ctx: Context) -> dict[str, Any]:
    """
    从 Context 中提取完整的 meta 数据。
    
    Meta 数据可能存在于多个位置，该函数按优先级尝试获取：
    1. rc.request.params.meta (model_dump) - Pydantic 模型的完整序列化
    2. rc.meta.__pydantic_extra__ - 额外字段存储
    3. 原始 request body - 从 HTTP 请求体直接解析 (回退方案)
    
    Returns:
        包含所有 meta 字段的字典，如果没有 meta 则返回空字典
    """
    rc = ctx.request_context
    
    # 添加详细日志，记录各个阶段的meta获取情况
    print(f"\n[DEBUG META] Entering get_meta_from_context")
    print(f"[DEBUG META] rc: {type(rc)}, hasattr(rc, 'request'): {hasattr(rc, 'request')}")
    
    if hasattr(rc, 'request'):
        print(f"[DEBUG META] rc.request: {type(rc.request)}, hasattr(params): {hasattr(rc.request, 'params')}")
        if hasattr(rc.request, '_body'):
            print(f"[DEBUG META] rc.request has _body: True")
        else:
            print(f"[DEBUG META] rc.request has _body: False")
    
    print(f"[DEBUG META] rc.meta: {rc.meta}")
    if rc.meta is not None:
        print(f"[DEBUG META] rc.meta type: {type(rc.meta)}")
        print(f"[DEBUG META] rc.meta.__dict__: {rc.meta.__dict__}")
        print(f"[DEBUG META] rc.meta.__pydantic_extra__: {getattr(rc.meta, '__pydantic_extra__', 'NOT_FOUND')}")
    
    # 方法 1: 从 request.params.meta 获取并检查 __pydantic_extra__
    print(f"\n[DEBUG META] Trying Method 1: rc.request.params.meta")
    if hasattr(rc, 'request') and hasattr(rc.request, 'params'):
        params_meta = rc.request.params.meta
        print(f"[DEBUG META] rc.request.params.meta: {params_meta}")
        if params_meta is not None:
            print(f"[DEBUG META] params_meta type: {type(params_meta)}")
            print(f"[DEBUG META] params_meta.__dict__: {params_meta.__dict__}")
            # 检查 __pydantic_extra__ 是否有数据
            extra = getattr(params_meta, '__pydantic_extra__', {})
            print(f"[DEBUG META] params_meta.__pydantic_extra__: {extra}")
            if extra:
                # 有 extra 字段，使用 model_dump 获取完整数据
                if hasattr(params_meta, 'model_dump'):
                    result = params_meta.model_dump()
                    print(f"[DEBUG META] Method 1 SUCCESS: {result}")
                    return result
    print(f"[DEBUG META] Method 1 FAILED")
    
    # 方法 2: 从 rc.meta 的 __pydantic_extra__ 获取
    print(f"\n[DEBUG META] Trying Method 2: rc.meta.__pydantic_extra__")
    if rc.meta is not None:
        extra = getattr(rc.meta, '__pydantic_extra__', {})
        print(f"[DEBUG META] rc.meta.__pydantic_extra__: {extra}")
        if extra:
            if hasattr(rc.meta, 'model_dump'):
                result = rc.meta.model_dump()
                print(f"[DEBUG META] Method 2 SUCCESS: {result}")
                return result
    print(f"[DEBUG META] Method 2 FAILED")
    
    # 方法 3: 回退 - 从原始 request body 中解析
    # 这是解决某些框架（如 strands）下 meta 丢失问题的终极方案
    print(f"\n[DEBUG META] Trying Method 3: raw request body")
    try:
        if hasattr(rc, 'request') and hasattr(rc.request, '_body'):
            body_bytes = rc.request._body
            print(f"[DEBUG META] raw body bytes: {body_bytes[:200]}..." if body_bytes else "None")
            if body_bytes:
                body_json = json.loads(body_bytes)
                print(f"[DEBUG META] parsed body: {body_json}")
                params = body_json.get('params', {})
                print(f"[DEBUG META] body params: {params}")
                # 检查 _meta (标准 MCP 协议字段)
                if '_meta' in params and params['_meta']:
                    print(f"[DEBUG META] Method 3 SUCCESS via _meta: {params['_meta']}")
                    return params['_meta']
                # 检查 meta (某些客户端可能用这个字段名)
                if 'meta' in params and params['meta']:
                    print(f"[DEBUG META] Method 3 SUCCESS via meta: {params['meta']}")
                    return params['meta']
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        print(f"[WARNING] Failed to parse meta from request body: {e}")
    print(f"[DEBUG META] Method 3 FAILED")
    
    print(f"[DEBUG META] All methods failed, returning empty dict")
    return {}


def get_meta_value(ctx: Context, key: str, default: Any = None) -> Any:
    """
    从 Context 中获取指定的 meta 字段值。
    
    Args:
        ctx: FastMCP Context 对象
        key: 要获取的 meta 字段名
        default: 如果字段不存在时返回的默认值
    
    Returns:
        字段值，如果不存在则返回 default
    """
    meta = get_meta_from_context(ctx)
    return meta.get(key, default)


@mcp.tool()
def meta_test(ctx: Context) -> str:
    """测试工具，用于验证是否能接收到客户端传递的 meta 信息。"""
    
    # 使用辅助函数获取 meta
    meta = get_meta_from_context(ctx)
    
    print(f"\n[SERVER] Received meta: {meta}")
    
    if meta:
        counter = meta.get('counter', 'NOT_FOUND')
        run_id = meta.get('run_id', 'NOT_FOUND')
        progress_token = meta.get('progressToken')
        
        return f"counter={counter}, run_id={run_id}, progressToken={progress_token}"
    else:
        return "No meta received"


@mcp.tool()
def process_with_context(ctx: Context, message: str) -> str:
    """
    示例工具：展示如何在实际业务逻辑中使用 meta 参数。
    
    Args:
        message: 用户输入的消息
    """
    # 获取请求上下文信息
    run_id = get_meta_value(ctx, 'run_id', 'unknown')
    counter = get_meta_value(ctx, 'counter', 0)
    app_name = get_meta_value(ctx, 'app_name', 'default')
    
    # 可以用于日志、追踪、限流等场景
    print(f"[{app_name}] Processing request #{counter} (run_id={run_id}): {message}")
    
    return f"Processed '{message}' in context: app={app_name}, run={run_id}, counter={counter}"


def main():
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
