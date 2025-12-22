import uvicorn
from mcp.server.fastmcp import FastMCP, Context

# 创建 MCP 服务器实例
mcp = FastMCP("meta-test-server")


@mcp.tool()
def meta_test(ctx: Context) -> str:
    """测试工具，用于验证是否能接收到客户端传递的 meta 信息。"""
    
    # 获取完整的 request_context
    rc = ctx.request_context
    print(f"[SERVER] Full request_context: {rc}")
    print(f"[SERVER] rc.meta: {rc.meta}")
    print(f"[SERVER] type(rc.meta): {type(rc.meta)}")
    
    if rc.meta:
        # 打印所有属性
        print(f"[SERVER] rc.meta.__dict__: {rc.meta.__dict__}")
        
        # 检查 Pydantic 模型的 extra 字段
        if hasattr(rc.meta, '__pydantic_extra__'):
            print(f"[SERVER] rc.meta.__pydantic_extra__: {rc.meta.__pydantic_extra__}")
        
        # 尝试 model_dump
        if hasattr(rc.meta, 'model_dump'):
            print(f"[SERVER] rc.meta.model_dump(): {rc.meta.model_dump()}")
        
        # 直接访问字段
        counter = getattr(rc.meta, 'counter', 'NOT_FOUND')
        run_id = getattr(rc.meta, 'run_id', 'NOT_FOUND')
        
        return f"counter={counter}, run_id={run_id}, progressToken={rc.meta.progressToken}"
    else:
        return "No meta received"


def main():
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
