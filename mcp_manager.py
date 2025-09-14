import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

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

# Estado global
sessions: Dict[str, ClientSession] = {}
available_tools: Dict[str, List] = {}
_server_tasks: Dict[str, asyncio.Task] = {}

# ----- Helpers: tasks que mantienen la conexión dentro del mismo task -----

async def _stdio_server_task(cfg: MCPServerConfig):
    name = cfg.name
    env = os.environ.copy()
    if cfg.env:
        env.update(cfg.env)

    server_params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args or [],
        env=env
    )

    try:
        # El 'async with' se ejecuta y se cierra dentro de este mismo task
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                sessions[name] = session

                try:
                    tools_resp = await session.list_tools()
                    available_tools[name] = tools_resp.tools
                except Exception:
                    logger.exception("list_tools failed for %s", name)
                    available_tools[name] = []

                logger.info("Connected to stdio MCP server '%s' with %d tools", name, len(available_tools[name]))
                for t in available_tools[name]:
                    logger.info("  - %s: %s", t.name, t.description or "")

                # Mantener el task vivo hasta que sea cancelado
                await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("Stdio server task for '%s' cancelled, cleaning up...", name)
        raise
    except Exception:
        logger.exception("Error in stdio server task for '%s'", name)
    finally:
        sessions.pop(name, None)
        available_tools.pop(name, None)
        logger.info("Stdio server '%s' fully cleaned up", name)


async def _streamable_http_server_task(cfg: MCPServerConfig):
    name = cfg.name
    url = cfg.url
    try:
        # El async with se ejecuta y cierra en este mismo task --> evita problemas con cancel scopes
        async with streamablehttp_client(url) as (read_stream, write_stream, aclose):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                sessions[name] = session

                try:
                    tools_resp = await session.list_tools()
                    available_tools[name] = tools_resp.tools
                except Exception:
                    logger.exception("list_tools failed for %s", name)
                    available_tools[name] = []

                logger.info("Connected to streamable-http MCP server '%s' at %s with %d tools",
                            name, url, len(available_tools[name]))
                for t in available_tools[name]:
                    logger.info("  - %s: %s", t.name, t.description or "")

                # Mantener el task vivo hasta que sea cancelado
                await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("Streamable-HTTP task for '%s' cancelled, cleaning up...", name)
        raise
    except Exception:
        logger.exception("Error in streamable-http server task for '%s'", name)
    finally:
        sessions.pop(name, None)
        available_tools.pop(name, None)
        logger.info("Streamable-HTTP server '%s' fully cleaned up", name)


# ----- Interfaz pública -----

async def start_servers(servers_config: List[MCPServerConfig]):
    """
    Inicia un task por servidor. Cada task mantiene la conexión usando 'async with'
    y por tanto el enter/exit ocurren en el mismo task (evita el error de anyio).
    """
    for cfg in servers_config:
        name = cfg.name
        transport = (cfg.transport or "stdio").lower()
        if name in _server_tasks:
            logger.warning("Server '%s' ya estaba iniciado, saltando", name)
            continue

        if transport == "stdio":
            if not cfg.command:
                logger.error("Command missing for stdio server '%s'", name)
                continue
            task = asyncio.create_task(_stdio_server_task(cfg), name=f"mcp-stdio-{name}")
        elif transport in ("sse", "streamable-http", "streamable-http"):
            if not cfg.url:
                logger.error("URL missing for streamable-http server '%s'", name)
                continue
            task = asyncio.create_task(_streamable_http_server_task(cfg), name=f"mcp-http-{name}")
        else:
            logger.error("Unsupported transport '%s' for server '%s'", transport, name)
            continue

        _server_tasks[name] = task
        logger.info("Spawned connection task for server '%s' (transport=%s)", name, transport)


async def call_tool(server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
    if server_name not in sessions:
        raise ValueError(f"Server '{server_name}' not connected")

    session = sessions[server_name]
    try:
        result = await session.call_tool(tool_name, arguments)
        if getattr(result, "content", None) and len(result.content) > 0:
            return result.content[0].text
        else:
            return str(result)
    except Exception:
        logger.exception("Tool call failed for %s.%s", server_name, tool_name)
        raise


def get_all_tools_for_anthropic() -> List[Dict[str, Any]]:
    anthropic_tools = []
    for server_name, tools in available_tools.items():
        for tool in tools:
            anthropic_tools.append({
                "name": f"{server_name}__{tool.name}",
                "description": f"[{server_name}] {tool.description or tool.name}",
                "input_schema": getattr(tool, "inputSchema", None) or {"type":"object","properties":{},"required":[]}
            })
    return anthropic_tools


def get_available_tools():
    return available_tools.copy()


async def cleanup():
    """
    Cancela todos los tasks y espera su terminación. Cada task cerrará sus contextos en el mismo task.
    """
    tasks = list(_server_tasks.values())
    if not tasks:
        return

    logger.info("Cancelling %d MCP server tasks...", len(tasks))
    for t in tasks:
        t.cancel()

    # esperar a que todos terminen (no propagar excepciones salvo logs)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for name, res in zip(list(_server_tasks.keys()), results):
        if isinstance(res, Exception) and not isinstance(res, asyncio.CancelledError):
            logger.warning("Task %s finished with exception: %s", name, res)
        else:
            logger.debug("Task %s finished cleanly", name)

    _server_tasks.clear()
    sessions.clear()
    available_tools.clear()
    logger.info("Cleanup complete: all MCP server tasks stopped.")

