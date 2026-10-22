"""Long-term memory: lives in memory.json (shared.MemoryStore); this file decides what reaches the model."""
import re
from pathlib import Path

from API.harness import trace
from shared.memory_store import MemoryStore


class Memory:
    def __init__(self, path: Path):
        self.store = MemoryStore(path)
        trace(__file__, f"loaded {self._size()} entries from {Path(path).name}")

    def _size(self) -> int:
        d = self.store.data
        return sum(len(d[s]) for s in ("preferences", "ignore", "known_issues", "incidents"))

    def relevant(self, user_text: str) -> str:
        """Always: preferences + ignore list (small, affect every answer).
        Known issues / incidents: full text only if they match the request; otherwise just an index."""
        d = self.store.data
        words = {w for w in re.split(r"\W+", user_text.lower()) if len(w) > 2}

        def matches(k, v):
            text = f"{k} {v}".lower()
            return any(w in text for w in words)

        lines, picked = [], 0
        if d["preferences"]:
            lines.append("preferences: " + ", ".join(f"{k}={v}" for k, v in d["preferences"].items()))
            picked += len(d["preferences"])
        if d["ignore"]:
            lines.append("ignored patterns (already hidden by tools): " + ", ".join(d["ignore"]))
            picked += len(d["ignore"])
        for section, label in (("known_issues", "known issue"), ("incidents", "incident")):
            hits = {k: v for k, v in d[section].items() if matches(k, v)}
            for k, v in hits.items():
                lines.append(f"{label} {k}: {v}")
            picked += len(hits)
            rest = [k for k in d[section] if k not in hits]
            if rest:
                lines.append(f"other {section} (use recall for details): " + ", ".join(rest))
        trace(__file__, f"selected {picked}/{self._size()} entries in full for this turn")
        if not lines:
            return "<memory>empty</memory>"
        return "<memory>\n" + "\n".join(lines) + "\n</memory>"
