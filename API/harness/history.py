"""Conversation on disk: append-only JSONL, one line per message or compaction marker."""
import json
from datetime import datetime, timezone
from pathlib import Path

from API.harness import trace


def to_param(block) -> dict:
    """Response content block -> request content block (exactly the fields the API accepts back)."""
    t = block.type
    if t == "text":
        return {"type": "text", "text": block.text}
    if t == "thinking":
        return {"type": "thinking", "thinking": block.thinking, "signature": block.signature}
    if t == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.data}
    if t == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return block.model_dump(mode="json", exclude_none=True)


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: list[dict] = []
        if self.path.exists():
            with self.path.open(encoding="utf-8") as f:
                self.entries = [json.loads(line) for line in f if line.strip()]
            trace(__file__, f"loaded {len(self.entries)} entries from {self.path.name}")

    def _append(self, entry: dict) -> None:
        entry["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.entries.append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def append(self, role: str, content: list[dict]) -> None:
        self._append({"type": "message", "role": role, "content": content})
        trace(__file__, f"append {role} message #{self.message_count()} ({len(content)} blocks)")

    def append_compaction(self, summary: str) -> None:
        self._append({"type": "compaction", "summary": summary})
        trace(__file__, f"append compaction marker ({len(summary)} chars); older messages stay on disk")

    def message_count(self) -> int:
        return sum(1 for e in self.entries if e["type"] == "message")

    def active(self) -> tuple[str | None, list[dict]]:
        """(latest compaction summary, messages after it)."""
        summary, msgs = None, []
        for e in self.entries:
            if e["type"] == "compaction":
                summary, msgs = e["summary"], []
            else:
                msgs.append({"role": e["role"], "content": e["content"]})
        return summary, msgs
