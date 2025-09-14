import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

from anthropic import AsyncAnthropic
from anthropic.types import Message
from anthropic._exceptions import APIError, RateLimitError, APIConnectionError

import mcp_manager

logger = logging.getLogger(__name__)
MODEL = "claude-3-7-sonnet-latest"
MAX_TOKENS = 1000

@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: datetime
    tool_calls: List[Dict[str, Any]] = None

client: AsyncAnthropic = None
conversation_history: List[ChatMessage] = []
max_context_messages: int = 20
session_file = Path("session.json")

async def initialize(api_key: str, mcp_servers: List[mcp_manager.MCPServerConfig], max_context: int = 20):
    global client, max_context_messages
    client = AsyncAnthropic(api_key=api_key)
    max_context_messages = max_context
    await mcp_manager.start_servers(mcp_servers)
    await load_session()

async def load_session():
    global conversation_history
    if session_file.exists():
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
                
            conversation_history = []
            for msg_data in data.get('messages', []):
                msg = ChatMessage(
                    role=msg_data['role'],
                    content=msg_data['content'],
                    timestamp=datetime.fromisoformat(msg_data['timestamp']),
                    tool_calls=msg_data.get('tool_calls')
                )
                conversation_history.append(msg)
                
            logger.info(f"Loaded {len(conversation_history)} messages from session")
        except Exception as e:
            logger.error(f"Failed to load session: {e}")

async def save_session():
    try:
        data = {'messages': []}
        
        for msg in conversation_history:
            msg_dict = asdict(msg)
            msg_dict['timestamp'] = msg.timestamp.isoformat()
            data['messages'].append(msg_dict)
        
        with open(session_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save session: {e}")

def prepare_messages_for_api() -> List[Dict[str, Any]]:
    recent_messages = conversation_history[-max_context_messages:]
    
    api_messages = []
    for msg in recent_messages:
        if msg.role in ["user", "assistant"]:
            api_messages.append({
                "role": msg.role,
                "content": msg.content
            })
    
    return api_messages

async def handle_tool_calls(message: Message) -> List[Dict[str, Any]]:
    tool_results = []
    
    for content_block in message.content:
        if content_block.type == "tool_use":
            tool_name = content_block.name
            arguments = content_block.input
            tool_use_id = content_block.id
            
            logger.info(f"Executing tool: {tool_name} with args: {arguments}")
            
            if "__" in tool_name:
                server_name, actual_tool_name = tool_name.split("__", 1)
            else:
                logger.error(f"Invalid tool name format: {tool_name}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "Error: Invalid tool name format. Expected format: server__tool_name"
                })
                continue
            
            try:
                result = await mcp_manager.call_tool(server_name, actual_tool_name, arguments)
                logger.info(f"Tool {tool_name} completed successfully")
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": str(result)
                })
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": f"Error executing {actual_tool_name}: {str(e)}"
                })
    
    return tool_results

async def send_message_stream(user_input: str):
    user_msg = ChatMessage(
        role="user",
        content=user_input,
        timestamp=datetime.now()
    )
    conversation_history.append(user_msg)
    
    try:
        messages = prepare_messages_for_api()
        tools = mcp_manager.get_all_tools_for_anthropic()
        
        assistant_content = ""
        all_tool_calls = []
        current_messages = messages
        
        while True:
            kwargs = {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "messages": current_messages
            }
            
            if tools:
                kwargs["tools"] = tools
            
            current_tool_calls = []
            
            async with client.messages.stream(**kwargs) as stream:
                async for chunk in stream:
                    if chunk.type == "content_block_delta":
                        if chunk.delta.type == "text_delta":
                            text_chunk = chunk.delta.text
                            assistant_content += text_chunk
                            yield text_chunk
                    elif chunk.type == "content_block_start":
                        if chunk.content_block.type == "tool_use":
                            current_tool_calls.append({
                                "id": chunk.content_block.id,
                                "name": chunk.content_block.name,
                                "input": chunk.content_block.input
                            })
                
                final_message = await stream.get_final_message()
            
            if final_message.stop_reason != "tool_use":
                break
            
            if current_tool_calls:
                all_tool_calls.extend(current_tool_calls)
                yield "\n\n🔧 Executing tools...\n"
                
                tool_results = await handle_tool_calls(final_message)
                
                if tool_results:
                    current_messages.append({
                        "role": "assistant", 
                        "content": final_message.content
                    })
                    
                    current_messages.append({
                        "role": "user", 
                        "content": tool_results
                    })
                    
                    continue
                else:
                    break
            else:
                break
        
        assistant_msg = ChatMessage(
            role="assistant",
            content=assistant_content,
            timestamp=datetime.now(),
            tool_calls=all_tool_calls if all_tool_calls else None
        )
        conversation_history.append(assistant_msg)
        
        await save_session()
        
    except RateLimitError as e:
        yield f"\n⚠️ Rate limit exceeded. Please wait a moment and try again."
    except APIConnectionError as e:
        yield f"\n❌ Connection error: {e}"
    except APIError as e:
        yield f"\n❌ API error: {e}"
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        yield f"\n❌ Unexpected error: {e}"

def clear_history():
    global conversation_history
    conversation_history.clear()

def get_conversation_stats():
    total_messages = len(conversation_history)
    user_messages = len([m for m in conversation_history if m.role == "user"])
    assistant_messages = len([m for m in conversation_history if m.role == "assistant"])
    
    return {
        "total": total_messages,
        "user": user_messages,
        "assistant": assistant_messages,
        "context_window": max_context_messages
    }

async def cleanup():
    await mcp_manager.cleanup()
    await save_session()
    if client:
        await client.close()
