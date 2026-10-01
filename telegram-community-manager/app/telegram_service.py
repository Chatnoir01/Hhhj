from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from telethon import TelegramClient, errors, functions
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from .config import Settings
from .security import harden_session_file, secure_session_path


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthState:
    status: str


@dataclass(frozen=True)
class InviteResult:
    status: str
    username: str
    wait_seconds: int | None = None
    detail: str | None = None


class TelegramService:
    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., TelegramClient] = TelegramClient,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory
        self.client: TelegramClient | None = None
        self._session_base: Path | None = None

    def _validate_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "TELEGRAM_API_ID": self.settings.telegram_api_id,
                "TELEGRAM_API_HASH": self.settings.telegram_api_hash,
                "TELEGRAM_PHONE": self.settings.telegram_phone,
            }.items()
            if value in (None, "")
        ]
        if missing:
            raise TelegramConfigurationError(
                "Missing Telegram configuration: " + ", ".join(missing)
            )

    def _harden_session(self) -> None:
        if self._session_base is None:
            return
        harden_session_file(Path(f"{self._session_base}.session"))

    async def start_login(self) -> AuthState:
        self._validate_credentials()
        self._session_base = secure_session_path(self.settings, "telegram")

        self.client = self.client_factory(
            str(self._session_base),
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )
        await self.client.connect()
        self._harden_session()

        if await self.client.is_user_authorized():
            return AuthState("authorized")

        await self.client.send_code_request(self.settings.telegram_phone)
        return AuthState("code_required")

    async def submit_code(self, code: str) -> AuthState:
        if self.client is None:
            raise TelegramAuthError("login_not_started")
        if not code or not code.strip():
            raise TelegramAuthError("code_required")

        try:
            await self.client.sign_in(
                phone=self.settings.telegram_phone,
                code=code.strip(),
            )
        except SessionPasswordNeededError:
            return AuthState("password_required")
        except (PhoneCodeInvalidError, PhoneCodeExpiredError) as exc:
            raise TelegramAuthError("invalid_or_expired_code") from exc

        self._harden_session()
        return AuthState("authorized")

    async def submit_password(self, password: str) -> AuthState:
        if self.client is None:
            raise TelegramAuthError("login_not_started")
        if not password:
            raise TelegramAuthError("password_required")

        await self.client.sign_in(password=password)
        self._harden_session()
        return AuthState("authorized")

    async def disconnect(self) -> None:
        if self.client is not None:
            await self.client.disconnect()

    async def resolve_username(self, username: str):
        if self.client is None:
            raise TelegramAuthError("not_connected")

        normalized = username.strip().lstrip("@").lower()
        if not normalized:
            raise ValueError("username_required")

        return await self.client.get_entity(normalized)

    async def resolve_target(self):
        if self.client is None:
            raise TelegramAuthError("not_connected")
        if not self.settings.target_group:
            raise TelegramConfigurationError("TARGET_GROUP is required")

        return await self.client.get_entity(self.settings.target_group)

    async def is_member(self, target, user) -> bool:
        if self.client is None:
            raise TelegramAuthError("not_connected")

        try:
            await self.client(
                functions.channels.GetParticipantRequest(
                    channel=target,
                    participant=user,
                )
            )
            return True
        except errors.UserNotParticipantError:
            return False

    async def invite_username(self, username: str) -> InviteResult:
        user = await self.resolve_username(username)
        target = await self.resolve_target()
        normalized = username.strip().lstrip("@").lower()

        if await self.is_member(target, user):
            return InviteResult("already_member", normalized)

        if self.settings.dry_run:
            return InviteResult("would_invite", normalized)

        try:
            await self.client(
                functions.channels.InviteToChannelRequest(
                    channel=target,
                    users=[user],
                )
            )
            return InviteResult("invited", normalized)
        except errors.UserAlreadyParticipantError:
            return InviteResult("already_member", normalized)
        except errors.UserPrivacyRestrictedError:
            return InviteResult("privacy_restricted", normalized)
        except errors.UserNotMutualContactError:
            return InviteResult("not_mutual_contact", normalized)
        except errors.UserChannelsTooMuchError:
            return InviteResult("too_many_channels", normalized)
        except errors.ChatAdminRequiredError:
            return InviteResult("admin_required", normalized)
        except errors.PeerFloodError:
            return InviteResult("peer_flood", normalized)
        except errors.FloodWaitError as exc:
            return InviteResult(
                "flood_wait",
                normalized,
                wait_seconds=int(exc.seconds),
            )
