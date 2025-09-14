import os
import json
import asyncio
import sys
import logging
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("Please install rich: uv add rich")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import claude_bot
import mcp_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    config = {
        "api_key": os.getenv("Anthropic_API_key"),
        "max_context_messages": int(os.getenv("MAX_CONTEXT_MESSAGES", "20")),
        "mcp_servers": []
    }
    
    config_file = os.getenv("MCP_CONFIG", "mcp_config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                mcp_config = json.load(f)
                
            for server_data in mcp_config.get("servers", []):
                server = mcp_manager.MCPServerConfig(
                    name=server_data["name"],
                    command=server_data.get("command"),
                    args=server_data.get("args"),
                    env=server_data.get("env"),
                    url=server_data.get("url"),
                    transport=server_data.get("transport", "stdio"),
                    description=server_data.get("description", "")
                )
                config["mcp_servers"].append(server)
                
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
    
    return config

async def show_help(console):
    console.print("\nCommands:")
    console.print("  /help     - Show this help")
    console.print("  /clear    - Clear conversation history")
    console.print("  [cyan]/tools    - Show available MCP tools")
    console.print("  [cyan]/quit     - Exit the chatbot")
    console.print("  /stats    - Show conversation statistics\n")

async def show_tools(console):
    tools = mcp_manager.get_available_tools()
    if tools:
        console.print("\n Available MCP Tools:")
        for server_name, server_tools in tools.items():
            console.print(f"\n {server_name}:")
            for tool in server_tools:
                desc = tool.description or 'No description'
                console.print(f"    •{tool.name}: {desc}")
    else:
        console.print("[yellow]No MCP tools available.[/yellow]")
    console.print()

async def show_stats(console, available_tools):
    stats = claude_bot.get_conversation_stats()
    
    console.print(f"\nConversation Statistics:")
    console.print(f"  Total messages: {stats['total']}")
    console.print(f"  User messages: {stats['user']}")
    console.print(f"  Assistant messages: {stats['assistant']}")
    console.print(f"  Context window: {stats['context_window']} messages")
    console.print(f"  MCP servers: {len(available_tools)}\n")

async def main():
    console = Console()
    
    config = load_config()
    
    if not config["api_key"]:
        console.print("Please set ANTHROPIC_API_KEY environment variable")
        sys.exit(1)
    
    console.print(Panel.fit(
        "Claude Terminal with LainBOT\n",
        title="Claude Chatbot",
        border_style="blue"
    ))
    
    await show_help(console)
    
    try:
        with console.status("Initializing chatbot and MCP servers..."):
            await claude_bot.initialize(
                api_key=config["api_key"],
                mcp_servers=config["mcp_servers"],
                max_context=config["max_context_messages"]
            )
        
        available_tools = mcp_manager.get_available_tools()
        if available_tools:
            total_tools = sum(len(tools) for tools in available_tools.values())
            console.print(f"\nConnected to {len(available_tools)} MCP server(s) with  {total_tools} total tools:")
            for server_name, tools in available_tools.items():
                console.print(f"  • {server_name}: {len(tools)} tools")
        else:
            console.print("\nNo MCP servers configured or available")
        
        console.print("\n[green]Ready! Type your message and press Enter. Use /quit to exit.[/green]\n")
        
        while True:
            try:
                user_input = console.input("[bold green]You:[/bold green] ").strip()
                
                if not user_input:
                    continue
                
                if user_input.startswith('/'):
                    command = user_input.lower()
                    
                    if command == '/quit':
                        break
                    elif command == '/help':
                        await show_help(console)
                        continue
                    elif command == '/clear':
                        claude_bot.clear_history()
                        await claude_bot.save_session()
                        console.print("Conversation history cleared.\n")
                        continue
                    elif command == '/tools':
                        await show_tools(console)
                        continue
                    elif command == '/stats':
                        await show_stats(console, available_tools)
                        continue
                    else:
                        console.print(f"Unknown command: {user_input}")
                        continue
                
                console.print("Claude: ", end="")
                
                async for chunk in claude_bot.send_message_stream(user_input):
                    console.print(chunk, end="", highlight=False)
                
                console.print()
                console.print()
                
            except KeyboardInterrupt:
                console.print("\n\n Goodbye!")
                break
            except Exception as e:
                logger.error(f"Error in chat loop: {e}")
                console.print(f"Error: {e}\n")
    
    finally:
        with console.status("Cleaning up..."):
            await claude_bot.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
