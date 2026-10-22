"""Lines of code per harness part.

API: non-blank, non-comment, non-docstring lines of each API/harness/<part>.py.
SDK: lines tagged '# replaces: <part>' in SDK/*.py.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTS = ["loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens"]


def _code_lines(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    doc_lines = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    return sum(1 for i, line in enumerate(src.splitlines(), 1)
               if line.strip() and not line.strip().startswith("#") and i not in doc_lines)


def api_loc() -> dict:
    loc = {p: _code_lines(ROOT / "API" / "harness" / f"{p}.py") for p in PARTS}
    loc["total"] = sum(loc.values())
    return loc


def sdk_loc() -> dict:
    loc = dict.fromkeys(PARTS, 0)
    tag = re.compile(r"#\s*replaces:\s*([\w, ]+)")
    for path in (ROOT / "SDK").glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = tag.search(line)
            if m:
                for part in (p.strip() for p in m.group(1).split(",")):
                    if part in loc:
                        loc[part] += 1
    loc["total"] = sum(loc.values())
    return loc


if __name__ == "__main__":
    print("API", api_loc())
    print("SDK", sdk_loc())
    sys.exit(0)
