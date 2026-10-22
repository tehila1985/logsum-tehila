"""Print the REPORT.md tables from results/api.json and results/sdk.json (either may be missing)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTS = ["loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens", "total"]


def load(name):
    p = ROOT / "results" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cell(r, f):
    return f(r) if r else "—"


def main() -> None:
    api, sdk = load("api"), load("sdk")
    rows = [
        ("input tokens", lambda r: f"{r['totals']['input']:,}"),
        ("cache read", lambda r: f"{r['totals']['cache_read']:,}"),
        ("cache write", lambda r: f"{r['totals']['cache_write']:,}"),
        ("output tokens", lambda r: f"{r['totals']['output']:,}"),
        ("cache %", lambda r: f"{r['totals']['cache_pct']}%"),
        ("model calls", lambda r: str(r["totals"]["model_calls"])),
        ("tool calls", lambda r: str(r["totals"]["tool_calls"])),
        ("cost (USD)", lambda r: f"${r['totals']['cost_usd']:.4f}"),
        ("time (s)", lambda r: str(r["totals"]["seconds"])),
        ("checks passed", lambda r: r["checks_passed"]),
    ]
    print("| metric | API | SDK |\n|---|---|---|")
    for label, f in rows:
        print(f"| {label} | {cell(api, f)} | {cell(sdk, f)} |")

    print("\n| turn | API in / cache_r / cache_w / out | API calls | API tools | SDK in / cache_r / cache_w / out | SDK calls | SDK tools |")
    print("|---|---|---|---|---|---|---|")
    ids = [t["turn"] for t in (api or sdk or {"turns": []})["turns"]]
    for tid in ids:
        out = [tid]
        for r in (api, sdk):
            t = next((x for x in r["turns"] if x["turn"] == tid), None) if r else None
            if t:
                k = t["tokens"]
                out += [f"{k['input']:,} / {k['cache_read']:,} / {k['cache_write']:,} / {k['output']:,}",
                        str(t["model_calls"]), ", ".join(t["tools"]) or "—"]
            else:
                out += ["—", "—", "—"]
        print("| " + " | ".join(out) + " |")

    print("\n| check | API | SDK |\n|---|---|---|")
    base = (api or sdk or {"checks": []})["checks"]
    for c in base:
        def res(r):
            if not r:
                return "—"
            m = next(x for x in r["checks"] if x["id"] == c["id"])
            return "PASS" if m["pass"] else "FAIL"
        print(f"| {c['id']} ({c['kind']}) {c['desc']} | {res(api)} | {res(sdk)} |")

    sys.path.insert(0, str(ROOT))
    from tools.count_loc import api_loc, sdk_loc
    a, s = api_loc(), sdk_loc()
    print("\n| part | API (lines) | SDK (lines marked `# replaces:`) |\n|---|---|---|")
    for p in PARTS:
        print(f"| {p} | {a[p]} | {s[p]} |")


if __name__ == "__main__":
    main()
