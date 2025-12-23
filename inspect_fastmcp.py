#!/usr/bin/env python3
"""
Inspect FastMCP Implementation

This script inspects the FastMCP class and its streamable_http_app method
to understand its routing configuration.
"""
import inspect
from mcp.server.fastmcp import FastMCP

# 检查 FastMCP 类
def inspect_fastmcp():
    print("=== Inspecting FastMCP class ===")
    print(f"FastMCP module: {FastMCP.__module__}")
    print(f"FastMCP class: {FastMCP}")
    
    # 获取所有方法
    methods = [method for method in dir(FastMCP) if not method.startswith('_') or method in ['__init__', '_']]
    print(f"\nFastMCP methods: {methods}")

    # 检查 streamable_http_app 方法
    if hasattr(FastMCP, 'streamable_http_app'):
        print("\n=== Inspecting streamable_http_app method ===")
        app_method = FastMCP.streamable_http_app
        print(f"Method: {app_method}")
        print(f"Method source: {inspect.getsourcefile(app_method)}")
        
        # 尝试获取源代码
        try:
            source = inspect.getsource(app_method)
            print(f"\nMethod source code:\n{source}")
        except Exception as e:
            print(f"\nCould not get source code: {e}")
            
        # 尝试获取方法签名
        sig = inspect.signature(app_method)
        print(f"\nMethod signature: {sig}")
    
    # 检查 FastMCP 的其他相关方法
    if hasattr(FastMCP, '__init__'):
        print("\n=== Inspecting __init__ method ===")
        init_method = FastMCP.__init__
        try:
            source = inspect.getsource(init_method)
            print(f"\n__init__ source code:\n{source}")
        except Exception as e:
            print(f"\nCould not get __init__ source code: {e}")


# 检查 MCP 服务器的 ASGI 应用配置
def inspect_asgi_app():
    from src.mcp_server import mcp
    
    print("\n=== Inspecting ASGI App ===")
    app = mcp.streamable_http_app()
    print(f"ASGI App: {app}")
    print(f"App type: {type(app)}")
    
    # 尝试查看应用的路由信息
    if hasattr(app, 'routes'):
        print(f"\nApp routes: {app.routes}")
    elif hasattr(app, '__dict__'):
        print(f"\nApp attributes: {list(app.__dict__.keys())}")
    
    # 检查应用的其他属性
    print(f"\nApp dir: {[attr for attr in dir(app) if not attr.startswith('_')]}")


if __name__ == "__main__":
    inspect_fastmcp()
    inspect_asgi_app()
