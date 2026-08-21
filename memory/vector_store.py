import numpy as np
from datetime import datetime
from langchain_ollama import OllamaEmbeddings
from config.settings import EMBED_MODEL, OLLAMA_HOST, OLLAMA_NUM_GPU
from memory import store

EMBEDDING_MODEL = EMBED_MODEL

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_HOST, num_gpu=OLLAMA_NUM_GPU)
    return _embedder


def embed_text(text: str) -> np.ndarray:
    vector = _get_embedder().embed_query(text)
    return np.array(vector, dtype=np.float32)


def index_memory(memory_id: int, text: str) -> None:
    vector = embed_text(text)
    conn = store._get_conn()
    conn.execute(
        "INSERT INTO embeddings (memory_id, vector, dim, model, created_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(memory_id) DO UPDATE SET vector = excluded.vector, dim = excluded.dim, "
        "model = excluded.model, created_at = excluded.created_at",
        (memory_id, vector.tobytes(), len(vector), EMBEDDING_MODEL, datetime.now().isoformat()),
    )
    conn.commit()


def search(query: str, top_k: int = 5, kind: str = None) -> list:
    conn = store._get_conn()
    rows = conn.execute(
        "SELECT e.memory_id, e.vector, e.dim FROM embeddings e WHERE e.model = ?",
        (EMBEDDING_MODEL,),
    ).fetchall()
    if not rows:
        return []

    query_vec = embed_text(query)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    scored = []
    for row in rows:
        candidate = np.frombuffer(row["vector"], dtype=np.float32)
        candidate_norm = np.linalg.norm(candidate)
        if candidate_norm == 0:
            continue
        similarity = float(np.dot(query_vec, candidate) / (query_norm * candidate_norm))
        scored.append((similarity, row["memory_id"]))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for similarity, memory_id in scored:
        memory = store.get_memory(memory_id)
        if memory is None:
            continue
        if kind and memory["kind"] != kind:
            continue
        memory["similarity"] = similarity
        results.append(memory)
        if len(results) >= top_k:
            break
    return results
