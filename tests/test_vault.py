from datetime import date, datetime
from unittest.mock import MagicMock, patch

from memory import vault


def _mock_response(status_code=200, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def test_daily_note_path_uses_journal_dir_and_iso_date():
    assert vault.daily_note_path(date(2026, 8, 8)) == "Journal/2026-08-08.md"


def test_sanitize_strips_obsidian_reserved_characters():
    assert vault.sanitize_entity_name("Auth [Refactor]") == "Auth Refactor"
    assert vault.sanitize_entity_name("api/v2") == "api-v2"
    assert vault.sanitize_entity_name("a:b|c#d^e") == "abcde"


def test_sanitize_collapses_whitespace_and_trims():
    assert vault.sanitize_entity_name("  Auth   Refactor  ") == "Auth Refactor"


def test_sanitize_strips_remaining_windows_illegal_characters():
    assert vault.sanitize_entity_name("What?") == "What"
    assert vault.sanitize_entity_name('"quoted"') == "quoted"
    assert vault.sanitize_entity_name("<tag>") == "tag"
    assert vault.sanitize_entity_name("a*b") == "ab"
    assert vault.sanitize_entity_name('<>:"/\\|?*') == "--"


def test_entity_note_path_uses_sanitized_name():
    assert vault.entity_note_path("Auth [Refactor]") == "Entities/Auth Refactor.md"


def test_format_capture_line_renders_time_kind_text_and_links():
    line = vault.format_capture_line(
        "commitment",
        "Finish the auth refactor by Tuesday",
        ["Auth Refactor"],
        when=datetime(2026, 8, 8, 14, 32),
    )
    assert line == "- 14:32 [commitment] Finish the auth refactor by Tuesday [[Auth Refactor]]"


def test_format_capture_line_with_no_entities_has_no_trailing_space():
    line = vault.format_capture_line(
        "fact", "Coffee is good", [], when=datetime(2026, 8, 8, 9, 5)
    )
    assert line == "- 09:05 [fact] Coffee is good"


def test_format_capture_line_links_every_entity():
    line = vault.format_capture_line(
        "idea", "Pair them up", ["Ravi", "Auth Refactor"], when=datetime(2026, 8, 8, 9, 5)
    )
    assert line.endswith("[[Ravi]] [[Auth Refactor]]")


def test_format_capture_line_flattens_newlines_in_text():
    line = vault.format_capture_line(
        "fact", "line one\nline two", [], when=datetime(2026, 8, 8, 9, 5)
    )
    assert line == "- 09:05 [fact] line one line two"


# --- REST verb regression tests ---------------------------------------------
#
# A PUT in append_daily_note would silently replace (destroy) a whole day's
# accumulated notes where POST appends. These tests pin the verb, and the
# path/URL each call targets, so that regression can't sneak back in.

def test_put_note_issues_a_put_to_the_correct_url():
    with patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_put.return_value = _mock_response(200)

        vault.put_note("Journal/2026-08-08.md", "content")

        mock_put.assert_called_once()
        mock_post.assert_not_called()
        called_url = mock_put.call_args.args[0]
        assert called_url == vault._url("Journal/2026-08-08.md")


def test_put_note_returns_the_response_for_diagnostics():
    with patch("memory.vault.requests.put") as mock_put:
        mock_put.return_value = _mock_response(500, "Internal Server Error")

        response = vault.put_note("x.md", "content")

        assert response.status_code == 500
        assert response.text == "Internal Server Error"


def test_append_daily_note_issues_a_post_not_a_put():
    with patch("memory.vault.requests.post") as mock_post, \
         patch("memory.vault.requests.put") as mock_put:
        mock_post.return_value = _mock_response(200)

        vault.append_daily_note("- 09:00 [fact] hi", when=date(2026, 8, 8))

        mock_post.assert_called_once()
        mock_put.assert_not_called()
        called_url = mock_post.call_args.args[0]
        assert called_url == vault._url("Journal/2026-08-08.md")


def test_ensure_entity_page_creates_via_put_and_never_posts_when_absent():
    with patch("memory.vault.requests.get") as mock_get, \
         patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_get.return_value = _mock_response(404)
        mock_put.return_value = _mock_response(201)

        vault.ensure_entity_page("Ravi", "person")

        mock_put.assert_called_once()
        mock_post.assert_not_called()
        called_url = mock_put.call_args.args[0]
        assert called_url == vault._url("Entities/Ravi.md")


def test_ensure_entity_page_is_a_noop_when_the_page_already_exists():
    with patch("memory.vault.requests.get") as mock_get, \
         patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_get.return_value = _mock_response(200, "already here")

        result = vault.ensure_entity_page("Ravi", "person")

        assert result is True
        mock_put.assert_not_called()
        mock_post.assert_not_called()


# --- note_exists / ensure_entity_page ambiguity handling --------------------
#
# get_note() collapses "confirmed absent" and "could not determine" into the
# same None, which made ensure_entity_page PUT-replace an existing note on a
# mere timeout. note_exists() keeps those two outcomes distinct (True/False/
# None), and ensure_entity_page must only ever create on a confirmed False.

def test_note_exists_true_on_200():
    with patch("memory.vault.requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, "content")
        assert vault.note_exists("Entities/Ravi.md") is True


def test_note_exists_false_on_404():
    with patch("memory.vault.requests.get") as mock_get:
        mock_get.return_value = _mock_response(404)
        assert vault.note_exists("Entities/Ravi.md") is False


def test_note_exists_none_on_exception():
    with patch("memory.vault.requests.get") as mock_get:
        mock_get.side_effect = TimeoutError("connection timed out")
        assert vault.note_exists("Entities/Ravi.md") is None


def test_note_exists_none_on_server_error():
    with patch("memory.vault.requests.get") as mock_get:
        mock_get.return_value = _mock_response(500, "Internal Server Error")
        assert vault.note_exists("Entities/Ravi.md") is None


def test_ensure_entity_page_does_not_put_on_timeout():
    """The critical regression case: a GET that merely times out against an
    existing page must NOT be treated as absent -- doing so would PUT-replace
    a note the user has been writing in with the 5-line stub."""
    with patch("memory.vault.requests.get") as mock_get, \
         patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_get.side_effect = TimeoutError("connection timed out")

        result = vault.ensure_entity_page("Ravi", "person")

        assert result is True
        mock_put.assert_not_called()
        mock_post.assert_not_called()


def test_ensure_entity_page_does_not_put_on_server_error():
    with patch("memory.vault.requests.get") as mock_get, \
         patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_get.return_value = _mock_response(500, "Internal Server Error")

        result = vault.ensure_entity_page("Ravi", "person")

        assert result is True
        mock_put.assert_not_called()
        mock_post.assert_not_called()
