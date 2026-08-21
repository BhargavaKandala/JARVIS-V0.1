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
