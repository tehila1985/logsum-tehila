"""The web backend, driven with the real API harness on the fake client (no key, no socket)."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from fakes import FakeClient, response, text, tool_use

from API.agent import LogSumAgent
from web.server import Backend, Harness, make_handler


@pytest.fixture
def backend(tmp_path):
    client = FakeClient([
        response(tool_use("a", "remember", kind="preference", key="language", value="hebrew"), stop="tool_use"),
        response(text("שמרתי: עברית")),
        response(text("second session answer")),
    ])
    api = Harness("api", lambda ws, sid: LogSumAgent(client, ws, sid, "claude-opus-5-5", "medium"), True,
                  root=tmp_path / "api")
    off = Harness("sdk", None, False, "off for the test", root=tmp_path / "sdk")
    return Backend({"api": api, "sdk": off})


def test_chat_runs_agent_and_returns_memory(backend):
    r = backend.chat("api", "from now on answer in Hebrew")
    assert r["turn"]["response"] == "שמרתי: עברית"
    assert [c["name"] for c in r["turn"]["tool_calls"]] == ["remember"]
    assert r["memory"]["preferences"] == {"language": "he"}
    assert {l["file"] for l in r["logs"]} == {"app.log", "nginx.log", "worker.log"}


def test_new_session_is_a_new_instance_with_memory_from_disk(backend):
    backend.chat("api", "remember hebrew")
    s = backend.new_session("api")
    assert s["current"]["session"] == "s2"
    r = backend.chat("api", "hi")
    assert r["turn"]["session"] == "s2" and r["memory"]["preferences"]["language"] == "he"


def test_disabled_harness_and_bad_input(backend):
    with pytest.raises(RuntimeError, match="off for the test"):
        backend.chat("sdk", "hello")
    with pytest.raises(ValueError):
        backend.chat("api", "   ")
    with pytest.raises(ValueError):
        backend.upload("api", "../../evil.txt", "x")


def test_upload_simulate_reset(backend):
    s = backend.upload("api", "mine.log", "2026-10-22T10:00:00 ERROR svc boom\n")
    assert "mine.log" in {l["file"] for l in s["logs"]}
    before = {l["file"]: l["lines"] for l in s["logs"]}["worker.log"]
    after = {l["file"]: l["lines"] for l in backend.simulate("api")["logs"]}["worker.log"]
    assert after > before
    s = backend.reset("api")
    assert "mine.log" not in {l["file"] for l in s["logs"]} and s["current"]["session"] == "s1"


def test_http_layer(backend):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(backend))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        html = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert "<title>LogSum</title>" in html
        state = json.loads(urllib.request.urlopen(base + "/api/state?harness=api").read())
        assert state["current"]["available"] is True
        req = urllib.request.Request(base + "/api/chat", data=json.dumps({"harness": "sdk", "message": "x"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 400
    finally:
        server.shutdown()
