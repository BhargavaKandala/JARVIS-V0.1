from voice import wakeword


def test_detects_the_canonical_wake_word():
    assert wakeword.detect_wake_word("Jarvis what is the weather") is True


def test_detects_whisper_homophones():
    assert wakeword.detect_wake_word("Travis, open youtube") is True
    assert wakeword.detect_wake_word("garbage save a memory") is True
    assert wakeword.detect_wake_word("Jaress, what time is it") is True


def test_rejects_text_without_a_wake_word():
    assert wakeword.detect_wake_word("what is the weather") is False
    assert wakeword.detect_wake_word("") is False


def test_strips_the_wake_word_and_leading_punctuation():
    assert wakeword.strip_wake_word("Jarvis, what is the weather") == "what is the weather"
    assert wakeword.strip_wake_word("Travis open youtube") == "open youtube"


def test_strips_only_the_first_occurrence():
    assert wakeword.strip_wake_word("Jarvis tell Jarvis hello") == "tell Jarvis hello"


def test_strip_preserves_original_casing_of_the_remainder():
    assert wakeword.strip_wake_word("jarvis Open YouTube") == "Open YouTube"


def test_strip_is_a_noop_without_a_wake_word():
    assert wakeword.strip_wake_word("what is the weather") == "what is the weather"


def test_strip_of_the_bare_wake_word_returns_empty():
    assert wakeword.strip_wake_word("Jarvis") == ""


def test_ambiguous_wake_word_mid_sentence_does_not_detect_or_strip():
    text = "the garbage disposal is broken"
    assert wakeword.detect_wake_word(text) is False
    assert wakeword.strip_wake_word(text) == text


def test_ambiguous_wake_word_at_start_detects_and_strips():
    assert wakeword.detect_wake_word("Garbage, what's the weather?") is True
    assert wakeword.strip_wake_word("Garbage, what's the weather?") == "what's the weather?"


def test_leading_wake_word_strips_but_ambiguous_word_survives_later_in_text():
    text = "Jarvis, take out the garbage"
    assert wakeword.detect_wake_word(text) is True
    stripped = wakeword.strip_wake_word(text)
    assert stripped == "take out the garbage"
    assert "garbage" in stripped


def test_wake_word_genuinely_mid_sentence_strips_without_double_space():
    text = "please help jarvis with something"
    assert wakeword.detect_wake_word(text) is True
    assert wakeword.strip_wake_word(text) == "please help with something"


def test_no_wake_word_at_all_is_unchanged():
    text = "let's grab lunch later"
    assert wakeword.detect_wake_word(text) is False
    assert wakeword.strip_wake_word(text) == text


def test_none_and_empty_are_handled_without_raising():
    assert wakeword.strip_wake_word("") == ""
    assert wakeword.strip_wake_word(None) == ""
    assert wakeword.detect_wake_word(None) is False


def test_detect_and_strip_agree_when_detection_is_false():
    text = "the garbage disposal is broken"
    assert wakeword.detect_wake_word(text) is False
    assert wakeword.strip_wake_word(text) == text
