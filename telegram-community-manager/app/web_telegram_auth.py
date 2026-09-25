from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient, errors

from .config import Settings
from .security import harden_session_file, secure_session_path


@dataclass
class _Flow:
    client: TelegramClient
    phone_code_hash: str


_FLOWS: dict[str, _Flow] = {}


async def _close_flow(token: str) -> None:
    flow = _FLOWS.pop(token, None)
    if flow and flow.client.is_connected():
        await flow.client.disconnect()


async def send_login_code(token: str, settings: Settings) -> dict:
    await _close_flow(token)

    session_path = secure_session_path(settings, "community-manager")
    client = TelegramClient(
        str(session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()

    if await client.is_user_authorized():
        harden_session_file(Path(f"{session_path}.session"))
        await client.disconnect()
        return {"ok": True, "already_authorized": True, "code_sent": False}

    sent = await client.send_code_request(settings.telegram_phone)
    _FLOWS[token] = _Flow(client=client, phone_code_hash=sent.phone_code_hash)
    return {"ok": True, "already_authorized": False, "code_sent": True}


async def verify_login_code(token: str, settings: Settings, code: str) -> dict:
    flow = _FLOWS.get(token)
    if not flow:
        return {"ok": False, "restart_required": True, "detail": "Request a new Telegram code"}

    try:
        await flow.client.sign_in(
            phone=settings.telegram_phone,
            code=code.strip(),
            phone_code_hash=flow.phone_code_hash,
        )
    except errors.SessionPasswordNeededError:
        return {"ok": True, "requires_2fa": True, "authorized": False}
    except errors.PhoneCodeInvalidError:
        return {"ok": False, "requires_2fa": False, "detail": "Invalid Telegram code"}
    except errors.PhoneCodeExpiredError:
        await _close_flow(token)
        return {"ok": False, "restart_required": True, "detail": "Telegram code expired"}

    path = secure_session_path(settings, "community-manager")
    harden_session_file(Path(f"{path}.session"))
    await _close_flow(token)
    return {"ok": True, "requires_2fa": False, "authorized": True}


async def verify_2fa_password(token: str, settings: Settings, password: str) -> dict:
    flow = _FLOWS.get(token)
    if not flow:
        return {"ok": False, "restart_required": True, "detail": "Request a new Telegram code"}

    try:
        await flow.client.sign_in(password=password)
    except errors.PasswordHashInvalidError:
        return {"ok": False, "detail": "Invalid Telegram 2FA password"}

    path = secure_session_path(settings, "community-manager")
    harden_session_file(Path(f"{path}.session"))
    await _close_flow(token)
    return {"ok": True, "authorized": True}


async def telegram_auth_status(settings: Settings) -> bool:
    session_path = secure_session_path(settings, "community-manager")
    client = TelegramClient(
        str(session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    try:
        await client.connect()
        return bool(await client.is_user_authorized())
    finally:
        await client.disconnect()
