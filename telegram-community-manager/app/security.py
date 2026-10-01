import hmac
import logging
import os
import re
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_ -]?hash|bot[_ -]?token|password|2fa|otp|code)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"\b\d{5,8}\b"),
)


def redact_sensitive(value: object) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.getMessage())
        record.args = ()
        return True


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    candidate = (
        credentials.credentials
        if credentials and credentials.scheme.lower() == "bearer"
        else ""
    )

    static_ok = bool(
        settings.admin_api_key
        and candidate
        and hmac.compare_digest(candidate, settings.admin_api_key)
    )

    from .runtime_store import has_session, is_configured

    runtime_ok = has_session(candidate)

    if static_ok or runtime_ok:
        return None

    if not settings.admin_api_key and not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin setup is not initialized",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    require_admin(credentials=credentials, settings=settings)
    return credentials.credentials if credentials else ""


def secure_session_path(settings: Settings, session_name: str = "telegram") -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", session_name):
        raise ValueError("Invalid session name")

    directory = settings.session_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)

    if os.name == "posix":
        directory.chmod(0o700)

    return directory / session_name


def harden_session_file(path: Path) -> None:
    if path.exists() and os.name == "posix":
        path.chmod(0o600)
