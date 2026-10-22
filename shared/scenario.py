"""Scenario runner used by both API/main.py and SDK/main.py, so measurement is identical."""
import json
import time
from pathlib import Path

from shared.checks import run_checks
from shared.workspace import Workspace

TOKEN_KEYS = ("input", "cache_read", "cache_write", "output")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(scenario: dict, ws: Workspace, make_agent, harness: str, loc: dict) -> dict:
    """make_agent(session_id) -> object with .turn(text) -> dict and .persisted_messages() -> int"""
    turns, snapshots, persisted = [], {}, {}
    for session in scenario["sessions"]:
        sid = session["id"]
        ws.pre_step(session.get("pre"))
        print(f"\n===== session {sid}: new agent instance =====", flush=True)
        agent = make_agent(sid)  # a fresh instance per session; state comes only from disk
        for t in session["turns"]:
            print(f"\n----- {t['id']}: {t['user']}", flush=True)
            start = time.perf_counter()
            r = agent.turn(t["user"])
            r["seconds"] = round(time.perf_counter() - start, 2)
            print(f"\n>>> {r['response']}\n", flush=True)
            turns.append({
                "session": sid, "turn": t["id"], "user": t["user"],
                "tokens": {k: r[k] for k in TOKEN_KEYS},
                "model_calls": r["model_calls"],
                "tools": [c["name"] for c in r["tool_calls"]],
                "tool_calls": r["tool_calls"],
                "cost_usd": round(r["cost_usd"], 6),
                "seconds": r["seconds"],
                "response": r["response"],
            })
        persisted[sid] = agent.persisted_messages()
        snapshots[sid] = json.loads(ws.memory_path.read_text(encoding="utf-8")) if ws.memory_path.exists() else {}

    totals = {k: sum(t["tokens"][k] for t in turns) for k in TOKEN_KEYS}
    denom = totals["input"] + totals["cache_read"] + totals["cache_write"]
    totals |= {
        "cache_pct": round(100 * totals["cache_read"] / denom, 1) if denom else 0.0,
        "model_calls": sum(t["model_calls"] for t in turns),
        "tool_calls": sum(len(t["tools"]) for t in turns),
        "cost_usd": round(sum(t["cost_usd"] for t in turns), 6),
        "seconds": round(sum(t["seconds"] for t in turns), 2),
    }
    checks = run_checks(snapshots, turns, persisted)
    passed = sum(c["pass"] for c in checks)
    print(f"\n===== checks: {passed}/{len(checks)} passed =====")
    for c in checks:
        print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['id']} {c['desc']}  {c['detail'] if not c['pass'] else ''}")
    return {
        "harness": harness,
        "model": scenario["model"],
        "effort": scenario["effort"],
        "turns": turns,
        "totals": totals,
        "checks": checks,
        "checks_passed": f"{passed}/{len(checks)}",
        "memory_final": snapshots.get(scenario["sessions"][-1]["id"], {}),
        "loc": loc,
    }


def write(result: dict, out: str) -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"results -> {out}")
