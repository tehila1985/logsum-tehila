"""A run's working state on disk: logs, memory, history. Fresh for every run."""
import shutil
from dataclasses import dataclass
from pathlib import Path

from shared.make_logs import PRE_STEPS, make_logs

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Workspace:
    root: Path

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def memory_path(self) -> Path:
        return self.root / "memory.json"

    @property
    def history_dir(self) -> Path:
        return self.root / "history"

    @classmethod
    def fresh(cls, name: str) -> "Workspace":
        ws = cls(ROOT / "runs" / name)
        if ws.root.exists():
            shutil.rmtree(ws.root)
        make_logs(ws.logs_dir)
        ws.history_dir.mkdir(parents=True)
        return ws

    def pre_step(self, step: str | None) -> None:
        if step:
            PRE_STEPS[step](self.logs_dir)
