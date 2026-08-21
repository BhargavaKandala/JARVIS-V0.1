from datetime import date, datetime

from memory import vault


def test_daily_note_path_uses_journal_dir_and_iso_date():
    assert vault.daily_note_path(date(2026, 8, 8)) == "Journal/2026-08-08.md"


def test_sanitize_strips_obsidian_reserved_characters():
    assert vault.sanitize_entity_name("Auth [Refactor]") == "Auth Refactor"
    assert vault.sanitize_entity_name("api/v2") == "api-v2"
    assert vault.sanitize_entity_name("a:b|c#d^e") == "abcde"


def test_sanitize_collapses_whitespace_and_trims():
    assert vault.sanitize_entity_name("  Auth   Refactor  ") == "Auth Refactor"


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
