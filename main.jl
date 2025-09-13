include("mcp_manager.jl")
include("claude_bot.jl")

using .MCPManager
using .ClaudeBot
using JSON
using Dates
using DotEnv

DotEnv.load!()

function find_env_key(names::Vector{String})
    for n in names
        if haskey(ENV, n) && !isempty(strip(ENV[n]))
            return ENV[n]
        end
    end
    return "" 
end

function load_config()
    api_key = find_env_key(["Anthropic_API_key", "ANTHROPIC_API_KEY", "anthropic_api_key"])
    mcp_cfg_path = get(ENV, "MCP_CONFIG", "mcp_config.json")
    sys_prompt = get(ENV, "SYS_PROMPT", "Eres un asistente que puede usar herramientas MCP cuando convenga.")
    max_ctx = parse(Int, get(ENV, "MAX_CONTEXT_MESSAGES", "20"))
    return Dict("api_key"=>api_key, "mcp_cfg"=>mcp_cfg_path, "sys_prompt"=>sys_prompt, "max_ctx"=>max_ctx)
end

function main()
    cfg = load_config()
    if isempty(strip(cfg["api_key"]))
        println("DEBUG: Anthropic API key NOT FOUND in ENV (checked common names).")

    end

    mcp_configs = MCPManager.load_mcp_config(cfg["mcp_cfg"])
    mgr = MCPManager.MCPMgr(mcp_configs)

    # crea el bot con la api_key 
    bot = ClaudeBot.Claude(cfg["api_key"], mgr; max_ctx=cfg["max_ctx"], sys_prompt=cfg["sys_prompt"])
    ClaudeBot.init_bot!(bot)

    println("MCP client ready. Escribe '/quit' para salir.")

    while true
        print("Tú: ")
        line = readline()
        cmd = strip(line)

        if cmd == "/quit"
            break
        elseif cmd == "/servers"
            println("Servidores MCP disponibles:")
            for (srv, tools) in MCPManager.get_tools(mgr)
                println("- ", srv, ": ", join(keys(tools), ", "))
            end
            continue
        elseif startswith(cmd, "/use ")
            parts = split(cmd)
            if length(parts) < 3
                println("Uso: /use <server> <tool> [args-json]")
                continue
            end
            srv, tool = parts[2], parts[3]
            args = length(parts) > 3 ? JSON.parse(join(parts[4:end], " ")) : Dict()
            res = MCPManager.call_tool(mgr, srv, tool, args)
            println("Resultado: ", res)
            continue
        elseif cmd == "/checkkey"
            println("checkkey -> found=", !isempty(strip(bot.api_key)), ", length=", length(bot.api_key))
            continue
        end

        res = ClaudeBot.send_stream(bot, line)
        if res[:success]
            println("Bot: \n", res[:text])
        else
            println("Error: ", get(res, :error, "unknown"))
        end
    end

    ClaudeBot.cleanup!(bot)
    println("Adiós")
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end

