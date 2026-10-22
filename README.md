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
