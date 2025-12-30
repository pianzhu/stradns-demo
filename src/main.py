from datetime import timedelta
from typing import Any

from mcp.client.streamable_http import streamable_http_client
from strands import Agent
from strands.models import anthropic
from strands.tools.mcp import MCPClient
from strands.tools.mcp.mcp_types import MCPToolResult


class CustomMCPClient(MCPClient):
    """自定义 MCP Client，支持传递 meta 参数到 MCP 服务器端。"""
    
    def __init__(self, *args, meta: dict[str, Any] | None = None, **kwargs):
        """
        初始化 CustomMCPClient.
        
        Args:
            meta: 可选的元数据字典，将在每次工具调用时传递到服务器端。
                  服务器端可以通过 ctx.request_context.meta 访问这些数据。
            *args, **kwargs: 传递给父类 MCPClient 的其他参数。
        """
        super().__init__(*args, **kwargs)
        self._meta = meta
    
    def set_meta(self, meta: dict[str, Any] | None):
        """动态设置 meta 信息，用于每次调用前更新。"""
        self._meta = meta
    
    async def call_tool_async(
        self,
        tool_use_id: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
    ) -> MCPToolResult:
        """异步调用 MCP 服务器上的工具，支持传递 meta 参数。"""
        import asyncio
        import logging
        from typing import cast
        from mcp.client.session import ClientSession
        from mcp.types import CallToolResult as MCPCallToolResult
        from strands.tools.mcp.mcp_client import (
            MCPClientInitializationError,
            CLIENT_SESSION_NOT_RUNNING_ERROR_MESSAGE,
        )
        
        logger = logging.getLogger(__name__)
        
        self._log_debug_with_thread(
            "calling MCP tool '%s' asynchronously with tool_use_id=%s, meta=%s", 
            name, tool_use_id, self._meta
        )
        
        if not self._is_session_active():
            raise MCPClientInitializationError(CLIENT_SESSION_NOT_RUNNING_ERROR_MESSAGE)
        
        async def _call_tool_async() -> MCPCallToolResult:
            # 关键改动：传递 meta 参数到 ClientSession.call_tool
            print(f"[CLIENT DEBUG] call_tool_async called!")
            print(f"[CLIENT DEBUG] self._meta = {self._meta}")
            print(f"[CLIENT DEBUG] name={name}, arguments={arguments}")
            
            # 获取 session 并验证
            session = cast(ClientSession, self._background_thread_session)
            print(f"[CLIENT DEBUG] session type: {type(session)}")
            print(f"[CLIENT DEBUG] Calling session.call_tool with meta={self._meta}")
            
            result = await session.call_tool(
                name, arguments, read_timeout_seconds, meta=self._meta
            )
            print(f"[CLIENT DEBUG] call_tool returned: {result}")
            return result
        
        try:
            future = self._invoke_on_background_thread(_call_tool_async())
            call_tool_result: MCPCallToolResult = await asyncio.wrap_future(future)
            return self._handle_tool_result(tool_use_id, call_tool_result)
        except Exception as e:
            logger.exception("tool execution failed")
            return self._handle_tool_execution_error(tool_use_id, e)


async def main():
    # 配置模型
    anthropic_model = anthropic.AnthropicModel(
        client_args={
            "api_key": "",
            "base_url": "https://api.minimaxi.com/anthropic"
        },
        model_id="MiniMax-M2",
        max_tokens=4096  # 添加 max_tokens 参数
    )
    
    # 使用 Streamable HTTP 连接到 MCP 服务器
    # 服务器需要先运行: python src/mcp_server.py
    mcp_server_url = "http://localhost:8002/mcp"
    
    # 创建带有 meta 支持的 CustomMCPClient
    mcp_client = CustomMCPClient(
        lambda: streamable_http_client(mcp_server_url),
        meta={"app_name": "strands-demo", "initial": True}
    )
    
    # 使用 context manager 管理 MCP 连接
    with mcp_client:
        # 获取 MCP 工具列表
        mcp_tools = mcp_client.list_tools_sync()
        
        # 创建 Agent，使用 MCP 客户端提供的工具
        custom_agent = Agent(
            model=anthropic_model,
            tools=mcp_tools,  # 展开工具列表
        )
        
        # 运行多次测试，每次更新 meta 信息
        for i in range(3):
            print(f"\n{'='*50}")
            print(f"Run {i + 1}: Testing with counter={i}")
            print('='*50)
            
            # 动态更新 meta
            mcp_client.set_meta({"counter": i, "run_id": f"run-{i}"})
            
            # 使用 strands event loop 执行
            result = custom_agent("请调用 meta_test 工具来验证 meta 参数是否传递成功")
            
            # 打印结果
            print(f"Agent Response: {result}")
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
