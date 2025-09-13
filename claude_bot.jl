module ClaudeBot

using JSON
using Dates
using Logging
using HTTP
const MCPManager = Main.MCPManager

export Claude, load_session!, save_session!, init_bot!, send_stream, cleanup!

mutable struct Message
    role::String
    content::String
    ts::DateTime
    meta::Dict{String,Any}
end

mutable struct Claude
    api_key::String
    mcp_mgr::MCPManager.MCPMgr
    max_ctx::Int
    history::Vector{Message}
    session_file::String
    sys_prompt::String
    logger::AbstractLogger
end

function Claude(api_key::String, mcp_mgr::MCPManager.MCPMgr; max_ctx::Int=20, session_file::String="session.json", sys_prompt::String="Eres un asistente que puede usar herramientas MCP cuando convenga.", logger=ConsoleLogger())
    return Claude(api_key, mcp_mgr, max_ctx, Message[], session_file, sys_prompt, logger)
end

function init_bot!(bot::Claude)
    @info(bot.logger, "Initializing MCP servers...")
    MCPManager.start!(bot.mcp_mgr)
    load_session!(bot)
end

function load_session!(bot::Claude)
    try
        if isfile(bot.session_file)
            txt = read(bot.session_file, String)
            arr = JSON.parse(txt)
            bot.history = Message[]
            for m in arr
                push!(bot.history, Message(m["role"], m["content"], DateTime(m["ts"]), get(m, "meta", Dict())))
            end
            @info(bot.logger, "Loaded $(length(bot.history)) messages from session")
        else
            @info(bot.logger, "No prior session file found at $(bot.session_file)")
        end
    catch e
        @warn(bot.logger, "Failed to load session: $e")
    end
end

function save_session!(bot::Claude)
    try
        arr = []
        for m in bot.history
            push!(arr, Dict("role"=>m.role, "content"=>m.content, "ts"=>string(m.ts), "meta"=>m.meta))
        end
        open(bot.session_file, "w") do io
            write(io, JSON.json(arr))
        end
        @info(bot.logger, "Saved session to $(bot.session_file)")
    catch e
        @warn(bot.logger, "Failed to save session: $e")
    end
end

function prepare_msgs(bot::Claude)
    msgs = []
    # Only include user/assistant messages, system prompt goes separately
    start_idx = max(1, length(bot.history) - bot.max_ctx + 1)
    for i in start_idx:length(bot.history)
        m = bot.history[i]
        if m.role in ["user", "assistant"]  # Only include user and assistant messages
            push!(msgs, Dict("role"=>m.role, "content"=>m.content))
        end
    end
    return msgs
end

function handle_tool_calls(bot::Claude, msg::Message)
    if haskey(msg.meta, "tool_call")
        tc = msg.meta["tool_call"]
        server = tc["server"]
        tool = tc["tool"]
        args = get(tc, "args", Dict())
        res = MCPManager.call_tool(bot.mcp_mgr, server, tool, args)
        return res
    end
    return nothing
end

function send_stream(bot::Claude, user_input::String)
    push!(bot.history, Message("user", user_input, now(), Dict()))

    if isempty(strip(bot.api_key))
        @error(bot.logger, "Anthropic API key is empty. Set Anthropic_API_key in your .env or export it in the environment.")
        return (success=false, error="Missing Anthropic API key")
    end

    # Use modern Messages API format
    payload = Dict(
        "model" => "claude-sonnet-4-20250514",
        "max_tokens" => 1000,                      
        "system" => bot.sys_prompt,                
        "messages" => prepare_msgs(bot)           
    )

    headers = Dict(
        "content-type" => "application/json",
        "x-api-key" => bot.api_key,
        "anthropic-version" => "2023-06-01"       # API version
    )

    try
        r = HTTP.post("https://api.anthropic.com/v1/messages"; headers=headers, body=JSON.json(payload))

        if r.status == 200
            body = String(r.body)
            parsed = JSON.parse(body)
            
            # Extract text from the modern API response format
            txt = ""
            if haskey(parsed, "content") && length(parsed["content"]) > 0
                # Modern API returns content as an array of content blocks
                for content_block in parsed["content"]
                    if content_block["type"] == "text"
                        txt *= content_block["text"]
                    end
                end
            end
            
            push!(bot.history, Message("assistant", txt, now(), Dict()))
            return (success=true, text=txt)
        else
            body = try String(r.body) catch _ "" end
            @warn(bot.logger, "Anthropic returned status $(r.status): $body")
            return (success=false, error=string(r.status) * " " * body)
        end
    catch e
        try
            if typeof(e) <: HTTP.Exceptions.StatusError
                response_body = ""
                try
                    response_body = String(e.response.body)
                catch
                    response_body = "Could not read response body"
                end
                @error(bot.logger, "Anthropic API Error ($(e.status)): $response_body")
                return (success=false, error="API Error $(e.status): $response_body")
            else
                @error(bot.logger, "Failed to call Anthropic: $e")
                return (success=false, error=string(e))
            end
        catch
            @error(bot.logger, "Unexpected error while handling exception: $e")
            return (success=false, error=string(e))
        end
    end
end

function cleanup!(bot::Claude)
    @info(bot.logger, "Cleaning up bot and MCP connections...")
    try
        save_session!(bot)
    catch e
    end
    try
        MCPManager.cleanup!(bot.mcp_mgr)
    catch e
    end
end

end 
