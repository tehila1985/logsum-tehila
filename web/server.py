"""Chat UI for LogSum: a local web server that runs the real agent (API or SDK harness).

    python web/server.py            # http://localhost:8000
    python web/server.py --port 9000 --fresh

Standard library only. The SDK harness runs on your Claude Code login. The API harness
is enabled only when ANTHROPIC_API_KEY is set in the terminal that starts the server.
"""
import argparse
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.make_logs import append_new_errors_to_worker_log  # noqa: E402
from shared.memory_store import MemoryStore  # noqa: E402
from shared.workspace import Workspace  # noqa: E402

MODEL, EFFORT = "claude-opus-5-5", "medium"
INDEX = Path(__file__).with_name("index.html")
LOG_NAME = re.compile(r"^[\w.-]{1,60}\.log$")
MAX_UPLOAD = 2_000_000


class Harness:
    """One harness (api or sdk): its own workspace, its current agent instance, one turn at a time."""

    def __init__(self, name: str, factory, available: bool, reason: str = "", root: Path | None = None):
        self.name, self.factory = name, factory
        self.available, self.reason = available, reason
        self.root = root or ROOT / "runs" / f"web-{name}"
        self.ws = Workspace.ensure(self.root)
        self.lock = threading.Lock()
        self.session_n = len(list(self.ws.history_dir.glob("*.jsonl"))) + 1
        self.agent = None

    @property
    def session_id(self) -> str:
        return f"s{self.session_n}"

    def new_session(self) -> None:
        with self.lock:
            self.session_n += 1
            self.agent = None  # a new instance is created on the next message; memory comes from disk

    def reset(self) -> None:
        with self.lock:
            shutil.rmtree(self.root, ignore_errors=True)
            self.ws = Workspace.ensure(self.root)
            self.session_n, self.agent = 1, None

    def turn(self, text: str) -> dict:
        if not self.available:
            raise RuntimeError(self.reason)
        with self.lock:
            if self.agent is None:
                self.agent = self.factory(self.ws, self.session_id)
            start = time.perf_counter()
            r = self.agent.turn(text)
            r["seconds"] = round(time.perf_counter() - start, 2)
            r["session"] = self.session_id
            return r

    def memory(self) -> dict:
        return MemoryStore(self.ws.memory_path).data

    def logs(self) -> list[dict]:
        out = []
        for p in sorted(self.ws.logs_dir.glob("*.log")):
            with p.open(encoding="utf-8", errors="replace") as f:
                out.append({"file": p.name, "lines": sum(1 for _ in f), "kb": round(p.stat().st_size / 1024, 1)})
        return out

    def info(self) -> dict:
        return {"name": self.name, "available": self.available, "reason": self.reason, "session": self.session_id}


def build_harnesses() -> dict[str, Harness]:
    key = os.environ.pop("ANTHROPIC_API_KEY", None)  # the SDK subprocess must not see it (billing)
    harnesses = {}

    try:
        from SDK.agent import LogSumAgent as SDKAgent
        harnesses["sdk"] = Harness("sdk", lambda ws, sid: SDKAgent(ws, sid, MODEL, EFFORT), True)
    except Exception as e:  # claude-agent-sdk missing
        harnesses["sdk"] = Harness("sdk", None, False, f"claude-agent-sdk is not available: {e}")

    if key:
        import anthropic

        from API.agent import LogSumAgent as APIAgent
        client = anthropic.Anthropic(api_key=key)
        harnesses["api"] = Harness("api", lambda ws, sid: APIAgent(client, ws, sid, MODEL, EFFORT), True)
    else:
        harnesses["api"] = Harness("api", None, False,
                                   'ANTHROPIC_API_KEY is not set. Start the server after: $env:ANTHROPIC_API_KEY="sk-ant-..."')
    return harnesses


class Backend:
    """Everything the HTTP layer calls; kept separate so tests can drive it without a socket."""

    def __init__(self, harnesses: dict[str, Harness]):
        self.h = harnesses

    def _get(self, name: str) -> Harness:
        if name not in self.h:
            raise ValueError(f"unknown harness '{name}'")
        return self.h[name]

    def state(self, name: str) -> dict:
        h = self._get(name)
        return {"harnesses": [x.info() for x in self.h.values()], "current": h.info(),
                "memory": h.memory(), "logs": h.logs(), "model": MODEL, "effort": EFFORT}

    def chat(self, name: str, message: str) -> dict:
        message = (message or "").strip()
        if not message:
            raise ValueError("empty message")
        h = self._get(name)
        r = h.turn(message[:4000])
        return {"turn": {k: r[k] for k in ("response", "tool_calls", "input", "cache_read", "cache_write",
                                           "output", "model_calls", "cost_usd", "seconds", "session")},
                **self.state(name)}

    def new_session(self, name: str) -> dict:
        self._get(name).new_session()
        return self.state(name)

    def reset(self, name: str) -> dict:
        self._get(name).reset()
        return self.state(name)

    def simulate(self, name: str) -> dict:
        h = self._get(name)
        append_new_errors_to_worker_log(h.ws.logs_dir)
        return self.state(name)

    def upload(self, name: str, filename: str, content: str) -> dict:
        h = self._get(name)
        filename = Path(filename or "").name
        if not LOG_NAME.match(filename):
            raise ValueError("file name must end with .log and use letters, digits, '.', '-' or '_'")
        if len(content.encode("utf-8")) > MAX_UPLOAD:
            raise ValueError("file is larger than 2 MB")
        (h.ws.logs_dir / filename).write_text(content.replace("\r\n", "\n"), encoding="utf-8")
        return self.state(name)


def make_handler(backend: Backend):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, fmt, *args):  # keep the console for the harness trace
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            if self.path.startswith("/api/state"):
                name = self.path.partition("harness=")[2] or "sdk"
                return self._call(lambda: backend.state(name))
            self._json(404, {"error": "not found"})

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "invalid JSON"})
            name = body.get("harness", "sdk")
            routes = {
                "/api/chat": lambda: backend.chat(name, body.get("message", "")),
                "/api/new-session": lambda: backend.new_session(name),
                "/api/reset": lambda: backend.reset(name),
                "/api/simulate": lambda: backend.simulate(name),
                "/api/upload": lambda: backend.upload(name, body.get("filename", ""), body.get("content", "")),
            }
            if self.path not in routes:
                return self._json(404, {"error": "not found"})
            self._call(routes[self.path])

        def _call(self, fn):
            try:
                self._json(200, fn())
            except (ValueError, RuntimeError) as e:
                self._json(400, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                self._json(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--fresh", action="store_true", help="start with empty memory, history and fresh logs")
    args = ap.parse_args()
    if args.fresh:
        for name in ("web-api", "web-sdk"):
            shutil.rmtree(ROOT / "runs" / name, ignore_errors=True)

    harnesses = build_harnesses()
    for h in harnesses.values():
        print(f"  {h.name}: {'ready' if h.available else 'off - ' + h.reason}")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Backend(harnesses)))
    print(f"\nLogSum UI: http://localhost:{args.port}   (Ctrl+C to stop)\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
