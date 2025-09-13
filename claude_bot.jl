module ClaudeBot

using JSON
using Dates
using Logging
using HTTP
using ..MCPManager

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
