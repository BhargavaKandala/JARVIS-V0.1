def test_temp_db_starts_empty(temp_db):
    assert temp_db.list_memories() == []


def test_temp_db_accepts_writes(temp_db):
    memory_id = temp_db.add_memory(kind="semantic", content="hello")
    assert temp_db.get_memory(memory_id)["content"] == "hello"
