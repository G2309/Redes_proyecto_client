module MCPManager

using JSON
using Sockets
using HTTP
using Logging
using Base.Threads: @spawn

struct MCPServerConfig
	name::String
	transport::String 
	cmd::Union{Nothing,String}
	url::Union{Nothing,String}
	enabled::Bool
	end

mutable struct MCPMgr
	servers::Dict{String,MCPServerConfig}
	tools::Dict{String,Any} 
	conns::Dict{String,Any}
	logger::AbstractLogger
	end

function MCPMgr(configs::Vector{MCPServerConfig}; logger=ConsoleLogger())
	sdict = Dict(cfg.name => cfg for cfg in configs)
	return MCPMgr(sdict, Dict{String,Any}(), Dict{String,Any}(), logger)
	end


