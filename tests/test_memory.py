import json

import pytest

from API.harness.memory import Memory
from shared.errors import ToolError
from shared.memory_store import MemoryStore


def test_upsert_overwrites_and_returns_old(ws):
    m = MemoryStore(ws.memory_path)
    assert m.upsert("preference", "language", "English") is None
    assert m.upsert("preference", "Language", "hebrew") == "en"
    assert m.data["preferences"] == {"language": "he"}


def test_persists_across_instances(ws):
    MemoryStore(ws.memory_path).upsert("known_issue", "DBTimeout", "nightly backup")
    again = MemoryStore(ws.memory_path)
    assert again.data["known_issues"]["DBTimeout"] == "nightly backup"
    assert json.loads(ws.memory_path.read_text(encoding="utf-8"))["known_issues"]


def test_forget_and_validation(ws):
    m = MemoryStore(ws.memory_path)
    m.upsert("ignore", "healthcheck", "health")
    m.delete("ignore", "healthcheck")
    assert m.data["ignore"] == {}
    with pytest.raises(ToolError):
        m.delete("ignore", "healthcheck")
    with pytest.raises(ToolError):
        m.upsert("preference", "color", "blue")
    with pytest.raises(ToolError):
        m.upsert("ignore", "bad", "([")


def test_search(ws):
    m = MemoryStore(ws.memory_path)
    m.upsert("incident", "2026-10-22-checkout", "40 x 5xx on /api/checkout at 14:10")
    m.upsert("known_issue", "DBTimeout", "backup")
    assert list(m.search("checkout")) == ["incident"]
    assert m.search(kind="known_issue") == {"known_issue": {"DBTimeout": "backup"}}


def test_relevant_injects_only_matching_entries(ws):
    mem = Memory(ws.memory_path)
    mem.store.upsert("preference", "format", "bullets")
    mem.store.upsert("known_issue", "DBTimeout", "nightly backup")
    mem.store.upsert("incident", "checkout-5xx", "40 errors on /api/checkout")
    block = mem.relevant("anything about checkout?")
    assert "format=bullets" in block
    assert "40 errors on /api/checkout" in block          # matched -> full text
    assert "nightly backup" not in block and "DBTimeout" in block  # not matched -> index only
