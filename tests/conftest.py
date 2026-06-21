"""conftest.py - put src/ on sys.path (flat sibling imports) and isolate state.

The CLI runs with sys.path[0]=src; mirror that for tests. Each store-backed
test gets its own DB under tmp_path so cases never share watches.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import paths
    import store
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB", tmp_path / "watches.db")
    c = store.connect()
    store.init_db(c)
    yield c
    c.close()
