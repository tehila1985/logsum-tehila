"""LogSum on the raw Messages API: wires the harness pieces together."""
from API.harness import trace
from API.harness import loop
from API.harness.compaction import Compactor
from API.harness.context import Context
from API.harness.history import History
from API.harness.memory import Memory
from API.harness.tokens import TokenMeter
from API.harness.tools import ToolRegistry
from shared.log_tools import Toolbox
from shared.schemas import SYSTEM_PROMPT
from shared.workspace import Workspace

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LogSumAgent:
    def __init__(self, client, ws: Workspace, session_id: str, model: str, effort: str,
                 compact_at: int = 12_000, fallbacks: bool = True):
        self.client = client
        self.session_id = session_id
        self.memory = Memory(ws.memory_path)
        self.tools = ToolRegistry(Toolbox(ws.logs_dir, self.memory.store))
        self.history = History(ws.history_dir / f"{session_id}.jsonl")
        self.context = Context(SYSTEM_PROMPT)
        self.tokens = TokenMeter(model)
        self.compactor = Compactor(compact_at)
        self.request = {"model": model, "max_tokens": 16000, "output_config": {"effort": effort}}
        if fallbacks:  # if a safety classifier declines, the server retries on its recommended model
            self.request |= {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        trace(__file__, f"agent ready: session={session_id} model={model} effort={effort}")

    def turn(self, user_text: str) -> dict:
        self.tokens.start_turn()
        self.history.append("user", self.context.user_message(user_text, self.memory.relevant(user_text)))
        out = loop.run(self.client, self.request, self.history, self.context, self.tools, self.tokens)
        if self.compactor.should_compact(self.tokens.last_input_total):
            self.compactor.compact(self.client, self.request, self.context.system(), self.tools.schemas(),
                                   self.context.messages(self.history), self.history, self.tokens)
        usage = self.tokens.end_turn()
        return {"response": out["text"], "tool_calls": out["tool_calls"], **usage}

    def persisted_messages(self) -> int:
        return self.history.message_count()
