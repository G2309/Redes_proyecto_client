using HTTP
using JSON3
using Sockets
using DotEnv
using Dates
using JSON

# -------------------------
#  Cargar configuración
# -------------------------
DotEnv.load!(".env")

ANTHROPIC_KEY = ENV["Anthropic_API_key"]
MCP_CONFIG = ENV["MCP_CONFIG"]
SYS_PROMPT = get(ENV, "SYS_PROMPT", "Eres un asistente.")
MAX_CONTEXT = parse(Int, get(ENV, "MAX_CONTEXT_MESSAGES", "20"))

# -------------------------
#  Utilidades
# -------------------------

struct Message
    role::String
    content::String
end

mutable struct ClaudeBot
    system_prompt::String
    messages::Vector{Message}
    mcp_tools::Dict{String,Any}
end

function ClaudeBot(;system_prompt=SYS_PROMPT)
    # cargar MCP config
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
    return ClaudeBot(system_prompt, Message[], mcp_tools)
end

function add_message!(bot::ClaudeBot, role::String, content::String)
    push!(bot.messages, Message(role, content))
    if length(bot.messages) > MAX_CONTEXT
        bot.messages = bot.messages[end-MAX_CONTEXT+1:end]
    end
end

# -------------------------
#  Llamada a Anthropic
# -------------------------

function claude_request(bot::ClaudeBot, user_msg::String)
    url = "https://api.anthropic.com/v1/messages"

    headers = [
        "Content-Type" => "application/json",
        "x-api-key" => ANTHROPIC_KEY,
        "anthropic-version" => "2023-06-01",
    ]

    payload = Dict(
        "model" => "claude-3-haiku-20240307",
        "system" => bot.system_prompt,
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
        return "[Error en respuesta Anthropic]"
    end
end

# -------------------------
#  Ejecutar herramientas MCP
# -------------------------

function call_mcp(bot::ClaudeBot, tool::String, args::Dict)
    if !haskey(bot.mcp_tools, tool)
        return "[No existe herramienta MCP: $tool]"
    end
    # Aquí conectas al servidor MCP real (ej: via sockets, subprocess o HTTP)
    # De momento simulo:
    return "[Ejecutando MCP:$tool con args=$(args)]"
end

# -------------------------
#  Loop principal
# -------------------------

function run_bot()
    bot = ClaudeBot()
    println("Claude MCP Bot listo. Escribe '/quit' para salir.")
    while true
        print("Tú: ")
        user_msg = readline()
        if user_msg == "/quit"
            break
        elseif startswith(user_msg, "/tool ")
            parts = split(user_msg, " "; limit=3)
            tool = parts[2]
            args = length(parts) > 2 ? JSON3.read(parts[3]) : Dict()
            println(call_mcp(bot, tool, args))
        else
            add_message!(bot, "user", user_msg)
            ans = claude_request(bot, user_msg)
            add_message!(bot, "assistant", ans)
            println("Claude: $ans")
        end
    end
end

# -------------------------
#  Ejecutar
# -------------------------
if abspath(PROGRAM_FILE) == @__FILE__
    run_bot()
end

