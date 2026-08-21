"""One-shot migration: re-embed every memory with the active local model.

gemini-embedding-001 produced 3072-dim vectors; nomic-embed-text produces 768.
Mixing dimensions in one table breaks cosine search, so every row is rewritten.
Safe to re-run.
"""
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory import store, vector_store  # noqa: E402


def main():
    conn = store._get_conn()

    backup = f"{store.DB_PATH}.bak-{date.today().strftime('%Y%m%d')}"
    shutil.copyfile(store.DB_PATH, backup)
    print(f"[*] Backed up database to {backup}")

    rows = conn.execute("SELECT id, content FROM memories ORDER BY id").fetchall()
    print(f"[*] Re-embedding {len(rows)} memories with {vector_store.EMBEDDING_MODEL}...")

    done, failed = 0, 0
    for row in rows:
        try:
            vector_store.index_memory(row["id"], row["content"])
            done += 1
        except Exception as e:
            failed += 1
            print(f"    ! memory {row['id']} failed: {e}")

    conn.execute("DELETE FROM embeddings WHERE model != ?", (vector_store.EMBEDDING_MODEL,))
    conn.commit()

    print(f"[*] Done. {done} re-embedded, {failed} failed, stale rows purged.")


if __name__ == "__main__":
    main()
