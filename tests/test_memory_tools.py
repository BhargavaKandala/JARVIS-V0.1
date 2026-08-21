from unittest.mock import MagicMock, patch

from skills import memory_tools as mt


def _mock_response(status_code=200, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def test_save_memory_sanitizes_a_path_separator_out_of_the_filename():
    """_url() leaves "/" unescaped (urllib.parse.quote's default safe set),
    so an unsanitized filename like "Journal/2026-08-22" would PUT-replace a
    whole day's accumulated captures instead of writing a new note. filename
    must be routed through vault.sanitize_entity_name, which maps "/" (and
    "\\") to "-", before ".md" is appended."""
    with patch.object(mt.vault, "put_note") as mock_put, \
         patch.object(mt.store, "add_memory", return_value=1), \
         patch.object(mt.vector_store, "index_memory"):
        mock_put.return_value = _mock_response(200)

        result = mt.save_memory.invoke({"filename": "Journal/2026-08-22", "content": "x"})

        called_path = mock_put.call_args.args[0]
        assert "/" not in called_path
        assert called_path == "Journal-2026-08-22.md"
        assert "Journal-2026-08-22.md" in result


def test_save_memory_sanitizes_traversal_segments():
    with patch.object(mt.vault, "put_note") as mock_put, \
         patch.object(mt.store, "add_memory", return_value=1), \
         patch.object(mt.vector_store, "index_memory"):
        mock_put.return_value = _mock_response(200)

        mt.save_memory.invoke({"filename": "../../Entities/Ravi", "content": "x"})

        called_path = mock_put.call_args.args[0]
        assert "/" not in called_path
        assert "\\" not in called_path


def test_save_memory_reports_failure_status_from_obsidian():
    with patch.object(mt.vault, "put_note") as mock_put, \
         patch.object(mt.store, "add_memory", return_value=1), \
         patch.object(mt.vector_store, "index_memory"):
        mock_put.return_value = _mock_response(500, "Internal Server Error")

        result = mt.save_memory.invoke({"filename": "notes", "content": "x"})

        assert "Failed to save" in result
