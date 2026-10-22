"""Domain tools. Every method returns a compact JSON string or raises ToolError.

The raw log never leaves this module: callers get filtered lines (capped) or
aggregates (error signatures with counts).
"""
import json
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from shared.errors import ToolError
from shared.memory_store import MemoryStore

LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
LINE_RE = re.compile(r"^(\S+) (DEBUG|INFO|WARN|ERROR) (\S+) (.*)$")
MAX_LINE = 160
MAX_LIMIT = 50


def compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def signature(service: str, msg: str) -> str:
    """Collapse the variable parts of a message so repeats group together."""
    s = re.sub(r"\(\w+=[^)]*\)", "", msg)
    s = re.sub(r"\b[0-9a-f]{8,}\b", "<ID>", s)
    s = re.sub(r"/\d+", "/<N>", s)
    s = re.sub(r"\d+(\.\d+)?(ms|s)\b", r"<N>\2", s)
    s = re.sub(r"\d{4,}", "<N>", s)  # 3-digit numbers stay: they are HTTP status codes
    return f"{service}: {s.strip()}"[:100]


class Toolbox:
    def __init__(self, log_dir: Path, memory: MemoryStore):
        self.log_dir = Path(log_dir)
        self.memory = memory

    # ---------- helpers ----------
    def _path(self, file: str) -> Path:
        p = (self.log_dir / file).resolve()
        if p.parent != self.log_dir.resolve() or not p.is_file():
            names = sorted(x.name for x in self.log_dir.glob("*.log"))
            raise ToolError(f"no log file '{file}'. available: {names}")
        return p

    @staticmethod
    def _time(value: str | None, name: str) -> str | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass
        raise ToolError(f"{name} must look like 2026-10-22T14:00 (got '{value}')")

    def _rows(self, file: str, since=None, until=None, min_level=None, apply_ignore=False):
        since, until = self._time(since, "since"), self._time(until, "until")
        if min_level and min_level.upper() not in LEVELS:
            raise ToolError(f"level must be one of {list(LEVELS)}")
        floor = LEVELS[min_level.upper()] if min_level else 0
        ignore = self.memory.ignore_patterns() if apply_ignore else []
        ignored = 0
        rows = []
        with self._path(file).open(encoding="utf-8") as f:
            for line in f:
                m = LINE_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                ts, level, service, msg = m.groups()
                if (since and ts < since) or (until and ts > until) or LEVELS[level] < floor:
                    continue
                if any(p.search(line) for p in ignore):
                    ignored += 1
                    continue
                rows.append((ts, level, service, msg))
        return rows, ignored

    # ---------- tools ----------
    def list_logs(self) -> str:
        out = []
        for p in sorted(self.log_dir.glob("*.log")):
            rows, _ = self._rows(p.name)
            errors = sum(1 for r in rows if r[1] == "ERROR")
            out.append({"file": p.name, "lines": len(rows), "errors": errors,
                        "from": rows[0][0] if rows else None, "to": rows[-1][0] if rows else None})
        return compact(out)

    def read_log(self, file: str, level: str | None = None, since: str | None = None,
                 until: str | None = None, limit: int = 20, apply_ignore: bool = True) -> str:
        limit = max(1, min(int(limit), MAX_LIMIT))
        rows, ignored = self._rows(file, since, until, level, apply_ignore)
        shown = [f"{ts} {lv} {svc} {msg}"[:MAX_LINE] for ts, lv, svc, msg in rows[-limit:]]
        return compact({"total": len(rows), "shown": len(shown), "ignored": ignored, "lines": shown})

    def group_errors(self, file: str, since: str | None = None, until: str | None = None,
                     apply_ignore: bool = True, top: int = 10) -> str:
        rows, ignored = self._rows(file, since, until, "WARN", apply_ignore)
        groups: "OrderedDict[str, dict]" = OrderedDict()
        for ts, level, service, msg in rows:
            sig = signature(service, msg)
            g = groups.setdefault(sig, {"sig": sig, "level": level, "count": 0, "first": ts,
                                        "last": ts, "sample": msg[:MAX_LINE]})
            g["count"] += 1
            g["last"] = ts
        ranked = sorted(groups.values(), key=lambda g: (-LEVELS[g["level"]], -g["count"]))
        top = max(1, min(int(top), 20))
        return compact({"file": file, "warn_or_error_lines": len(rows), "ignored": ignored,
                        "groups": ranked[:top], "more_groups": max(0, len(ranked) - top)})

    def search_logs(self, pattern: str, file: str | None = None, limit: int = 10) -> str:
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ToolError(f"invalid regex: {e}") from None
        limit = max(1, min(int(limit), MAX_LIMIT))
        files = [file] if file else sorted(p.name for p in self.log_dir.glob("*.log"))
        matches, shown = 0, []
        for name in files:
            for ts, lv, svc, msg in self._rows(name)[0]:
                line = f"{ts} {lv} {svc} {msg}"
                if rx.search(line):
                    matches += 1
                    if len(shown) < limit:
                        shown.append(f"{name}: {line}"[:MAX_LINE])
        return compact({"matches": matches, "shown": shown})

    def remember(self, kind: str, key: str, value: str) -> str:
        old = self.memory.upsert(kind, key, value)
        return compact({"ok": True, "kind": kind, "key": key, "replaced": old})

    def forget(self, kind: str, key: str) -> str:
        old = self.memory.delete(kind, key)
        return compact({"ok": True, "kind": kind, "key": key, "removed": old})

    def recall(self, query: str | None = None, kind: str | None = None) -> str:
        return compact(self.memory.search(query, kind))


TOOL_NAMES = ["list_logs", "read_log", "group_errors", "search_logs", "remember", "forget", "recall"]
