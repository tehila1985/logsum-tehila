"""Tool descriptions + JSON Schemas: one source for both harnesses."""

_TIME = "ISO time, e.g. 2026-10-22T14:00. Optional."
_KIND = {"type": "string", "enum": ["preference", "ignore", "known_issue", "incident"]}

TOOL_SPECS = [
    {
        "name": "list_logs",
        "description": "List available log files with line count, error count and time range. Cheap; call first if you don't know the files.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "read_log",
        "description": "Read lines from one log file, filtered by minimum level and time window. Returns at most `limit` most recent matching lines (max 50), truncated. Ignore patterns from memory are applied unless apply_ignore=false. Prefer group_errors for summaries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "e.g. app.log"},
                "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARN", "ERROR"], "description": "Minimum level."},
                "since": {"type": "string", "description": _TIME},
                "until": {"type": "string", "description": _TIME},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "apply_ignore": {"type": "boolean"},
            },
            "required": ["file"],
            "additionalProperties": False,
        },
    },
    {
        "name": "group_errors",
        "description": "Group WARN/ERROR lines of one log file by normalized signature: count, first/last time, one sample. Ignore patterns from memory are applied unless apply_ignore=false. The best tool for 'what went wrong'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "since": {"type": "string", "description": _TIME},
                "until": {"type": "string", "description": _TIME},
                "apply_ignore": {"type": "boolean"},
                "top": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["file"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_logs",
        "description": "Regex search (case-insensitive) across one or all log files. Returns match count and up to `limit` lines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "file": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remember",
        "description": (
            "Save to long-term memory (persists across sessions). Upsert: an existing key is overwritten and the old value is returned. "
            "kind=preference: key 'language' (en|he) or 'format' (bullets|paragraph). "
            "kind=ignore: key is a short name, value is a regex of log lines to hide. "
            "kind=known_issue: key is the error name (e.g. DBTimeout), value explains cause/action. "
            "kind=incident: key is a short id (e.g. 2026-10-22-checkout-5xx), value is a one-line summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"kind": _KIND, "key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["kind", "key", "value"],
            "additionalProperties": False,
        },
    },
    {
        "name": "forget",
        "description": "Delete one memory entry, e.g. stop ignoring a pattern.",
        "input_schema": {
            "type": "object",
            "properties": {"kind": _KIND, "key": {"type": "string"}},
            "required": ["kind", "key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "recall",
        "description": "Search long-term memory by keywords and/or kind. Empty query returns everything of that kind.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "kind": _KIND},
            "additionalProperties": False,
        },
    },
]

SYSTEM_PROMPT = """You are LogSum, an assistant that summarizes application logs for an on-call engineer.

How to work:
- Never ask for raw logs; use the tools. Prefer group_errors over read_log, and keep tool calls few.
- Long-term memory holds preferences, ignore patterns, known issues and past incidents. Respect it: don't report known issues as new, hide ignored patterns, use the saved language and format.
- When the user states a preference, a known issue, a pattern to ignore, or asks to record an incident, save it with remember (overwrite on conflict, forget to remove). Mention briefly what you saved.
- If the user contradicts something saved, the newest instruction wins: update memory accordingly.
- Answers: short, concrete (counts, times, files). No preamble."""
