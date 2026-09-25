from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import Settings, get_settings

_STORE = Path("data/runtime_config.json")
_SESSIONS: dict[str, bytes] = {}


@dataclass
class RuntimeTelegramConfig:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone: str
    telegram_bot_token: str | None = None


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**15,
        r=8,
        p=1,
        dklen=32,
    )


def is_configured() -> bool:
    return _STORE.exists()


def initialize(
    *,
    password: str,
    telegram_api_id: int,
    telegram_api_hash: str,
    telegram_phone: str,
    telegram_bot_token: str | None = None,
) -> None:
    if is_configured():
        raise RuntimeError("Runtime configuration already initialized")
    if len(password) < 12:
        raise ValueError("Admin password must contain at least 12 characters")
    if telegram_api_id <= 0 or not telegram_api_hash.strip() or not telegram_phone.strip():
        raise ValueError("Telegram API ID, API hash and phone are required")

    _STORE.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        _STORE.parent.chmod(0o700)

    salt = secrets.token_bytes(16)
    key = _derive(password, salt)
    nonce = secrets.token_bytes(12)
    payload = json.dumps(
        {
            "telegram_api_id": telegram_api_id,
            "telegram_api_hash": telegram_api_hash.strip(),
            "telegram_phone": telegram_phone.strip(),
            "telegram_bot_token": telegram_bot_token.strip() if telegram_bot_token else None,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, payload, b"telegram-community-manager")
    verifier = hmac.new(key, b"admin-verifier", hashlib.sha256).digest()

    _STORE.write_text(
        json.dumps(
            {
                "version": 1,
                "salt": _b64e(salt),
                "nonce": _b64e(nonce),
                "ciphertext": _b64e(ciphertext),
                "verifier": _b64e(verifier),
            }
        ),
        encoding="utf-8",
    )
    if os.name == "posix":
        _STORE.chmod(0o600)


def _unlock(password: str) -> tuple[bytes, RuntimeTelegramConfig]:
    if not is_configured():
        raise RuntimeError("Runtime configuration is not initialized")
    data = json.loads(_STORE.read_text(encoding="utf-8"))
    salt = _b64d(data["salt"])
    key = _derive(password, salt)
    verifier = hmac.new(key, b"admin-verifier", hashlib.sha256).digest()
    if not hmac.compare_digest(verifier, _b64d(data["verifier"])):
        raise ValueError("Invalid admin password")
    plaintext = AESGCM(key).decrypt(
        _b64d(data["nonce"]),
        _b64d(data["ciphertext"]),
        b"telegram-community-manager",
    )
    decoded: dict[str, Any] = json.loads(plaintext.decode("utf-8"))
    cfg = RuntimeTelegramConfig(
        telegram_api_id=int(decoded["telegram_api_id"]),
        telegram_api_hash=str(decoded["telegram_api_hash"]),
        telegram_phone=str(decoded["telegram_phone"]),
        telegram_bot_token=decoded.get("telegram_bot_token"),
    )
    return key, cfg


def login(password: str) -> tuple[str, RuntimeTelegramConfig]:
    key, cfg = _unlock(password)
    token = secrets.token_urlsafe(48)
    _SESSIONS[token] = key
    return token, cfg


def logout(token: str) -> None:
    _SESSIONS.pop(token, None)


def has_session(token: str) -> bool:
    return bool(token) and token in _SESSIONS


def runtime_config_for_token(token: str) -> RuntimeTelegramConfig:
    key = _SESSIONS.get(token)
    if key is None:
        raise ValueError("Invalid or expired admin session")
    data = json.loads(_STORE.read_text(encoding="utf-8"))
    plaintext = AESGCM(key).decrypt(
        _b64d(data["nonce"]),
        _b64d(data["ciphertext"]),
        b"telegram-community-manager",
    )
    decoded = json.loads(plaintext.decode("utf-8"))
    return RuntimeTelegramConfig(
        telegram_api_id=int(decoded["telegram_api_id"]),
        telegram_api_hash=str(decoded["telegram_api_hash"]),
        telegram_phone=str(decoded["telegram_phone"]),
        telegram_bot_token=decoded.get("telegram_bot_token"),
    )


def effective_settings(token: str | None = None) -> Settings:
    base = get_settings()
    if token and has_session(token):
        cfg = runtime_config_for_token(token)
        return base.model_copy(
            update={
                "telegram_api_id": cfg.telegram_api_id,
                "telegram_api_hash": cfg.telegram_api_hash,
                "telegram_phone": cfg.telegram_phone,
                "telegram_bot_token": cfg.telegram_bot_token,
            }
        )
    return base
