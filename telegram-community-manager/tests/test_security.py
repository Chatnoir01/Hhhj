import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import Settings
from app.main import app, health
from app.security import harden_session_file, redact_sensitive, require_admin, secure_session_path


def test_dry_run_is_safe_by_default():
    assert Settings(_env_file=None).dry_run is True


def test_redacts_otp_and_named_secrets():
    message = "code=123456 api_hash=abcdef password=hunter2 bot_token=123:abc"
    redacted = redact_sensitive(message)

    assert "123456" not in redacted
    assert "abcdef" not in redacted
    assert "hunter2" not in redacted
    assert "123:abc" not in redacted
    assert redacted.count("[REDACTED]") >= 4


def test_admin_guard_rejects_missing_and_wrong_credentials():
    settings = Settings(_env_file=None, admin_api_key="x" * 40)

    with pytest.raises(HTTPException) as missing:
        require_admin(credentials=None, settings=settings)
    assert missing.value.status_code == 401

    wrong = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
    with pytest.raises(HTTPException) as invalid:
        require_admin(credentials=wrong, settings=settings)
    assert invalid.value.status_code == 401


def test_admin_guard_accepts_correct_bearer():
    token = "x" * 40
    settings = Settings(_env_file=None, admin_api_key=token)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    assert require_admin(credentials=credentials, settings=settings) is None


def test_health_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_HASH", "super-secret-api-hash")
    monkeypatch.setenv("TELEGRAM_PHONE", "+32000000000")
    monkeypatch.setenv("ADMIN_API_KEY", "y" * 40)

    from app.config import get_settings

    get_settings.cache_clear()
    body = repr(health())

    assert "super-secret-api-hash" not in body
    assert "+32000000000" not in body
    assert "y" * 40 not in body

    get_settings.cache_clear()


def test_session_name_cannot_escape_directory(tmp_path):
    settings = Settings(_env_file=None, session_dir=tmp_path)

    with pytest.raises(ValueError):
        secure_session_path(settings, "../escape")


def test_session_permissions_are_private_on_posix(tmp_path):
    settings = Settings(_env_file=None, session_dir=tmp_path / "sessions")
    path = secure_session_path(settings, "telegram.session")
    path.write_text("dummy", encoding="utf-8")
    harden_session_file(path)

    if os.name == "posix":
        assert (settings.session_dir.stat().st_mode & 0o777) == 0o700
        assert (path.stat().st_mode & 0o777) == 0o600


def test_no_destructive_taskkill_in_application_source():
    root = Path(__file__).parents[1] / "app"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.glob("*.py")
    )

    assert "taskkill" not in source.lower()
    assert "subprocess.run" not in source


def test_localhost_bind_is_default():
    assert Settings(_env_file=None).bind_host == "127.0.0.1"


def test_no_permissive_cors_middleware():
    names = {middleware.cls.__name__ for middleware in app.user_middleware}
    assert "CORSMiddleware" not in names


def test_redacting_filter_scrubs_log_output(capfd):
    from app.logging_config import get_logger

    logger = get_logger("security-test-2")
    logger.warning("code=123456 password=secret api_hash=abcdef")
    captured = capfd.readouterr()

    assert "123456" not in captured.err
    assert "secret" not in captured.err
    assert "abcdef" not in captured.err
    assert "[REDACTED]" in captured.err
