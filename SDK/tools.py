"""The same shared tools, exposed to Claude Code as an in-process MCP server."""
from claude_agent_sdk import create_sdk_mcp_server, tool

from shared.errors import ToolError
from shared.log_tools import Toolbox
from shared.schemas import TOOL_SPECS

SERVER = "logsum"
TOOL_IDS = [f"mcp__{SERVER}__{spec['name']}" for spec in TOOL_SPECS]  # replaces: tools


def _wrap(toolbox: Toolbox, spec: dict):
    fn = getattr(toolbox, spec["name"])

    @tool(spec["name"], spec["description"], spec["input_schema"])  # replaces: tools
    async def handler(args: dict) -> dict:
        try:
            return {"content": [{"type": "text", "text": fn(**args)}]}  # replaces: tools
        except (ToolError, TypeError) as e:
            return {"content": [{"type": "text", "text": f"error: {e}"}], "is_error": True}  # replaces: tools

    return handler


def build_server(toolbox: Toolbox):
    tools = [_wrap(toolbox, spec) for spec in TOOL_SPECS]  # replaces: tools
    return create_sdk_mcp_server(SERVER, tools=tools)  # replaces: tools
