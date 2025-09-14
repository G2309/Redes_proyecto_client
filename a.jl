using HTTP
using JSON3
using JSON
using DotEnv
using Dates
using UUIDs
using Base.Threads: ReentrantLock, lock, unlock

DotEnv.load!(".env")

ANTHROPIC_KEY = ENV["Anthropic_API_key"]
MCP_CONFIG = get(ENV, "MCP_CONFIG", "./mcp_config.json")
SYS_PROMPT = get(ENV, "SYS_PROMPT", "Eres un asistente.")
MAX_CONTEXT = parse(Int, get(ENV, "MAX_CONTEXT_MESSAGES", "20"))

struct Message
    role::String
    content::String
end

mutable struct MCPServer
    name::String
    cmdstr::String
    io::IO
    lock::ReentrantLock
    next_id::Int
end

mutable struct ClaudeBot
    system_prompt::String
    messages::Vector{Message}
    mcp_tools::Dict{String,Any}
    mcp_servers::Dict{String,MCPServer}
end

function build_cmdstr(entry)
    cmd = entry["command"]
    args = haskey(entry, "args") ? collect(entry["args"]) : String[]
    all = [cmd; args]
    return join(all, " ")
end

function start_mcp_server(name::String, entry)::Union{MCPServer,Nothing}
    try
        cmdstr = build_cmdstr(entry)
        cmd = `sh -c $cmdstr`
        io = open(cmd, "r+")
        m = MCPServer(name, cmdstr, io, ReentrantLock(), 1)
        println("MCP arrancado: $name -> $cmdstr")
        return m
    catch e
        @warn "Error arrancando MCP $name: $e"
        return nothing
    end
end

function start_all_mcp!(bot::ClaudeBot)
    bot.mcp_servers = Dict{String,MCPServer}()
    for (name,entry) in bot.mcp_tools
        m = start_mcp_server(name, entry)
        if m !== nothing
            bot.mcp_servers[name] = m
        end
    end
end

function stop_all_mcp!(bot::ClaudeBot)
    for (name, srv) in bot.mcp_servers
        try
            println("Cerrando MCP $name")
            try
                close(srv.io)
            catch
            end
        catch e
            @warn "Error cerrando MCP $name: $e"
        end
    end
    bot.mcp_servers = Dict{String,MCPServer}()
end

function add_message!(bot::ClaudeBot, role::String, content::String)
    push!(bot.messages, Message(role, content))
    if length(bot.messages) > MAX_CONTEXT
        bot.messages = bot.messages[end-MAX_CONTEXT+1:end]
    end
end

function format_tools_prompt(bot::ClaudeBot)
    lines = ["Herramientas MCP disponibles:"]
    for (name, entry) in bot.mcp_tools
        cmd = haskey(entry, "command") ? String(entry["command"]) : ""
        args = haskey(entry, "args") ? join(collect(entry["args"]), " ") : ""
        descr = haskey(entry, "description") ? String(entry["description"]) : ""
        push!(lines, "- name: $(name)")
        push!(lines, "  command: $(cmd) $(args)")
        push!(lines, "  description: $(descr)")
        push!(lines, "  ejemplo_call_json: {\"tool\":\"$(name)\",\"params\":{\"action\":\"<accion>\",\"...\":...}}")
    end
    return join(lines, "\n")
end

function find_json_line(text::String)
    for line in split(text, '\n')
        s = strip(line)
        if startswith(s, "{") && endswith(s, "}")
            try
                x = JSON3.read(s)
                return s
            catch
            end
        end
    end
    return nothing
end

function agent_turn(bot::ClaudeBot, user_msg::String)
    add_message!(bot, "user", user_msg)

    tools_desc = format_tools_prompt(bot)
    instruction = """
    REGLAS (muy importantes):
    - Si necesitas ejecutar una herramienta MCP, responde ÚNICAMENTE con una línea JSON válida como:
      { "tool": "<nombre>", "params": { ... } }
      Ejemplo: {"tool":"filesystem","params":{"action":"write_file","path":"prueba.txt","content":"hola"}}.
    - Tras ejecutar la herramienta, el programa (yo) te devolverá la respuesta de la herramienta y tú debes continuar tu razonamiento en otro mensaje (puedes volver a pedir otra herramienta).
    - Cuando hayas terminado y tengas la respuesta final para el usuario, responde ÚNICAMENTE con:
      { "final": true, "response": "<texto final para el usuario>" }
    - No añadas texto adicional fuera del JSON en esos mensajes de acción o final. Si no vas a usar una herramienta, devuelve directamente el JSON final con final=true.
    - Aquí están las herramientas disponibles:\n
    $(tools_desc)
    """

    resp_text = claude_request(bot, user_msg; extra_system=instruction)

    while true
        json_line = find_json_line(resp_text)
        if json_line === nothing
            add_message!(bot, "assistant", resp_text)
            return resp_text
        end

        parsed = JSON3.read(json_line)
        if haskey(parsed, "final") && parsed["final"] == true
            final_text = parsed["response"]
            add_message!(bot, "assistant", final_text)
            return final_text
        end

        if haskey(parsed, "tool")
            toolname = String(parsed["tool"])
            params = haskey(parsed, "params") ? parsed["params"] : Dict()
            tool_resp = call_mcp(bot, toolname, params)

            add_message!(bot, "assistant", json_line)
            tool_resp_json = try
                JSON.json(tool_resp)
            catch
                sprint(show, tool_resp)
            end
            add_message!(bot, "system", "TOOL_RESPONSE: " * tool_resp_json)

            continue_prompt = "He ejecutado la herramienta y aquí está la respuesta: TOOL_RESPONSE: " * tool_resp_json * "\nPor favor continúa (si necesitas más herramientas devuélvelas en JSON según las reglas)."
            resp_text = claude_request(bot, continue_prompt; extra_system=instruction)
            continue
        else
            add_message!(bot, "assistant", resp_text)
            return resp_text
        end
    end
