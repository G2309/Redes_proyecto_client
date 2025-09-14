module MCPManager

using JSON
using HTTP
using Logging
using Base.Threads: @spawn
using Random

export MCPServerConfig, MCPMgr, load_mcp_config, start!, start_stdio!, start_sse!, call_tool, tools_anthropic, get_tools, cleanup!

struct MCPServerConfig
    name::String
    transport::String    
    cmd::Union{Nothing,Vector{String}}   
    url::Union{Nothing,String}
    enabled::Bool
end

mutable struct MCPMgr
    servers::Dict{String,MCPServerConfig}
    tools::Dict{String,Any}           
    conns::Dict{String,Any}           
    logger::AbstractLogger
    msg_id::Int
end

function MCPMgr(configs::Vector{MCPServerConfig}; logger=ConsoleLogger())
    sdict = Dict(cfg.name => cfg for cfg in configs)
    return MCPMgr(sdict, Dict{String,Any}(), Dict{String,Any}(), logger, 0)
end

# Generate unique message ID
function next_id(mgr::MCPMgr)
    mgr.msg_id += 1
    return string(mgr.msg_id)
end

# Send JSON-RPC message and wait for response
function send_jsonrpc(io, id, method, params=nothing)
    msg = Dict{String,Any}(
        "jsonrpc" => "2.0",
        "id"      => id,
        "method"  => method
    )
    if params !== nothing
        msg["params"] = params
    end

    raw = JSON.json(msg)

    try
        write(io, raw * "\n")
        flush(io)
    catch e
        println("Error escribiendo en IO: ", e)
        rethrow(e)
    end
end


# Read response with ID matching
function read_response(io, expected_id; timeout_sec=10)
    deadline = time() + timeout_sec
    buffer = ""
    while time() < deadline
        if eof(io)
            sleep(0.05)
            continue
        end

        line = try
            readline(io)
        catch e
            try
                available = readavailable(io)
                    isempty(available) ? "" : String(available)
            catch
                ""
            end
        end

        if !isempty(line)
            sline = strip(line)
            if isempty(sline)
                continue
            end

            try
                resp = JSON.parse(sline)
                if haskey(resp, "id") && resp["id"] == expected_id
                    return resp
                else
                    continue
                end
            catch e
                buffer *= line * "\n"
            end
        end

        if !isempty(buffer)
            try
                resp = JSON.parse(buffer)
                if haskey(resp, "id") && resp["id"] == expected_id
                    return resp
                end
            catch
            end
        end

        try
            nothing
        catch
            nothing
        end

        sleep(0.01)
    end

    return nothing
end

# Start all servers
function start!(mgr::MCPMgr)
    for (name, cfg) in mgr.servers
        if !cfg.enabled
            println("Skipping disabled MCP server: ", name)
            continue
        end
        try
            if lowercase(cfg.transport) == "stdio"
                start_stdio!(mgr, cfg)
            elseif lowercase(cfg.transport) == "sse"
                start_sse!(mgr, cfg)
            else
                println("Warning: Unknown transport ", cfg.transport, " for server ", name)
            end
        catch e
            println("Error: Failed starting server ", name, ": ", e)
        end
    end
end

# Start a stdio-backed server with proper MCP initialization
function start_stdio!(mgr::MCPMgr, cfg::MCPServerConfig)
    if cfg.cmd === nothing
        throw(ArgumentError("stdio transport requires a `cmd` in config for server $(cfg.name)"))
    end

    # Construir cmd completo y comprobar existencia del ejecutable
    cmdstr = join(cfg.cmd, " ")
    println("Starting stdio server ", cfg.name, " -> ", cmdstr)

    exe = Sys.which(cfg.cmd[1])
    if exe === nothing
        println("Error: Command not found in PATH: ", cfg.cmd[1], " (server ", cfg.name, ")")
        throw(ErrorException("Command not found: $(cfg.cmd[1])"))
    end

    # Envuelve el comando para forzar line-buffered stdout/stderr y redirigir stderr a stdout
    # stdbuf suele estar disponible en coreutils; si no, puedes quitar este wrapper o instalar stdbuf.
    wrapped_cmd = "stdbuf -oL -eL " * cmdstr * " 2>&1"
    println("Starting stdio server ", cfg.name, " (wrapped): ", wrapped_cmd)

    proc_io = open(`sh -c $wrapped_cmd`, "r+")

    mgr.conns[cfg.name] = (type = :stdio, io = proc_io, task = nothing)

    try
        # Dar un poco más de tiempo en arranque
        sleep(1.0)

        init_id = next_id(mgr)
        init_params = Dict{String, Any}(
            "protocolVersion" => "0.1.0",
            "capabilities" => Dict{String, Any}(
                "tools" => Dict{String, Any}()
            ),
            "clientInfo" => Dict{String, Any}(
                "name" => "julia-mcp-client",
                "version" => "0.1.0"
            )
        )

        send_jsonrpc(proc_io, init_id, "initialize", init_params)

        # aumentar timeout durante el desarrollo (30s)
        init_resp = read_response(proc_io, init_id; timeout_sec=30)
        if init_resp === nothing
            println("Error: No initialize response from ", cfg.name)
            try close(proc_io) catch end
            delete!(mgr.conns, cfg.name)
            return
        end

        println("Initialized ", cfg.name, ": ", JSON.json(get(init_resp, "result", Dict())))

        initialized_msg = Dict{String,Any}(
            "jsonrpc" => "2.0",
            "method"  => "notifications/initialized"
        )
        write(proc_io, JSON.json(initialized_msg) * "\n")
        flush(proc_io)

        sleep(0.2)

        # Request tools list
        tools_id = next_id(mgr)
        send_jsonrpc(proc_io, tools_id, "tools/list")

        tools_resp = read_response(proc_io, tools_id; timeout_sec=10)
        if tools_resp !== nothing && haskey(tools_resp, "result") && haskey(tools_resp["result"], "tools")
            tools_list = tools_resp["result"]["tools"]
            tool_dict = Dict{String,Any}()
            for tool in tools_list
                tool_dict[tool["name"]] = tool
            end
            mgr.tools[cfg.name] = tool_dict
            println("Registered ", length(tools_list), " tools for ", cfg.name)
            for (tname, _) in tool_dict
                println("  - ", tname)
            end
        else
            println("Warning: No tools received from ", cfg.name)
            mgr.tools[cfg.name] = Dict{String,Any}()
        end

    catch e
        println("Error: Failed starting server ", cfg.name, ": ", e)
        println("Stack trace: ")
        Base.show_backtrace(stdout, catch_backtrace())
        try close(proc_io) catch end
        delete!(mgr.conns, cfg.name)
        return
    end

    # Spawn background reader task (not bloquing el hilo principal)
    t = @spawn begin
        try
            while !eof(proc_io)
                line = readline(proc_io)
                if isempty(strip(line))
                    continue
                end
                try
                    msg = JSON.parse(line)
                    if !haskey(msg, "id")
                        println("Notification from ", cfg.name, ": ", JSON.json(msg))
                    end
                catch e
                    # Ignorar líneas no JSON o mensajes parciales
                end
            end
        catch e
            println("Reader task for ", cfg.name, " ended: ", e)
        end
    end

    mgr.conns[cfg.name] = (type = :stdio, io = proc_io, task = t)
