"""Scenario pass/fail checks. Most look at saved state, not at reply text.

Inputs (both harnesses produce the same shapes):
  snapshots: {"s1": memory_dict_after_session_1, "s2": ...}
  turns:     [{"turn": "t1", "response": str, "tool_calls": [{"name": str, "input": dict}]}]
  persisted: {"s1": number_of_messages_saved_to_disk, "s2": ...}
"""
import re


def _entries(section: dict) -> list[str]:
    return [f"{k} {v}".lower() for k, v in (section or {}).items()]


def _turn(turns, tid):
    return next((t for t in turns if t["turn"] == tid), {"response": "", "tool_calls": []})


def hebrew_ratio(text: str) -> float:
    he = len(re.findall(r"[֐-׿]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return he / (he + latin) if he + latin else 0.0


def run_checks(snapshots: dict, turns: list, persisted: dict) -> list[dict]:
    s1, s2 = snapshots.get("s1", {}), snapshots.get("s2", {})
    t5, t6, t8 = _turn(turns, "t5"), _turn(turns, "t6"), _turn(turns, "t8")
    t5_text, t6_text = t5["response"].lower(), t6["response"].lower()
    log_tools = {"group_errors", "read_log", "search_logs"}

    results = []

    def check(cid, kind, desc, ok, detail=""):
        results.append({"id": cid, "kind": kind, "desc": desc, "pass": bool(ok), "detail": detail})

    known = _entries(s1.get("known_issues"))
    check("C1", "state", "s1: DBTimeout saved as known issue caused by backup",
          any(re.search(r"db ?timeout", e) and "backup" in e for e in known), str(known))

    incidents = _entries(s1.get("incidents"))
    check("C2", "state", "s1: checkout/nginx incident saved",
          any("checkout" in e or "nginx" in e for e in incidents), str(incidents))

    fmt = (s1.get("preferences") or {}).get("format", "")
    check("C3", "state", "s1: preference format=bullets", fmt.startswith("bullet"), fmt)

    ignore_s1 = _entries(s1.get("ignore"))
    ignore_s2 = _entries(s2.get("ignore"))
    check("C4", "state", "s1 had a healthcheck ignore; s2 removed it (contradiction resolved)",
          any("health" in e for e in ignore_s1) and not any("health" in e for e in ignore_s2),
          f"s1={ignore_s1} s2={ignore_s2}")

    lang = (s2.get("preferences") or {}).get("language", "")
    check("C5", "state", "s2: preference language overwritten to he", lang == "he", lang)

    used = {c["name"] for c in t5["tool_calls"]}
    check("C6", "tools+text", "t5: read logs with a tool and found the new S3 AccessDenied error",
          bool(used & log_tools) and ("s3" in t5_text or "accessdenied" in t5_text), str(sorted(used)))

    check("C7", "text", "t5: DBTimeout not reported as new (known issue from memory)",
          "dbtimeout" not in t5_text.replace(" ", "") or any(w in t5_text for w in ("known", "backup", "ידוע")),
          "")

    nginx_reads = [c for c in t6["tool_calls"] if (c.get("input") or {}).get("file") == "nginx.log"]
    check("C8", "state+text", "t6: checkout incident answered from memory, without re-reading nginx.log",
          "checkout" in t6_text and not nginx_reads, f"nginx reads={len(nginx_reads)}")

    ratio = hebrew_ratio(_turn(turns, "t8")["response"])
    check("C9", "text", "t8: summary written in Hebrew (>30% Hebrew letters)", ratio > 0.3, f"{ratio:.2f}")

    check("C10", "state", "conversation of each session persisted to disk",
          all(persisted.get(s, 0) > 0 for s in ("s1", "s2")), str(persisted))

    return results
