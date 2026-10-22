# LogSum: one log-summary agent, two harnesses

LogSum reads log files through tools, groups errors by signature and answers in a few lines. It remembers known issues, ignore patterns, preferences and past incidents between sessions.

- `API/`: the whole harness written by hand on the raw Messages API (`API/harness/`, one file per responsibility).
- `SDK/`: the same agent configured on the Claude Agent SDK. Every line that replaces a harness file is tagged `# replaces: <name>`.
- `shared/`: domain code used by both: tools, memory store, synthetic logs, scenario runner, checks.

The design is in [PLAN.md](PLAN.md) and the comparison is in [REPORT.md](REPORT.md).

## Setup

```powershell
pip install -r requirements.txt
```

## Chat UI

```powershell
python web/server.py          # then open http://localhost:8000
```

A local chat page that runs the real agent. Switch between the SDK and API harnesses in the header. The side panel shows memory changing after each answer and lists the log files. Buttons start a new session (a new agent instance that loads memory from disk), add new errors to `worker.log`, upload your own `.log` file, or reset everything. The server uses the standard library only. The API harness is enabled only if `ANTHROPIC_API_KEY` is set in the terminal before you start the server, and the server hides the key from the SDK so the SDK still bills your Claude Code login. State lives in `runs/web-api/` and `runs/web-sdk/` and persists across restarts. Use `--fresh` to start empty.

## Run

```powershell
# offline tests: no key, no network
python -m pytest tests -q

# API version: needs a key, set ONLY in this terminal (never in code or git)
$env:ANTHROPIC_API_KEY="sk-ant-..."
python API/main.py --scenario scenario.json --out results/api.json

# SDK version: runs on your Claude Code login. The key must NOT be set,
# otherwise billing goes to the key (main.py removes it from its own process).
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
python SDK/main.py --scenario scenario.json --out results/sdk.json

# tables for REPORT.md
python tools/report_tables.py
```

Every run starts from a clean state in `runs/<api|sdk>/`, with logs regenerated deterministically, an empty memory and no history.
