import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.services.passwords import hash_password, verify_password
from app.services.storage import audio_url


def test_audio_url_joins_base_and_escapes_path(monkeypatch):
    monkeypatch.setattr(
        "app.services.storage.get_settings", lambda: Settings(audio_base_url="https://cdn.example.com/audio/")
    )
    assert audio_url("lessons/12/main track.mp3") == "https://cdn.example.com/audio/lessons/12/main%20track.mp3"
    assert audio_url(None) is None


def test_password_hashing_is_argon2id():
    hashed = hash_password("correct horse")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse")
    assert not verify_password(hashed, "wrong")
    assert not verify_password("not-a-hash", "correct horse")


def test_prod_refuses_default_secret_and_insecure_cookies():
    with pytest.raises(ValidationError):
        Settings(env="prod")
    with pytest.raises(ValidationError):
        Settings(env="prod", secret_key=SecretStr("x" * 40), cookie_secure=False)
    Settings(env="prod", secret_key=SecretStr("x" * 40), cookie_secure=True)
