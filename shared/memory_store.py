"""Persistent memory: one JSON file, four sections, upsert semantics."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from shared.errors import ToolError

SECTIONS = {
    "preference": "preferences",
    "ignore": "ignore",
    "known_issue": "known_issues",
    "incident": "incidents",
}
PREFERENCE_KEYS = {"language", "format"}
LANGUAGE_ALIASES = {"english": "en", "hebrew": "he", "עברית": "he"}


class MemoryStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            data = {}
        for section in SECTIONS.values():
            data.setdefault(section, {})
        return data

    def save(self) -> None:
        self.data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _section(self, kind: str) -> dict:
        if kind not in SECTIONS:
            raise ToolError(f"unknown kind '{kind}', use one of {sorted(SECTIONS)}")
        return self.data[SECTIONS[kind]]

    def upsert(self, kind: str, key: str, value: str) -> str | None:
        """Write key=value; returns the value it replaced (None if new)."""
        key, value = key.strip(), value.strip()
        if not key or not value:
            raise ToolError("key and value must be non-empty")
        if kind == "preference":
            key = key.lower()
            if key not in PREFERENCE_KEYS:
                raise ToolError(f"preference key must be one of {sorted(PREFERENCE_KEYS)}")
            value = value.lower()
            if key == "language":
                value = LANGUAGE_ALIASES.get(value, value)
        if kind == "ignore":
            try:
                re.compile(value)
            except re.error as e:
                raise ToolError(f"ignore value must be a valid regex: {e}") from None
        section = self._section(kind)
        old = section.get(key)
        section[key] = value
        self.save()
        return old

    def delete(self, kind: str, key: str) -> str:
        section = self._section(kind)
        if key not in section:
            raise ToolError(f"no {kind} '{key}'. existing: {sorted(section) or 'none'}")
        old = section.pop(key)
        self.save()
        return old

    def search(self, query: str | None = None, kind: str | None = None) -> dict:
        kinds = [kind] if kind else list(SECTIONS)
        words = [w for w in re.split(r"\W+", (query or "").lower()) if len(w) > 2]
        out = {}
        for k in kinds:
            hits = {
                key: val for key, val in self._section(k).items()
                if not words or any(w in f"{key} {val}".lower() for w in words)
            }
            if hits:
                out[k] = hits
        return out

    def ignore_patterns(self) -> list[re.Pattern]:
        return [re.compile(p, re.IGNORECASE) for p in self.data["ignore"].values()]
