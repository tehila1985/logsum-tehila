"""python API/main.py --scenario scenario.json --out results/api.json"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from API.agent import LogSumAgent  # noqa: E402
from shared import scenario as sc  # noqa: E402
from shared.workspace import Workspace  # noqa: E402
from tools.count_loc import api_loc  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/api.json")
    ap.add_argument("--compact-at", type=int, default=12_000, help="compact when a call's input exceeds this")
    ap.add_argument("--no-fallbacks", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Set it in this terminal only:  $env:ANTHROPIC_API_KEY=\"sk-ant-...\"")
    import anthropic

    scenario = sc.load(args.scenario)
    client = anthropic.Anthropic()
    ws = Workspace.fresh("api")  # every run starts from a clean state

    def make_agent(session_id: str) -> LogSumAgent:
        return LogSumAgent(client, ws, session_id, scenario["model"], scenario["effort"],
                           compact_at=args.compact_at, fallbacks=not args.no_fallbacks)

    sc.write(sc.run(scenario, ws, make_agent, "api", api_loc()), args.out)


if __name__ == "__main__":
    main()
