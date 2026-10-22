"""Deterministic synthetic logs for the scenario.

Every line has the same shape:  <ISO timestamp> <LEVEL> <service> <message>
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

DAY = datetime(2026, 10, 22)


def _ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def _app(rng: random.Random) -> list[tuple[datetime, str]]:
    out = []
    t = DAY + timedelta(hours=8)
    while t < DAY + timedelta(hours=20):
        out.append((t, f"INFO OrderService Order {rng.randint(10000, 99999)} created"))
        t += timedelta(seconds=rng.randint(20, 90))
    for i in range(12):
        t = DAY + timedelta(hours=11, minutes=5 * i, seconds=rng.randint(0, 59))
        out.append((t, f"ERROR OrderService NullPointerException in OrderService.applyDiscount (order={rng.randint(10000, 99999)})"))
    for i in range(5):
        t = DAY + timedelta(hours=16, minutes=3 * i, seconds=rng.randint(0, 59))
        out.append((t, f"ERROR PaymentClient PaymentGateway returned 502 after {rng.randint(800, 3000)}ms"))
    for i in range(3):
        t = DAY + timedelta(hours=9 + i, minutes=rng.randint(0, 59))
        out.append((t, "WARN OrderService Slow query on orders table"))
    return out


def _nginx(rng: random.Random) -> list[tuple[datetime, str]]:
    out = []
    paths = ["/api/products", "/api/cart", "/api/users/me", "/static/app.js"]
    t = DAY + timedelta(hours=8)
    while t < DAY + timedelta(hours=20):
        out.append((t, f"INFO nginx GET {rng.choice(paths)} 200 {rng.randint(5, 120)}ms"))
        t += timedelta(seconds=rng.randint(5, 40))
    for i in range(40):
        t = DAY + timedelta(hours=14, minutes=10, seconds=i * 20 + rng.randint(0, 9))
        code = rng.choice([502, 503, 504])
        out.append((t, f"ERROR nginx POST /api/checkout {code} {rng.randint(1000, 30000)}ms"))
    for i in range(6):
        t = DAY + timedelta(hours=rng.randint(8, 19), minutes=rng.randint(0, 59))
        out.append((t, f"WARN nginx GET /api/users/{rng.randint(1, 999)} 404 {rng.randint(2, 9)}ms"))
    return out


def _worker(rng: random.Random) -> list[tuple[datetime, str]]:
    out = []
    t = DAY
    while t < DAY + timedelta(hours=20):
        out.append((t, f"INFO worker GET /health 200 {rng.randint(1, 4)}ms"))
        t += timedelta(minutes=2)
    for i in range(30):
        t = DAY + timedelta(hours=2, minutes=i, seconds=rng.randint(0, 59))
        out.append((t, f"ERROR worker DBTimeout: connection pool exhausted after 30000ms (job={rng.randint(1000, 9999)})"))
    for i in range(8):
        t = DAY + timedelta(hours=rng.randint(6, 19), minutes=rng.randint(0, 59))
        out.append((t, "WARN worker healthcheck failed: upstream timeout"))
    t = DAY + timedelta(hours=3)
    while t < DAY + timedelta(hours=20):
        out.append((t, f"INFO worker Job {rng.randint(1000, 9999)} completed in {rng.randint(100, 900)}ms"))
        t += timedelta(minutes=rng.randint(5, 15))
    return out


def _write(path: Path, rows: list[tuple[datetime, str]], mode: str = "w") -> None:
    rows.sort(key=lambda r: r[0])
    with path.open(mode, encoding="utf-8", newline="\n") as f:
        for t, msg in rows:
            f.write(f"{_ts(t)} {msg}\n")


def make_logs(log_dir: Path, seed: int = 42) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    _write(log_dir / "app.log", _app(rng))
    _write(log_dir / "nginx.log", _nginx(rng))
    _write(log_dir / "worker.log", _worker(rng))


def append_new_errors_to_worker_log(log_dir: Path, seed: int = 7) -> None:
    """Between sessions: the next day brings a new error (S3) and the known one again."""
    rng = random.Random(seed)
    nxt = DAY + timedelta(days=1)
    rows = []
    for i in range(20):
        rows.append((nxt + timedelta(minutes=i * 3), f"INFO worker GET /health 200 {rng.randint(1, 4)}ms"))
    for i in range(10):
        rows.append((nxt + timedelta(hours=2, minutes=i * 2), f"ERROR worker DBTimeout: connection pool exhausted after 30000ms (job={rng.randint(1000, 9999)})"))
    for i in range(6):
        rows.append((nxt + timedelta(hours=9, minutes=i * 4), f"ERROR worker S3 AccessDenied: PutObject bucket=reports-prod key=daily/{rng.randint(100, 999)}.csv"))
    for i in range(3):
        rows.append((nxt + timedelta(hours=10, minutes=i * 7), "WARN worker healthcheck failed: upstream timeout"))
    _write(log_dir / "worker.log", rows, mode="a")


PRE_STEPS = {"append_new_errors_to_worker_log": append_new_errors_to_worker_log}
