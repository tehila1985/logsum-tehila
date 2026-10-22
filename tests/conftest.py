import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from shared.make_logs import make_logs  # noqa: E402
from shared.workspace import Workspace  # noqa: E402


@pytest.fixture
def ws(tmp_path) -> Workspace:
    w = Workspace(tmp_path)
    make_logs(w.logs_dir)
    w.history_dir.mkdir()
    return w
