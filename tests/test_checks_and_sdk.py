import asyncio
import json

from shared.checks import hebrew_ratio, run_checks
from shared.log_tools import Toolbox
from shared.memory_store import MemoryStore
from tools.count_loc import api_loc, sdk_loc

GOOD = {
    "s1": {"known_issues": {"DBTimeout": "nightly backup"}, "incidents": {"checkout-5xx": "nginx 5xx"},
           "preferences": {"format": "bullets", "language": "en"}, "ignore": {"healthcheck": "health"}},
    "s2": {"known_issues": {"DBTimeout": "nightly backup"}, "incidents": {},
           "preferences": {"format": "bullets", "language": "he"}, "ignore": {}},
}
TURNS = [
    {"turn": "t5", "response": "New: S3 AccessDenied x6. DBTimeout is known (backup).",
     "tool_calls": [{"name": "group_errors", "input": {"file": "worker.log"}}]},
    {"turn": "t6", "response": "Yes: checkout 5xx at 14:10", "tool_calls": [{"name": "recall", "input": {}}]},
    {"turn": "t8", "response": "סיכום: שגיאות S3 חדשות, healthcheck נכשל 3 פעמים", "tool_calls": []},
]


def test_all_checks_pass_on_good_state():
    res = run_checks(GOOD, TURNS, {"s1": 8, "s2": 6})
    assert all(c["pass"] for c in res), [c for c in res if not c["pass"]]
    assert len(res) >= 5 and sum(c["kind"].startswith("state") for c in res) >= 5


def test_checks_fail_on_bad_state():
    bad = json.loads(json.dumps(GOOD))
    bad["s2"]["ignore"] = {"healthcheck": "health"}   # contradiction not applied
    bad["s2"]["preferences"]["language"] = "en"
    res = {c["id"]: c["pass"] for c in run_checks(bad, TURNS, {"s1": 8, "s2": 0})}
    assert not res["C4"] and not res["C5"] and not res["C10"]


def test_hebrew_ratio():
    assert hebrew_ratio("שלום world") > 0.3 and hebrew_ratio("hello") == 0


def test_sdk_tool_wrappers_call_shared_and_flag_errors(ws):
    from SDK.tools import TOOL_IDS, _wrap
    from shared.schemas import TOOL_SPECS

    tb = Toolbox(ws.logs_dir, MemoryStore(ws.memory_path))
    spec = {s["name"]: s for s in TOOL_SPECS}
    ok = asyncio.run(_wrap(tb, spec["group_errors"]).handler({"file": "app.log"}))
    assert "NullPointerException" in ok["content"][0]["text"] and not ok.get("is_error")
    bad = asyncio.run(_wrap(tb, spec["read_log"]).handler({"file": "nope.log"}))
    assert bad["is_error"]
    assert "mcp__logsum__recall" in TOOL_IDS


def test_loc_counter():
    api, sdk = api_loc(), sdk_loc()
    assert api["loop"] > 10 and sdk["loop"] >= 2 and sdk["total"] < api["total"]
