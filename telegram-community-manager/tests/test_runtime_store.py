import pytest

from app import runtime_store


def test_runtime_store_encrypts_telegram_secrets(tmp_path, monkeypatch):
    store = tmp_path / "runtime_config.json"
    monkeypatch.setattr(runtime_store, "_STORE", store)
    runtime_store._SESSIONS.clear()

    runtime_store.initialize(
        password="very-strong-admin-password",
        telegram_api_id=123456,
        telegram_api_hash="0123456789abcdef0123456789abcdef",
        telegram_phone="+32000000000",
    )

    raw = store.read_text(encoding="utf-8")
    assert "0123456789abcdef0123456789abcdef" not in raw
    assert "+32000000000" not in raw

    token, cfg = runtime_store.login("very-strong-admin-password")
    assert token
    assert cfg.telegram_api_id == 123456
    assert cfg.telegram_api_hash == "0123456789abcdef0123456789abcdef"
    assert cfg.telegram_phone == "+32000000000"
    assert runtime_store.has_session(token)

    runtime_store.logout(token)
    assert not runtime_store.has_session(token)


def test_runtime_store_rejects_wrong_password(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_store, "_STORE", tmp_path / "runtime_config.json")
    runtime_store._SESSIONS.clear()

    runtime_store.initialize(
        password="very-strong-admin-password",
        telegram_api_id=123456,
        telegram_api_hash="0123456789abcdef0123456789abcdef",
        telegram_phone="+32000000000",
    )

    with pytest.raises(ValueError):
        runtime_store.login("totally-wrong-password")
