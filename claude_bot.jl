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
    if !haskey(msg.meta, "tool_call")
        return nothing
    end

    tc = msg.meta["tool_call"]
    server_raw = get(tc, "server", nothing)
    tool_raw   = get(tc, "tool", nothing)
    args_raw   = get(tc, "args", Dict())

    server, tool = normalize_server_tool(server_raw, tool_raw)

    args = Dict{String,Any}()
    if isa(args_raw, Dict)
        for (k,v) in args_raw
            args[string(k)] = v
        end
    end

    if isempty(strip(server)) || isempty(strip(tool))
        return (success=false, error="tool_call mal formado tras normalización: falta server o tool")
    end

    try
        return MCPManager.call_tool(bot.mcp_mgr, server, tool, args)
    catch e
        return (success=false, error=string(e))
    end
end

function extract_first_json_object(s::String)
    start_idx = findfirst('{', s)
    if start_idx === nothing
        return nothing
    end
    for end_idx in start_idx+1:length(s)
        if s[end_idx] == '}'
            candidate = s[start_idx:end_idx]
            try
                parsed = JSON.parse(candidate)
                return parsed
            catch
            end
        end
    end
    return nothing
end

function normalize_server_tool(server_raw, tool_raw)
    server = server_raw === nothing ? "" : String(server_raw)
    tool   = tool_raw   === nothing ? "" : String(tool_raw)

    if isempty(server) || lowercase(server) == "mcp"
        if occursin("__", tool)
            parts = split(tool, "__")
            if length(parts) >= 2
                server = parts[1]
                tool = parts[2]
            end
        end
    end

    if occursin("__", server) && !occursin("__", tool)
        parts = split(server, "__")
        if length(parts) >= 2
            server, tool = parts[1], parts[2]
        end
    end

    return (server, tool)
end


function send_stream(bot::Claude, user_input::String)
    push!(bot.history, Message("user", user_input, now(), Dict()))

    if isempty(strip(bot.api_key))
        @error(bot.logger, "Anthropic API key is empty. Set Anthropic_API_key in your .env or export it in the environment.")
        return (success=false, error="Missing Anthropic API key")
    end

    tool_list = []
    for (s, tdict) in bot.mcp_mgr.tools
        for (t, _) in tdict
            push!(tool_list, "$(s)__$(t)")
        end
    end
    tool_list_str = isempty(tool_list) ? "Ninguna" : join(tool_list, ", ")

    sys_with_tools = bot.sys_prompt * "\n\nHerramientas disponibles: " * tool_list_str * "\n" *
        "Si deseas invocar una herramienta, responde SOLO con un JSON EXACTO con este formato:\n" *
        "{\"tool_call\": {\"server\": \"<server>\", \"tool\": \"<tool>\", \"args\": { ... } }}\n" *
        "No incluyas texto adicional cuando estés invocando la herramienta. Si no vas a invocar herramienta, responde en lenguaje natural."

    payload = Dict(
        "model" => "claude-3-5-haiku-20241022",
        "max_tokens" => 1000,
        "system" => sys_with_tools,
        "messages" => prepare_msgs(bot)
    )

    headers = Dict(
        "content-type" => "application/json",
        "x-api-key" => bot.api_key,
        "anthropic-version" => "2023-06-01"
    )

    try
        r = HTTP.post("https://api.anthropic.com/v1/messages"; headers=headers, body=JSON.json(payload))

        if r.status == 200
            body = String(r.body)
            parsed = JSON.parse(body)
            
            txt = ""
            if haskey(parsed, "content") && length(parsed["content"]) > 0
                for content_block in parsed["content"]
                    if content_block["type"] == "text"
                        txt *= content_block["text"]
                    end
                end
            end

            if isempty(strip(txt))
                txt = get(parsed, "text", "")  
            end

            push!(bot.history, Message("assistant", txt, now(), Dict()))

            parsed_json = extract_first_json_object(txt)
            if parsed_json !== nothing && haskey(parsed_json, "tool_call")
                tc = parsed_json["tool_call"]
                server = get(tc, "server", nothing)
                tool = get(tc, "tool", nothing)
                args = get(tc, "args", Dict{String,Any}())

                if server === nothing || tool === nothing
                    @warn(bot.logger, "tool_call JSON mal formado: $(parsed_json)")
                    return (success=true, text=txt)  # devolvemos la respuesta textual
                end

                tool_msg = Message("assistant", txt, now(), Dict("tool_call" => Dict("server"=>server, "tool"=>tool, "args"=>args)))
                tool_res = handle_tool_calls(bot, tool_msg)

                if tool_res === nothing
                    @warn(bot.logger, "handle_tool_calls devolvió nothing")
                    return (success=false, error="Tool handler returned nothing")
                end

                result_text = ""
                if haskey(tool_res, :success) && tool_res[:success] == true
                    # Serializar resultado si existe
                    result_text = "TOOL_RESULT: " * (haskey(tool_res, :result) ? JSON.json(tool_res[:result]) : "sin contenido")
                else
                    # Error en la herramienta
                    result_text = "TOOL_ERROR: " * get(tool_res, :error, "error desconocido")
                end

                push!(bot.history, Message("assistant", result_text, now(), Dict("tool_result"=>tool_res)))

                full_text = "Claude Bot: \n" * txt * "\n\n" * result_text
                return (success=true, text=full_text)
            end

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
