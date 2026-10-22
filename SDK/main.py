"""python SDK/main.py --scenario scenario.json --out results/sdk.json"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from SDK.agent import LogSumAgent  # noqa: E402
from shared import scenario as sc  # noqa: E402
from shared.workspace import Workspace  # noqa: E402
from tools.count_loc import sdk_loc  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/sdk.json")
    args = ap.parse_args()

    if os.environ.pop("ANTHROPIC_API_KEY", None):
        print("note: ANTHROPIC_API_KEY removed for this process so the SDK bills your Claude Code login")

    scenario = sc.load(args.scenario)
    ws = Workspace.fresh("sdk")  # every run starts from a clean state

    def make_agent(session_id: str) -> LogSumAgent:
        return LogSumAgent(ws, session_id, scenario["model"], scenario["effort"])

    sc.write(sc.run(scenario, ws, make_agent, "sdk", sdk_loc()), args.out)


if __name__ == "__main__":
    main()
