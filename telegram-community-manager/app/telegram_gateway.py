from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telethon import TelegramClient, errors, functions
from telethon.tl.types import Channel, Chat, InputPeerUser, User

from .config import Settings
from .security import harden_session_file, secure_session_path


@dataclass
class ResolvedUser:
    user_id: int
    access_hash: int
    username: str
    is_bot: bool = False
    deleted: bool = False


@dataclass
class PreflightResult:
    ok: bool
    target_title: str | None
    can_invite: bool
    detail: str


@dataclass
class InviteResult:
    status: str
    detail: str | None = None
    retry_after: datetime | None = None


class TelegramGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session_path = secure_session_path(settings, "community-manager")
        self.client = TelegramClient(
            str(self.session_path),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        self.target = None
        self._chat_participant_ids: set[int] | None = None

    async def connect_authorized(self) -> bool:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            return False
        harden_session_file(Path(f"{self.session_path}.session"))
        return True

    async def close(self) -> None:
        if self.client.is_connected():
            await self.client.disconnect()

    async def preflight(self, target_group: str) -> PreflightResult:
        try:
            self.target = await self.client.get_entity(target_group)
            title = getattr(self.target, "title", str(target_group))
            can_invite = True
            detail = "target resolved"
            if isinstance(self.target, Channel):
                try:
                    me = await self.client.get_me()
                    permissions = await self.client.get_permissions(self.target, me)
                    can_invite = bool(
                        getattr(permissions, "is_creator", False)
                        or getattr(permissions, "invite_users", False)
                    )
                    detail = (
                        "admin invite permission verified"
                        if can_invite
                        else "missing invite_users permission"
                    )
                except errors.RPCError as exc:
                    can_invite = False
                    detail = f"permission check failed: {type(exc).__name__}"
            return PreflightResult(can_invite, title, can_invite, detail)
        except errors.RPCError as exc:
            return PreflightResult(
                False,
                None,
                False,
                f"target resolution failed: {type(exc).__name__}",
            )

    async def resolve_username(self, username: str) -> ResolvedUser | None:
        try:
            entity = await self.client.get_entity(username)
        except (errors.UsernameInvalidError, errors.UsernameNotOccupiedError, ValueError):
            return None
        if not isinstance(entity, User) or not entity.access_hash:
            return None
        return ResolvedUser(
            user_id=int(entity.id),
            access_hash=int(entity.access_hash),
            username=(entity.username or username).lower(),
            is_bot=bool(entity.bot),
            deleted=bool(entity.deleted),
        )

    async def is_member(self, user: ResolvedUser) -> bool:
        if self.target is None:
            raise RuntimeError("preflight must run before membership checks")
        if isinstance(self.target, Channel):
            try:
                await self.client(
                    functions.channels.GetParticipantRequest(
                        channel=self.target,
                        participant=InputPeerUser(user.user_id, user.access_hash),
                    )
                )
                return True
            except errors.UserNotParticipantError:
                return False
        if isinstance(self.target, Chat):
            if self._chat_participant_ids is None:
                participants = await self.client.get_participants(self.target)
                self._chat_participant_ids = {int(member.id) for member in participants}
            return user.user_id in self._chat_participant_ids
        return False

    async def invite(self, user: ResolvedUser) -> InviteResult:
        if self.target is None:
            raise RuntimeError("preflight must run before invite")
        peer = InputPeerUser(user.user_id, user.access_hash)
        try:
            if isinstance(self.target, Channel):
                await self.client(
                    functions.channels.InviteToChannelRequest(
                        channel=self.target,
                        users=[peer],
                    )
                )
            elif isinstance(self.target, Chat):
                await self.client(
                    functions.messages.AddChatUserRequest(
                        chat_id=self.target.id,
                        user_id=peer,
                        fwd_limit=0,
                    )
                )
            else:
                return InviteResult("FAILED_FINAL", "unsupported target type")
            return InviteResult("DIRECT_INVITED")
        except errors.UserAlreadyParticipantError:
            return InviteResult("ALREADY_MEMBER")
        except errors.UserPrivacyRestrictedError:
            return InviteResult(
                "PRIVACY_RESTRICTED",
                "Telegram privacy restriction",
            )
        except errors.FloodWaitError as exc:
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=int(exc.seconds))
            return InviteResult(
                "FLOOD_WAIT",
                f"Telegram FloodWait {int(exc.seconds)}s",
                retry_at,
            )
        except errors.ChatAdminRequiredError:
            return InviteResult(
                "FAILED_FINAL",
                "admin invite permission required",
            )
        except errors.RPCError as exc:
            name = type(exc).__name__
            mapping = {
                "UserNotMutualContactError": "NOT_MUTUAL_CONTACT",
                "UserChannelsTooMuchError": "TOO_MANY_CHANNELS",
                "UserDeactivatedError": "DELETED_ACCOUNT",
                "UserDeactivatedBanError": "DELETED_ACCOUNT",
                "PeerFloodError": "FLOOD_WAIT",
            }
            return InviteResult(mapping.get(name, "FAILED_TEMPORARY"), name)

    async def export_invite_link(self) -> str:
        if self.target is None:
            raise RuntimeError("preflight must run before invite link export")
        result = await self.client(
            functions.messages.ExportChatInviteRequest(peer=self.target)
        )
        return result.link
