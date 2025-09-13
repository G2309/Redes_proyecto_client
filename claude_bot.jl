module ClaudeBot

using JSON
using Dates
using Logging
using HTTP
using ..MCPManager

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
    push!(msgs, Dict("role"=>"system", "content"=>bot.sys_prompt))
    start_idx = max(1, length(bot.history) - bot.max_ctx + 1)
    for i in start_idx:length(bot.history)
        m = bot.history[i]
        push!(msgs, Dict("role"=>m.role, "content"=>m.content))
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
    payload = Dict(
        "model" => "claude-2.1",
        "messages" => prepare_msgs(bot),
        "max_tokens_to_sample" => 1000
    )
    headers = ["Content-Type" => "application/json", "x-api-key" => bot.api_key]
    try
        r = HTTP.post("https://api.anthropic.com/v1/complete", headers, JSON.json(payload))
        if r.status == 200
            body = String(r.body)
            parsed = JSON.parse(body)
            txt = get(parsed, "completion", get(parsed, "text", ""))
            push!(bot.history, Message("assistant", txt, now(), Dict()))
            return (success=true, text=txt)
        else
            @warn(bot.logger, "Anthropic returned status $(r.status): $(String(r.body))")
            return (success=false, error = string(r.status))
        end
    catch e
        @error(bot.logger, "Failed to call Anthropic: $e")
        return (success=false, error=string(e))
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
