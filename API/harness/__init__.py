from pathlib import Path


def trace(file: str, msg: str) -> None:
    """Every runtime action is printed with the harness file that performed it."""
    print(f"[{Path(file).name}] {msg}", flush=True)
