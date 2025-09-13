module MCPManager

using JSON
using HTTP
using Logging
using Base.Threads: @spawn

export MCPServerConfig, MCPMgr, load_mcp_config, start!, start_stdio!, start_sse!, call_tool, tools_anthropic, get_tools, cleanup!

struct MCPServerConfig
    name::String
    transport::String    # "stdio" or "sse"
    cmd::Union{Nothing,String}
    url::Union{Nothing,String}
    enabled::Bool
end

mutable struct MCPMgr
    servers::Dict{String,MCPServerConfig}
    tools::Dict{String,Any}           # server_name => Dict(toolname=>toolmeta)
    conns::Dict{String,Any}           # server_name => connection handle (IO, Task, HTTP connection, ...)
    logger::AbstractLogger
end

function MCPMgr(configs::Vector{MCPServerConfig}; logger=ConsoleLogger())
    sdict = Dict(cfg.name => cfg for cfg in configs)
    return MCPMgr(sdict, Dict{String,Any}(), Dict{String,Any}(), logger)
end

# start all servers
function start!(mgr::MCPMgr)
    for (name, cfg) in mgr.servers
        if !cfg.enabled
            @info(mgr.logger, "Skipping disabled MCP server: $name")
            continue
        end
        try
            if lowercase(cfg.transport) == "stdio"
                start_stdio!(mgr, cfg)
            elseif lowercase(cfg.transport) == "sse"
                start_sse!(mgr, cfg)
            else
                @warn(mgr.logger, "Unknown transport $(cfg.transport) for server $name")
            end
        catch e
            @error(mgr.logger, "Failed starting server $name: $e")
        end
    end
end

# Start a stdio-backed server by launching its command and communicating JSON-lines.
function start_stdio!(mgr::MCPMgr, cfg::MCPServerConfig)
    if cfg.cmd === nothing
        throw(ArgumentError("stdio transport requires a `cmd` in config for server $(cfg.name)"))
    end

    @info(mgr.logger, "Starting stdio server $(cfg.name) -> $(cfg.cmd)")
    proc_io = open(`$(cfg.cmd)`, "r+")

    t = @spawn begin
        try
            while !eof(proc_io)
                line = readline(proc_io)
                if isempty(strip(line))
                    continue
                end
                try
                    msg = JSON.parse(line)
                    if haskey(msg, "type") && msg["type"] == "tools"
                        mgr.tools[cfg.name] = msg["tools"]
                        @info(mgr.logger, "Registered $(length(msg["tools"])) tools for $(cfg.name)")
                    else
                        @info(mgr.logger, "Message from $(cfg.name): $(msg)")
                    end
                catch e
                    @warn(mgr.logger, "Failed parsing JSON from $(cfg.name): $e | raw: $line")
                end
            end
        catch e
            @error(mgr.logger, "Stdio reader task for $(cfg.name) failed: $e")
        finally
            try close(proc_io) catch end
        end
    end

    mgr.conns[cfg.name] = (type = :stdio, io = proc_io, task = t)
end

# Start SSE server (simple SSE client reading event: data: <json>)
function start_sse!(mgr::MCPMgr, cfg::MCPServerConfig)
    if cfg.url === nothing
        throw(ArgumentError("sse transport requires a `url` in config for server $(cfg.name)"))
    end
    @info(mgr.logger, "Connecting SSE to $(cfg.url) for server $(cfg.name)")

    http_task = @spawn begin
        try
			HTTP.open("GET", cfg.url; headers = ["Accept" => "text/event-stream"]) do conn
    		buf = String[]
    			body = conn.body
    			for chunk in body
        			s = String(chunk)
        			push!(buf, s)
        			joined = join(buf, "")
        			parts = split(joined, "\n\n")
        			for i in 1:(length(parts)-1)
            			event = parts[i]
            			lines = split(event, '\n')
            			datas = String[]
            			for L in lines
                			Ls = strip(L)
                			if startswith(Ls, "data:")
                    			push!(datas, strip(replace(Ls, "data:" => "")))
                			end
            			end
            			if !isempty(datas)
                			text = join(datas, "\n")
                			try
                    			obj = JSON.parse(text)
                    			if haskey(obj, "type") && obj["type"] == "tools"
                        			mgr.tools[cfg.name] = obj["tools"]
                        			@info(mgr.logger, "Registered $(length(obj["tools"])) tools for $(cfg.name) (SSE)")
                    			else
                        			@info(mgr.logger, "SSE $(cfg.name) -> $(obj)")
                    			end
                			catch e
                    			@warn(mgr.logger, "Failed parse SSE JSON from $(cfg.name): $e | raw: $text")
                			end
            			end
        			end
        			buf = [parts[end]]
    			end
			end
        	catch e
            @error(mgr.logger, "SSE connection for $(cfg.name) failed: $e")
        end
    end

    mgr.conns[cfg.name] = (type = :sse, task = http_task, url = cfg.url)
