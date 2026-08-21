import numpy as np

from memory import vector_store


def _stub_embedder(monkeypatch, mapping):
    """Make embed_text deterministic: exact text lookup, else a zero-ish default."""
    def fake(text):
        return np.array(mapping.get(text, [0.0, 0.0, 1.0]), dtype=np.float32)
    monkeypatch.setattr(vector_store, "embed_text", fake)


def test_search_returns_closest_match_first(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {
        "cats": [1.0, 0.0, 0.0],
        "kittens": [0.9, 0.1, 0.0],
        "trucks": [0.0, 1.0, 0.0],
    })
    cat_id = temp_db.add_memory(kind="semantic", content="cats")
    truck_id = temp_db.add_memory(kind="semantic", content="trucks")
    vector_store.index_memory(cat_id, "cats")
    vector_store.index_memory(truck_id, "trucks")

    results = vector_store.search("kittens", top_k=2)

    assert results[0]["id"] == cat_id


def test_search_ignores_rows_from_a_different_embedding_model(temp_db, monkeypatch):
    """A half-finished migration must degrade to fewer results, not crash."""
    _stub_embedder(monkeypatch, {"cats": [1.0, 0.0, 0.0]})
    memory_id = temp_db.add_memory(kind="semantic", content="cats")
    vector_store.index_memory(memory_id, "cats")

    conn = temp_db._get_conn()
    conn.execute("UPDATE embeddings SET model = ? WHERE memory_id = ?",
                 ("models/gemini-embedding-001", memory_id))
    conn.commit()

    assert vector_store.search("cats") == []


def test_search_on_empty_index_returns_empty_list(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {})
    assert vector_store.search("anything") == []


def test_index_memory_records_the_active_model_and_dim(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {"cats": [1.0, 0.0, 0.0]})
    memory_id = temp_db.add_memory(kind="semantic", content="cats")
    vector_store.index_memory(memory_id, "cats")

    row = temp_db._get_conn().execute(
        "SELECT model, dim FROM embeddings WHERE memory_id = ?", (memory_id,)
    ).fetchone()
    assert row["model"] == vector_store.EMBEDDING_MODEL
    assert row["dim"] == 3


def test_search_filters_by_kind(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {
        "cats": [1.0, 0.0, 0.0],
        "a decision": [0.99, 0.0, 0.0],
    })
    cat_id = temp_db.add_memory(kind="semantic", content="cats")
    dec_id = temp_db.add_memory(kind="decision", content="a decision")
    vector_store.index_memory(cat_id, "cats")
    vector_store.index_memory(dec_id, "a decision")

    results = vector_store.search("cats", kind="decision")

    assert [r["id"] for r in results] == [dec_id]


# --- scripts/reindex_embeddings.py migration safety ---
#
# These exercise the actual migration script (not a rewritten copy). No test
# hits Ollama: vector_store.embed_text (the only thing that would make a
# network call) is monkeypatched, and scripts.reindex_embeddings.index_memory
# resolves to vector_store.embed_text through the shared vector_store module,
# so patching it there is sufficient.

def _old_model_row(conn, memory_id, model="models/gemini-embedding-001"):
    """Simulate a pre-existing embedding written by the old (Gemini) embedder."""
    vector = np.array([1.0, 0.0, 0.0], dtype=np.float32).tobytes()
    conn.execute(
        "INSERT INTO embeddings (memory_id, vector, dim, model, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (memory_id, vector, 3, model, "2020-01-01T00:00:00"),
    )
    conn.commit()
    return vector


def test_reindex_survives_total_embedder_failure(temp_db, monkeypatch, capsys):
    """If every re-embed fails (e.g. Ollama is down), old rows must survive untouched."""
    from scripts import reindex_embeddings

    conn = temp_db._get_conn()
    memory_id = temp_db.add_memory(kind="semantic", content="cats")
    old_vector = _old_model_row(conn, memory_id)

    def always_fail(text):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(vector_store, "embed_text", always_fail)

    reindex_embeddings.main()

    row = conn.execute(
        "SELECT model, vector FROM embeddings WHERE memory_id = ?", (memory_id,)
    ).fetchone()
    assert row is not None
    assert row["model"] == "models/gemini-embedding-001"
    assert row["vector"] == old_vector

    out = capsys.readouterr().out
    assert "TOTAL FAILURE" in out
    assert "NOTHING WAS PURGED" in out


def test_reindex_purges_stale_rows_only_for_memories_reembedded_this_run(temp_db, monkeypatch, capsys):
    """Partial failure: the failed memory's old row survives; only the succeeded one is superseded."""
    from scripts import reindex_embeddings

    conn = temp_db._get_conn()
    stale_id = temp_db.add_memory(kind="semantic", content="cats")
    old_vector = _old_model_row(conn, stale_id)
    ok_id = temp_db.add_memory(kind="semantic", content="dogs")

    def flaky(text):
        if text == "cats":
            raise RuntimeError("connection refused")
        return np.array([0.0, 1.0, 0.0], dtype=np.float32)
    monkeypatch.setattr(vector_store, "embed_text", flaky)

    reindex_embeddings.main()

    stale_row = conn.execute(
        "SELECT model, vector FROM embeddings WHERE memory_id = ?", (stale_id,)
    ).fetchone()
    assert stale_row["model"] == "models/gemini-embedding-001"
    assert stale_row["vector"] == old_vector

    ok_row = conn.execute(
        "SELECT model FROM embeddings WHERE memory_id = ?", (ok_id,)
    ).fetchone()
    assert ok_row["model"] == vector_store.EMBEDDING_MODEL

    out = capsys.readouterr().out
    assert "PARTIAL FAILURE" in out


def test_reindex_full_success_purges_all_stale_rows(temp_db, monkeypatch, capsys):
    """No failures: old-model row is fully replaced and the run reports a clean summary."""
    from scripts import reindex_embeddings

    conn = temp_db._get_conn()
    memory_id = temp_db.add_memory(kind="semantic", content="cats")
    _old_model_row(conn, memory_id)

    monkeypatch.setattr(
        vector_store, "embed_text",
        lambda text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    )

    reindex_embeddings.main()

    row = conn.execute(
        "SELECT model FROM embeddings WHERE memory_id = ?", (memory_id,)
    ).fetchone()
    assert row["model"] == vector_store.EMBEDDING_MODEL

    count = conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()["n"]
    assert count == 1  # no leftover old-model row for this memory

    out = capsys.readouterr().out
    assert "1 re-embedded, 0 failed" in out
    assert "FAILURE" not in out


def test_reindex_backup_filename_does_not_collide_on_repeated_same_day_runs(temp_db, monkeypatch):
    """A second run today must not overwrite the first run's pre-migration snapshot."""
    import glob

    from scripts import reindex_embeddings

    temp_db.add_memory(kind="semantic", content="cats")
    monkeypatch.setattr(
        vector_store, "embed_text",
        lambda text: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    )

    reindex_embeddings.main()
    first_backups = set(glob.glob(f"{temp_db.DB_PATH}.bak-*"))
    assert len(first_backups) == 1

    reindex_embeddings.main()
    second_backups = set(glob.glob(f"{temp_db.DB_PATH}.bak-*"))

    assert len(second_backups) == 2
    assert first_backups.issubset(second_backups)
