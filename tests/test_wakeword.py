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
