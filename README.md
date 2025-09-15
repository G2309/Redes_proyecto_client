# MCP Chatbot Project
---
- Gustavo Adolfo Cruz Bardales - 22779
---
## Overview

This project implements a console-based chatbot that interacts with different Model Context Protocol (MCP) servers. The chatbot serves as the host, coordinating connections to local and remote MCP servers and exposing their tools to a Large Language Model (LLM). The chosen LLM is Anthropic's Claude, but the design allows flexibility to connect to other providers.

The chatbot supports context maintenance, logging of interactions, and tool discovery through MCP. It integrates both official servers (such as filesystem and git) and custom servers (local and remote) built during the project.

## Project Structure

```
.
├── claude_bot.py        # Chatbot logic using Anthropic API
├── main.py              # Entry point, command-line interface
├── mcp_config.json      # Configuration of available MCP servers
├── mcp_manager.py       # Client manager handling connections to MCP servers
├── pyproject.toml       # uv project configuration
├── README.md            # Project documentation
├── requirements.txt     # Python dependencies
├── session.json         # Saved conversation sessions and logs
├── uv.lock              # Lock file for uv package manager
```

## Features

* Connection to Anthropic Claude API as LLM
* Context maintenance across user queries
* Logging of all MCP requests and responses
* Integration with official MCP servers (filesystem and git)
* Implementation of a custom local MCP server
* Deployment of a remote MCP server on Northflank
* Command-line chatbot interface

## Branches

* `client_test`: branch used exclusively to test the client implementation. It first contained the Julia client, and later the Python version before merging into the main branch.
* `remote_mcp`: branch used to deploy the remote MCP server on Northflank. Instead of creating a separate repository, this branch was pushed to Northflank where a Dockerfile builds and runs the remote server.

## Installation

This project uses uv as the package manager.

Install required dependencies:

```
uv add rich textual black ruff pytest
```

Run the chatbot:

```
uv run python main.py
```

## Usage

After running, the chatbot starts in the terminal and maintains a conversation log. You can interact with it by asking general questions to the LLM or by invoking tools exposed through MCP servers configured in `mcp_config.json`.

Examples of scenarios:

* Ask general knowledge questions through Claude
* Use filesystem MCP to list or create files
* Use git MCP to initialize a repository and commit files
* Call custom local MCP server with advanced functionality
* Call remote MCP server deployed on Northflank

## Difficulties

At the beginning, the client was implemented in Julia. Although it worked, building a terminal user interface was complicated (mostly because of my lack of experience using TerminalUserInterface.jl), so the decision was made to switch to Python. 
Another difficulty was selecting a platform to host the remote MCP server. I thought of Google Cloud Run, Netlify, or AWS, but after research Northflank was chosen and worked successfully.
Also, originally the plan was to use ChatGPT as LLM, but the API key had expired, so the final implementation used Anthropic Claude instead.

## Lessons Learned

* MCP provides a unified way to connect tools regardless of the LLM vendor
* Handling asynchronous communication in Python was simpler compared to Julia for this use case
* Handling try catch is easier in Python compared to Julia
* Interoperability between tools and chatbots is possible with a clear protocol definition


