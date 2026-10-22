"""LogSum on the Claude Agent SDK: Claude Code runs the harness, this file configures it."""
import asyncio
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage,
                              ToolUseBlock, get_session_messages)

from SDK.tools import SERVER, TOOL_IDS, build_server
from shared.log_tools import Toolbox
from shared.memory_store import MemoryStore
from shared.schemas import SYSTEM_PROMPT
from shared.workspace import Workspace

SDK_DIR = Path(__file__).resolve().parent  # holds CLAUDE.md

# Nothing is injected per turn, so the model has to pull memory itself.
SDK_SYSTEM_PROMPT = SYSTEM_PROMPT + (  # replaces: context
    "\n- Memory is not shown to you. Before answering a request about logs, call recall once"  # replaces: context, memory
    " (no query) to load preferences, ignore patterns, known issues and incidents."  # replaces: context, memory
)


class LogSumAgent:
    def __init__(self, ws: Workspace, session_id: str, model: str, effort: str, resume: str | None = None):
        self.memory = MemoryStore(ws.memory_path)
        self.server = build_server(Toolbox(ws.logs_dir, self.memory))
        self.model, self.effort = model, effort
        self.label = session_id
        self.session_id = resume  # Claude Code's own session id, set after the first turn

    def _options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=self.model,
            effort=self.effort,
            system_prompt=SDK_SYSTEM_PROMPT,  # replaces: context
            tools=[],  # no built-in tools (Read/Bash/...): only ours  # replaces: tools
            mcp_servers={SERVER: self.server},  # replaces: tools
            allowed_tools=TOOL_IDS,  # replaces: tools
            strict_mcp_config=True,  # replaces: tools
            permission_mode="dontAsk",
            setting_sources=["project"],  # loads SDK/CLAUDE.md  # replaces: memory
            cwd=str(SDK_DIR),
            resume=self.session_id,  # conversation is reloaded from Claude Code's transcript  # replaces: history
            max_turns=8,  # replaces: loop
        )

    async def _turn(self, text: str) -> dict:
        tool_calls, calls, response = [], set(), ""
        result = None
        async with ClaudeSDKClient(self._options()) as client:
            await client.query(text)  # replaces: loop
            async for msg in client.receive_response():  # replaces: loop
                if isinstance(msg, AssistantMessage) and msg.parent_tool_use_id is None:
                    calls.add(msg.message_id)  # replaces: tokens
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            tool_calls.append({"name": block.name.removeprefix(f"mcp__{SERVER}__"),
                                               "input": block.input})
                elif isinstance(msg, ResultMessage):
                    result = msg  # replaces: tokens
        # compaction and prompt caching: automatic inside Claude Code  # replaces: compaction, caching
        self.session_id = result.session_id
        usage = result.usage or {}  # replaces: tokens
        return {
            "response": result.result or response,
            "tool_calls": tool_calls,
            "input": usage.get("input_tokens", 0),  # replaces: tokens
            "cache_read": usage.get("cache_read_input_tokens", 0),  # replaces: tokens
            "cache_write": usage.get("cache_creation_input_tokens", 0),  # replaces: tokens
            "output": usage.get("output_tokens", 0),  # replaces: tokens
            "model_calls": len(calls),
            "cost_usd": result.total_cost_usd or 0.0,  # replaces: tokens
        }

    def turn(self, text: str) -> dict:
        r = asyncio.run(self._turn(text))
        print(f"[sdk] {self.label}: calls={r['model_calls']} in={r['input']} cache_r={r['cache_read']} "
              f"cache_w={r['cache_write']} out={r['output']} ${r['cost_usd']:.4f} tools={[c['name'] for c in r['tool_calls']]}",
              flush=True)
        return r

    def persisted_messages(self) -> int:
        if not self.session_id:
            return 0
        return len(get_session_messages(self.session_id, directory=str(SDK_DIR)))
