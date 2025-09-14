import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)

@dataclass
class MCPServerConfig:
    name: str
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    transport: str = "stdio"
    description: str = ""

sessions: Dict[str, ClientSession] = {}
available_tools: Dict[str, List] = {}
exit_stack = AsyncExitStack()

async def start_servers(servers_config: List[MCPServerConfig]):
    for server_config in servers_config:
        try:
            if server_config.transport == "stdio":
                await _start_stdio_server(server_config)
            elif server_config.transport == "sse":
                await _start_sse_server(server_config)
            else:
                logger.error(f"Unsupported transport type '{server_config.transport}' for server '{server_config.name}'")
                continue
        except Exception as e:
            logger.error(f"Failed to start MCP server '{server_config.name}': {e}")

async def _start_stdio_server(server_config: MCPServerConfig):
    if not server_config.command:
        raise ValueError(f"Command is required for stdio transport in server '{server_config.name}'")
    
    args = [server_config.command]
    if server_config.args:
        args.extend(server_config.args)
    
    env = os.environ.copy()
    if server_config.env:
        env.update(server_config.env)
    
    server_params = StdioServerParameters(
        command=server_config.command,
        args=server_config.args or [],
        env=env
    )
    
    stdio_transport = await exit_stack.enter_async_context(
        stdio_client(server_params)
    )
    
    session = await exit_stack.enter_async_context(
        ClientSession(*stdio_transport)
    )
    
    await session.initialize()
    sessions[server_config.name] = session
    
    tools_response = await session.list_tools()
    available_tools[server_config.name] = tools_response.tools
    
    logger.info(f"Connected to stdio MCP server '{server_config.name}' with {len(tools_response.tools)} tools")
    for tool in tools_response.tools:
        logger.info(f"  - {tool.name}: {tool.description}")

async def _start_sse_server(server_config: MCPServerConfig):
    if not server_config.url:
        raise ValueError(f"URL is required for sse transport in server '{server_config.name}'")
    
    read_stream, write_stream, _ = await exit_stack.enter_async_context(
        streamablehttp_client(server_config.url)
    )
    
    session = await exit_stack.enter_async_context(
        ClientSession(read_stream, write_stream)
    )
    
    await session.initialize()
    sessions[server_config.name] = session
    
    tools_response = await session.list_tools()
    available_tools[server_config.name] = tools_response.tools
    
    logger.info(f"Connected to SSE MCP server '{server_config.name}' at {server_config.url} with {len(tools_response.tools)} tools")
    for tool in tools_response.tools:
        logger.info(f"  - {tool.name}: {tool.description}")

async def call_tool(server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
    if server_name not in sessions:
        raise ValueError(f"Server '{server_name}' not connected")
    
    session = sessions[server_name]
    
    try:
        result = await session.call_tool(tool_name, arguments)
        
        if result.content and len(result.content) > 0:
            return result.content[0].text
        else:
            return str(result)
    except Exception as e:
        logger.error(f"Tool call failed for {server_name}.{tool_name}: {e}")
        return f"Error: {str(e)}"

def get_all_tools_for_anthropic() -> List[Dict[str, Any]]:
    anthropic_tools = []
    
    for server_name, tools in available_tools.items():
        for tool in tools:
            anthropic_tool = {
                "name": f"{server_name}__{tool.name}",
                "description": f"[{server_name}] {tool.description or tool.name}",
                "input_schema": tool.inputSchema or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            anthropic_tools.append(anthropic_tool)
    
    return anthropic_tools

def get_available_tools():
    return available_tools.copy()

async def cleanup():
    try:
        await exit_stack.aclose()
        logger.info("All MCP servers disconnected")
    except Exception as e:
        logger.error(f"Error during MCP cleanup: {e}")
