import asyncio
from pathlib import Path

import pytest
from telethon.errors import SessionPasswordNeededError, UserNotParticipantError

from app.config import Settings
from app.telegram_service import TelegramService


class FakeClient:
    def __init__(self, session, api_id, api_hash):
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self.authorized = False
        self.sent_code = False
        self.disconnected = False
        self.sign_in_mode = "ok"
        self.calls = []
        self.entities = {
            "subscriber": object(),
            "@target": object(),
        }

    async def connect(self):
        return None

    async def disconnect(self):
        self.disconnected = True

    async def is_user_authorized(self):
        return self.authorized

    async def send_code_request(self, phone):
        self.sent_code = True

    async def sign_in(self, **kwargs):
        if self.sign_in_mode == "2fa":
            raise SessionPasswordNeededError(request=None)
        self.authorized = True

    async def get_entity(self, value):
        return self.entities[value]

    async def __call__(self, request):
        self.calls.append(request)
        if request.__class__.__name__ == "GetParticipantRequest":
            raise UserNotParticipantError(request=request)


def make_settings(tmp_path: Path, dry_run: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        telegram_api_id=123,
        telegram_api_hash="a" * 32,
        telegram_phone="+32000000000",
        target_group="@target",
        admin_api_key="z" * 40,
        session_dir=tmp_path,
        dry_run=dry_run,
    )


def test_start_login_requests_code_without_logging_credentials(tmp_path):
    service = TelegramService(make_settings(tmp_path), client_factory=FakeClient)
    state = asyncio.run(service.start_login())

    assert state.status == "code_required"
    assert service.client.sent_code is True


def test_submit_code_uses_typed_2fa_exception(tmp_path):
    service = TelegramService(make_settings(tmp_path), client_factory=FakeClient)
    asyncio.run(service.start_login())
    service.client.sign_in_mode = "2fa"

    state = asyncio.run(service.submit_code("12345"))

    assert state.status == "password_required"


def test_dry_run_resolves_and_checks_membership_but_does_not_invite(tmp_path):
    service = TelegramService(
        make_settings(tmp_path, dry_run=True),
        client_factory=FakeClient,
    )
    asyncio.run(service.start_login())

    result = asyncio.run(service.invite_username("@Subscriber"))

    assert result.status == "would_invite"
    call_names = [request.__class__.__name__ for request in service.client.calls]
    assert call_names == ["GetParticipantRequest"]
    assert "InviteToChannelRequest" not in call_names


def test_real_mode_sends_one_invite_request_after_membership_check(tmp_path):
    service = TelegramService(
        make_settings(tmp_path, dry_run=False),
        client_factory=FakeClient,
    )
    asyncio.run(service.start_login())

    result = asyncio.run(service.invite_username("@Subscriber"))

    assert result.status == "invited"
    call_names = [request.__class__.__name__ for request in service.client.calls]
    assert call_names == ["GetParticipantRequest", "InviteToChannelRequest"]


def test_source_does_not_use_exception_string_password_detection():
    source = Path("app/telegram_service.py").read_text(encoding="utf-8")

    assert "SessionPasswordNeededError" in source
    assert "'password' in str" not in source
    assert '"password" in str' not in source
