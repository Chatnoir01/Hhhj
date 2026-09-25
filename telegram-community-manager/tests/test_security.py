import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.security import harden_session_file, redact_sensitive, secure_session_path


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


def test_config_status_requires_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "x" * 40)
    get_settings.cache_clear()
    client = TestClient(app)

    assert client.get("/config/status").status_code == 401
    assert client.get(
        "/config/status",
        headers={"Authorization": "Bearer wrong"},
    ).status_code == 401

    response = client.get(
        "/config/status",
        headers={"Authorization": f"Bearer {'x' * 40}"},
    )
    assert response.status_code == 200
    get_settings.cache_clear()


def test_health_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_HASH", "super-secret-api-hash")
    monkeypatch.setenv("TELEGRAM_PHONE", "+32000000000")
    monkeypatch.setenv("ADMIN_API_KEY", "y" * 40)
    get_settings.cache_clear()

    body = TestClient(app).get("/health").text

    assert "super-secret-api-hash" not in body
    assert "+32000000000" not in body
    assert "y" * 40 not in body
    get_settings.cache_clear()


def test_session_name_cannot_escape_directory(tmp_path):
    settings = Settings(_env_file=None, session_dir=tmp_path)

    try:
        secure_session_path(settings, "../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal session name was accepted")


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

    logger = get_logger("security-test")
    logger.warning("code=123456 password=secret api_hash=abcdef")
    captured = capfd.readouterr()

    assert "123456" not in captured.err
    assert "secret" not in captured.err
    assert "abcdef" not in captured.err
    assert "[REDACTED]" in captured.err
