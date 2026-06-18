WAKE_WORD = "hey jarvis"

def detect_wake_word(text: str) -> bool:
    return WAKE_WORD in text.lower()