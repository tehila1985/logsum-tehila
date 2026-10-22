"""Loop, tools, history, context, caching, compaction, tokens — against the fake client."""
import json

from fakes import FakeClient, response, text, thinking, tool_use

from API.agent import LogSumAgent
from API.harness import caching
from API.harness.history import History
from API.harness.tokens import TokenMeter, cache_pct


def make(ws, script, session="s1", **kw):
    client = FakeClient(script)
    return client, LogSumAgent(client, ws, session, "claude-opus-5-5", "medium", **kw)


def test_parallel_tool_results_return_in_one_message(ws):
    client, agent = make(ws, [
        response(thinking(), tool_use("a", "list_logs"), tool_use("b", "group_errors", file="app.log"), stop="tool_use"),
        response(text("done")),
    ])
    out = agent.turn("what's wrong?")
    assert out["response"] == "done" and out["model_calls"] == 2
    assert [c["name"] for c in out["tool_calls"]] == ["list_logs", "group_errors"]
    second = client.requests[1]["messages"]
    results = second[-1]["content"]
    assert second[-1]["role"] == "user" and [r["tool_use_id"] for r in results] == ["a", "b"]
    # the thinking block is passed back unchanged
    assert second[-2]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}


def test_tool_errors_go_back_as_is_error(ws):
    client, agent = make(ws, [
        response(tool_use("a", "read_log", file="missing.log"), tool_use("b", "no_such_tool"), stop="tool_use"),
        response(text("sorry")),
    ])
    agent.turn("read missing")
    results = client.requests[1]["messages"][-1]["content"]
    assert all(r["is_error"] for r in results)
    assert "available" in results[0]["content"] and "unknown tool" in results[1]["content"]


def test_loop_stops_at_max_iterations(ws):
    script = [response(tool_use(f"x{i}", "list_logs"), stop="tool_use") for i in range(8)]
    _, agent = make(ws, script)
    out = agent.turn("loop forever")
    assert out["model_calls"] == 8 and "stopped" in out["response"]


def test_remember_tool_writes_memory_and_new_instance_sees_it(ws):
    _, agent = make(ws, [
        response(tool_use("a", "remember", kind="known_issue", key="DBTimeout", value="nightly backup"), stop="tool_use"),
        response(text("saved")),
    ])
    agent.turn("DBTimeout is the backup, remember")
    client2, agent2 = make(ws, [response(text("ok"))], session="s2")
    agent2.turn("anything on DBTimeout?")
    first_user = client2.requests[0]["messages"][0]["content"]
    assert "nightly backup" in first_user[0]["text"]  # memory block, from disk


def test_history_is_append_only_and_reloads(ws):
    _, agent = make(ws, [response(text("one")), response(text("two"))])
    agent.turn("first")
    size1 = agent.history.path.stat().st_size
    agent.turn("second")
    assert agent.history.path.stat().st_size > size1
    lines = agent.history.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert History(agent.history.path).message_count() == 4


def test_system_prompt_is_frozen_and_memory_rides_in_user_turn(ws):
    client, agent = make(ws, [response(text("a")), response(text("b"))])
    agent.turn("first")
    agent.memory.store.upsert("preference", "language", "he")
    agent.turn("second")
    s0, s1 = client.requests[0]["system"], client.requests[1]["system"]
    assert s0 == s1
    assert "language=he" in client.requests[1]["messages"][-1]["content"][0]["text"]
    # earlier messages are sent byte-identical (append-only prefix)
    strip = lambda m: json.dumps(m["content"][0]["text"])  # noqa: E731
    assert strip(client.requests[0]["messages"][0]) == strip(client.requests[1]["messages"][0])


def test_no_raw_log_in_context(ws):
    client, agent = make(ws, [response(text("ok"))])
    agent.turn("summarize app.log")
    sent = json.dumps(client.requests[0])
    assert "Order 1" not in sent and "INFO OrderService" not in sent


def test_cache_breakpoints():
    system = [{"type": "text", "text": "s"}]
    tools = [{"name": "a"}, {"name": "b"}]
    messages = [{"role": "user", "content": "hi"}]
    s, t, m = caching.apply(system, tools, messages)
    marks = [x for x in (s[-1], t[-1], m[-1]["content"][-1]) if "cache_control" in x]
    assert len(marks) == 3 and "cache_control" not in t[0]
    assert "cache_control" not in tools[-1] and messages[0]["content"] == "hi"  # inputs untouched


def test_compaction_summarizes_and_keeps_disk_history(ws):
    client, agent = make(ws, [
        response(text("answer"), inp=50_000),
        response(text("SUMMARY: DBTimeout is known.")),
        response(text("next")),
    ], compact_at=10_000)
    agent.turn("first")
    assert agent.history.entries[-1]["type"] == "compaction"
    agent.turn("second")
    msgs = client.requests[2]["messages"]
    assert len(msgs) == 1 and "SUMMARY: DBTimeout is known." in msgs[0]["content"][0]["text"]
    assert agent.history.message_count() == 4  # nothing deleted


def test_tokens_cost_and_cache_pct():
    meter = TokenMeter("claude-opus-5-5")
    meter.record(response(inp=1000, out=100, cache_r=9000, cache_w=0).usage)
    t = meter.end_turn()
    assert t["cost_usd"] == round((1000 * 4 + 9000 * 0.2 + 100 * 20) / 1e6, 6)
    assert cache_pct(t) == 90.0


def test_fallbacks_and_effort_in_request(ws):
    client, agent = make(ws, [response(text("ok"))])
    agent.turn("hi")
    req = client.requests[0]
    assert req["output_config"] == {"effort": "medium"} and req["fallbacks"] == "default"