end

# Start SSE server (
function start_sse!(mgr::MCPMgr, cfg::MCPServerConfig)
    if cfg.url === nothing
        throw(ArgumentError("sse transport requires a `url` in config for server $(cfg.name)"))
    end
    println("Info: SSE transport not fully implemented yet for ", cfg.name)
    mgr.tools[cfg.name] = Dict{String,Any}()
end

# Call a tool using JSON-RPC protocol
function call_tool(mgr::MCPMgr, server_name::String, tool_name::String, args::Dict{String,Any}; timeout_sec=10)
    if !haskey(mgr.conns, server_name)
        return (success=false, error = "No connection to server $server_name")
    end
    
    conn = mgr.conns[server_name]
    
    if conn[:type] == :stdio
        io = conn[:io]
        try
            call_id = next_id(mgr)
            send_jsonrpc(io, call_id, "tools/call", Dict(
                "name" => tool_name,
                "arguments" => args
            ))
            
            resp = read_response(io, call_id; timeout_sec=timeout_sec)
            if resp === nothing
                return (success=false, error = "Timeout waiting for response")
            end
            
            if haskey(resp, "error")
                return (success=false, error = resp["error"])
            end
            
            if haskey(resp, "result")
                return (success=true, result=resp["result"])
            end
            
            return (success=false, error = "Invalid response format")
        catch e
            return (success=false, error = string(e))
        end
    else
        return (success=false, error = "Unsupported connection type $(conn[:type])")
    end
end

# Convert available tools into a format Anthropic expects
function tools_anthropic(mgr::MCPMgr)
    out = []
    for (sname, tdict) in mgr.tools
        for (tname, meta) in tdict
            # Use the full tool name with server prefix
            tool_def = Dict(
                "name" => "$(sname)__$(tname)",  # Use __ as separator for clarity
                "description" => get(meta, "description", "Tool from $sname"),
                "input_schema" => get(meta, "inputSchema", Dict("type" => "object", "properties" => Dict()))
            )
            push!(out, tool_def)
        end
    end
    return out
end

function get_tools(mgr::MCPMgr)
    return deepcopy(mgr.tools)
end

function cleanup!(mgr::MCPMgr)
    for (name, conn) in mgr.conns
        try
            if conn[:type] == :stdio
                io = conn[:io]
                try
                    # Send shutdown notification
					shutdown_msg = Dict{String,Any}(
    					"jsonrpc" => "2.0",
    					"method"  => "shutdown"
					)

                    write(io, JSON.json(shutdown_msg) * "\n")
                    flush(io)
                    sleep(0.1)  # Give time for graceful shutdown
                catch
                end
                try close(io) catch end
            end
        catch e
            println("Warning: Error closing connection ", name, ": ", e)
        end
    end
    empty!(mgr.conns)
    empty!(mgr.tools)
end

function load_mcp_config(path::String)
    txt = read(path, String)
    j = JSON.parse(txt)
    configs = MCPServerConfig[]
    for item in j["mcp_servers"]
        cmdvec = nothing
        if haskey(item, "cmd") && item["cmd"] !== nothing
            if isa(item["cmd"], String)
                cmdvec = [item["cmd"]]
            elseif isa(item["cmd"], Array)
                cmdvec = [string(x) for x in item["cmd"]]
            end
        elseif haskey(item, "command") && item["command"] !== nothing
            cmdvec = [string(item["command"])]
        end

        if cmdvec !== nothing && haskey(item, "args") && isa(item["args"], Array)
            cmdvec = vcat(cmdvec, [string(x) for x in item["args"]])
        end

        push!(configs, MCPServerConfig(
            item["name"],
            item["transport"],
            cmdvec,
            get(item, "url", nothing),
            get(item, "enabled", true)
        ))
    end
    return configs
end

end
