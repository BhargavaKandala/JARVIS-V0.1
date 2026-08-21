"""One-shot migration: re-embed every memory with the active local model.

gemini-embedding-001 produced 3072-dim vectors; nomic-embed-text produces 768.
Mixing dimensions in one table breaks cosine search, so every row is rewritten.

Safe to re-run: the purge of old-model rows is scoped to only the memories
that were *successfully* re-embedded in this run. If the embedder is down
(e.g. Ollama not running) and every row fails, nothing is deleted and the
script can simply be re-run once the embedder is back. If only some rows
fail, the surviving old-model rows for those specific memories are left in
place rather than destroyed, and re-running finishes the job.
"""
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory import store, vector_store  # noqa: E402


def main():
    conn = store._get_conn()

    # Timestamped (not just dated) so a second run on the same day can never
    # overwrite the pre-migration snapshot from an earlier run today. Taken
    # before any mutation.
    backup = f"{store.DB_PATH}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    shutil.copyfile(store.DB_PATH, backup)
    print(f"[*] Backed up database to {backup}")

    rows = conn.execute("SELECT id, content FROM memories ORDER BY id").fetchall()
    print(f"[*] Re-embedding {len(rows)} memories with {vector_store.EMBEDDING_MODEL}...")

    succeeded_ids = []
    failed = 0
    for row in rows:
        try:
            vector_store.index_memory(row["id"], row["content"])
            succeeded_ids.append(row["id"])
        except Exception as e:
            failed += 1
            print(f"    ! memory {row['id']} failed: {e}")

    done = len(succeeded_ids)

    # Only purge stale (non-active-model) rows for memories this run actually
    # replaced. Memories that failed to re-embed keep whatever embedding they
    # had before -- including a total-failure run, which purges nothing.
    if succeeded_ids:
        placeholders = ", ".join("?" for _ in succeeded_ids)
        conn.execute(
            f"DELETE FROM embeddings WHERE model != ? AND memory_id IN ({placeholders})",
            (vector_store.EMBEDDING_MODEL, *succeeded_ids),
        )
        conn.commit()

    if failed and done == 0:
        print(
            f"[!] TOTAL FAILURE: 0 of {len(rows)} memories were re-embedded "
            f"({failed} failed, e.g. Ollama unreachable). NOTHING WAS "
            "PURGED -- all pre-existing embeddings are untouched. Fix the "
            "embedder and re-run this script; it is safe to re-run."
        )
    elif failed:
        print(
            f"[!] PARTIAL FAILURE: {done} re-embedded, {failed} failed. Stale "
            f"rows were purged ONLY for the {done} memories that were "
            f"successfully re-embedded this run. The {failed} memories that "
            "failed still have their OLD embedding in place (not purged, "
            "not replaced -- semantic search for those rows may be stale or "
            "absent). Fix the embedder and re-run this script to finish the "
            "job; it is safe to re-run."
        )
    else:
        print(f"[*] Done. {done} re-embedded, 0 failed, stale rows purged.")


if __name__ == "__main__":
    main()
