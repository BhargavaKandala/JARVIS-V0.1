import pytest

from memory import store as _store


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point memory.store at a throwaway SQLite file for the duration of one test."""
    monkeypatch.setattr(_store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(_store, "_conn", None)

    yield _store

    if _store._conn is not None:
        _store._conn.close()
    _store._conn = None
