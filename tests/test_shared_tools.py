import json

import pytest

from shared.errors import ToolError
from shared.log_tools import Toolbox, signature
from shared.make_logs import append_new_errors_to_worker_log
from shared.memory_store import MemoryStore


@pytest.fixture
def tb(ws):
    return Toolbox(ws.logs_dir, MemoryStore(ws.memory_path))


def test_signature_normalizes_variable_parts():
    a = signature("worker", "DBTimeout: pool exhausted after 30000ms (job=1234)")
    b = signature("worker", "DBTimeout: pool exhausted after 999ms (job=8)")
    assert a == b
    assert "502" in signature("nginx", "POST /api/checkout 502 1200ms")  # status codes kept


def test_group_errors_counts_and_ranks(tb):
    out = json.loads(tb.group_errors("worker.log"))
    top = out["groups"][0]
    assert top["count"] == 30 and "DBTimeout" in top["sig"]


def test_ignore_patterns_hide_lines(tb):
    tb.remember("ignore", "healthcheck", "health")
    out = json.loads(tb.group_errors("worker.log"))
    assert out["ignored"] == 8
    assert not any("health" in g["sig"] for g in out["groups"])
    assert json.loads(tb.group_errors("worker.log", apply_ignore=False))["ignored"] == 0


def test_new_error_appears_after_pre_step(ws, tb):
    append_new_errors_to_worker_log(ws.logs_dir)
    sigs = [g["sig"] for g in json.loads(tb.group_errors("worker.log"))["groups"]]
    assert any("S3 AccessDenied" in s for s in sigs)


def test_read_log_is_capped_and_compact(tb):
    out = json.loads(tb.read_log("nginx.log", limit=500))
    assert out["shown"] == 50 and out["total"] > 1000
    assert all(len(line) <= 160 for line in out["lines"])


def test_time_filter(tb):
    out = json.loads(tb.read_log("nginx.log", level="ERROR", since="2026-10-22T14:15", until="2026-10-22T14:16"))
    assert 0 < out["total"] < 40


def test_tool_errors_are_explicit(tb):
    with pytest.raises(ToolError, match="available"):
        tb.read_log("nope.log")
    with pytest.raises(ToolError, match="regex"):
        tb.search_logs("([")
    with pytest.raises(ToolError, match="since"):
        tb.read_log("app.log", since="yesterday")