end

function normalize_json_value(x)
    if x isa JSON3.Object || x isa AbstractDict
        d = Dict{String,Any}()
        for (k,v) in x
            kstr = String(k)
            d[kstr] = normalize_json_value(v)
        end
        return d
    elseif x isa JSON3.Array || x isa AbstractVector
        return [normalize_json_value(v) for v in x]
    else
        return x
    end
end

function claude_request(bot::ClaudeBot, user_msg::String; extra_system::String = "")
    url = "https://api.anthropic.com/v1/messages"

    headers = [
        "Content-Type" => "application/json",
        "x-api-key" => ANTHROPIC_KEY,
        "anthropic-version" => "2023-06-01",
    ]

    system_combined = bot.system_prompt
    if !isempty(extra_system)
        system_combined *= "\n\n" * extra_system
    end

    payload = Dict(
        "model" => "claude-3-haiku-20240307",
        "system" => system_combined,
        "max_tokens" => 512,
        "messages" => [Dict("role"=>m.role,"content"=>m.content) for m in bot.messages]
    )

    push!(payload["messages"], Dict("role"=>"user","content"=>user_msg))

    resp = HTTP.post(url; headers=headers, body=JSON.json(payload))
    data = JSON3.read(String(resp.body))

    if haskey(data, "content")
        answer = join([c["text"] for c in data["content"] if haskey(c,"text")])
        return answer
    else
        return "[Error en respuesta Anthropic: $(String(resp.body))]"
    end
end

function mcp_send_request_and_wait(srv::MCPServer, payload::Dict; timeout_s=10.0)
    lock(srv.lock)
    try
        id = srv.next_id
        srv.next_id += 1
        payload_with_id = merge(Dict("id" => string(id)), payload)
        payload_with_id_native = normalize_json_value(payload_with_id)
        line = JSON.json(payload_with_id_native) * "\n"
        try
            write(srv.io, line)
            flush(srv.io)
        catch e
            unlock(srv.lock); rethrow(e)
        end

        deadline = time() + timeout_s
        while time() < deadline
            try
                resp_line = readline(srv.io)
            catch e
                unlock(srv.lock)
                return Dict("error" => "EOF or closed IO while waiting response: $e")
            end

            parsed = nothing
            try
                parsed = JSON3.read(resp_line)
            catch
                continue
            end

            if haskey(parsed, "id") && string(parsed["id"]) == string(id)
                resp_native = normalize_json_value(parsed)
                unlock(srv.lock)
                return resp_native
            end
        end

        unlock(srv.lock)
        return Dict("error" => "timeout waiting response", "id" => string(id))
    catch e
        unlock(srv.lock)
        rethrow(e)
    end
end

function call_mcp(bot::ClaudeBot, tool::String, args)
    args_native = normalize_json_value(args)

    if !haskey(bot.mcp_servers, tool)
        return Dict("error" => "No existe herramienta MCP arrancada: $tool", "tool"=>tool, "params"=>args_native)
    end
    srv = bot.mcp_servers[tool]
    payload = Dict(
        "type" => "request",
        "method" => "call_tool",
        "params" => args_native
    )
    resp = mcp_send_request_and_wait(srv, payload; timeout_s=10.0)
    return resp
end

function ClaudeBot(;system_prompt=SYS_PROMPT)
    mcp_tools = Dict{String,Any}()
    if isfile(MCP_CONFIG)
        cfg = JSON3.read(read(MCP_CONFIG, String))

        if haskey(cfg, "servers") && cfg["servers"] isa JSON3.Object
            mcp_tools = Dict(cfg["servers"])
        elseif haskey(cfg, "servers") && cfg["servers"] isa JSON3.Array
            mcp_tools = Dict(s["name"] => s for s in cfg["servers"])
        elseif haskey(cfg, "mcp_servers") && cfg["mcp_servers"] isa JSON3.Array
            mcp_tools = Dict(s["name"] => s for s in cfg["mcp_servers"])
        else
            @warn "Formato inesperado en $MCP_CONFIG"
        end
    end

    bot = ClaudeBot(system_prompt, Message[], mcp_tools, Dict{String,MCPServer}())
    start_all_mcp!(bot)
    return bot
end

function run_bot()
    bot = ClaudeBot()
    println("Claude MCP Bot listo. Escribe '/quit' para salir.")
    try
        while true
            print("Tú: ")
            user_msg = readline()
            if user_msg == "/quit"
                break
            elseif startswith(user_msg, "/tool ")
                parts = split(user_msg, " "; limit=3)
                tool = parts[2]
                args = length(parts) > 2 ? JSON3.read(parts[3]) : Dict()
                resp = call_mcp(bot, tool, args)
                println("MCP Resp: ", resp)
            else
                result = agent_turn(bot, user_msg)
                println("Claude: ", result)
            end
        end
    finally
        stop_all_mcp!(bot)
    end
end

if abspath(PROGRAM_FILE) == @__FILE__
    run_bot()
end