end

# Call a tool by sending a JSON message to the server and waiting for a response.
function call_tool(mgr::MCPMgr, server_name::String, tool_name::String, args::Dict{String,Any}; timeout_sec=10)
    if !haskey(mgr.conns, server_name)
        return (success=false, error = "No connection to server $server_name")
    end
    conn = mgr.conns[server_name]
    payload = Dict("type" => "call", "tool" => tool_name, "args" => args)
    raw = JSON.json(payload)

    if conn[:type] == :stdio
        io = conn[:io]
        try
            write(io, raw * "\n")
            flush(io)
            deadline = time() + timeout_sec
            while time() < deadline
                if eof(io)
                    sleep(0.05)
                    continue
                end
                line = readline(io)
                if isempty(strip(line))
                    continue
                end
                try
                    resp = JSON.parse(line)
                    return (success=true, result=resp)
                catch e
                    return (success=false, error = "Invalid JSON response: $e")
                end
            end
            return (success=false, error = "Timeout waiting for response")
        catch e
            return (success=false, error = string(e))
        end
    elseif conn[:type] == :sse
        cfg = mgr.servers[server_name]
        if cfg.url === nothing
            return (success=false, error = "SSE server has no URL configured for POST calls")
        end
        post_url = cfg.url
        try
            r = HTTP.post(post_url, ["Content-Type" => "application/json"], raw)
            if r.status == 200
                return (success=true, result = JSON.parse(String(r.body)))
            else
                return (success=false, error = "HTTP error $(r.status)")
            end
        catch e
            return (success=false, error = string(e))
        end
    else
        return (success=false, error = "Unsupported connection type $(conn[:type])")
    end
end

# Convert available tools into a format Anthropic expects (basic shape). Add server prefix.
function tools_anthropic(mgr::MCPMgr)
    out = Dict()
    for (sname, tdict) in mgr.tools
        converted = Vector{Dict{String,Any}}()
        for (tname, meta) in tdict
            push!(converted, Dict(
                "name" => "$(sname)::$(tname)",
                "description" => get(meta, "description", ""),
                "args_schema" => get(meta, "args_schema", Dict())
            ))
        end
        out[sname] = converted
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
                    write(io, "{\"type\":\"shutdown\"}\n")
                    flush(io)
                catch
                end
                try close(io) catch end
            elseif conn[:type] == :sse
                try
                    Base.Threads.kill(conn[:task])
                catch
                end
            end
        catch e
            @warn(mgr.logger, "Error closing connection $name: $e")
        end
    end
    empty!(mgr.conns)
    empty!(mgr.tools)
end

# helper: load JSON config file and return Vector{MCPServerConfig}
function load_mcp_config(path::String)
    txt = read(path, String)
    j = JSON.parse(txt)
    configs = MCPServerConfig[]
    for item in j["mcp_servers"]
        push!(configs, MCPServerConfig(
            item["name"],
            item["transport"],
            get(item, "cmd", nothing),
            get(item, "url", nothing),
            get(item, "enabled", true)
        ))
    end
    return configs
end

end
