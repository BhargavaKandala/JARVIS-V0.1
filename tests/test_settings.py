from config import settings


def test_ollama_defaults_present():
    assert settings.OLLAMA_HOST == "http://127.0.0.1:11434"
    assert settings.HERMES_MODEL == "hermes3:8b"
    assert settings.EMBED_MODEL == "nomic-embed-text"


def test_auto_capture_defaults_on():
    assert settings.ENABLE_AUTO_CAPTURE is True


def test_ollama_num_gpu_defaults_to_zero():
    assert settings.OLLAMA_NUM_GPU == 0
