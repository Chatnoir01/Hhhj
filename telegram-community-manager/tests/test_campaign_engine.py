from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.campaign_engine import CampaignEngine
from app.config import Settings
from app.db import Base
from app.models import CampaignMember, MemberStatus
from app.repository import add_usernames, create_campaign
from app.telegram_gateway import InviteResult, PreflightResult, ResolvedUser


class FakeGateway:
    def __init__(self):
        self.resolve_calls = 0
        self.invite_calls = 0
        self.members = set()
        self.invite_results = {}

    async def preflight(self, target_group):
        return PreflightResult(
            ok=True,
            target_title="Target",
            can_invite=True,
            detail="ok",
        )

    async def resolve_username(self, username):
        self.resolve_calls += 1
        if username == "invalid_user":
            return None
        if username == "bot_user":
            return ResolvedUser(2, 22, username, is_bot=True)
        if username == "deleted_user":
            return ResolvedUser(3, 33, username, deleted=True)
        ids = {
            "member_user": (4, 44),
            "ready_user": (5, 55),
            "privacy_user": (6, 66),
            "flood_user": (7, 77),
        }
        user_id, access_hash = ids.get(username, (99, 999))
        return ResolvedUser(user_id, access_hash, username)

    async def is_member(self, user):
        return user.username in self.members

    async def invite(self, user):
        self.invite_calls += 1
        return self.invite_results.get(
            user.username,
            InviteResult(MemberStatus.DIRECT_INVITED.value),
        )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.mark.asyncio
async def test_dry_run_classifies_without_inviting(db):
    campaign = create_campaign(db, "dry", "@target")
    add_usernames(
        db,
        campaign,
        [
            "invalid_user",
            "bot_user",
            "deleted_user",
            "member_user",
            "ready_user",
        ],
    )

    gateway = FakeGateway()
    gateway.members.add("member_user")
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)

    result = await CampaignEngine(settings).run(
        db,
        campaign,
        gateway,
        requested_live=False,
        limit=25,
    )

    rows = {
        row.username: row.status
        for row in db.scalars(select(CampaignMember)).all()
    }

    assert result["live"] is False
    assert gateway.invite_calls == 0
    assert rows["invalid_user"] == MemberStatus.INVALID.value
    assert rows["bot_user"] == MemberStatus.BOT_ACCOUNT.value
    assert rows["deleted_user"] == MemberStatus.DELETED_ACCOUNT.value
    assert rows["member_user"] == MemberStatus.ALREADY_MEMBER.value
    assert rows["ready_user"] == MemberStatus.READY_DIRECT_INVITE.value


@pytest.mark.asyncio
async def test_global_dry_run_blocks_invite_even_if_live_requested(db):
    campaign = create_campaign(db, "safe", "@target")
    campaign.live_enabled = True
    add_usernames(db, campaign, ["ready_user"])
    db.commit()

    gateway = FakeGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)

    result = await CampaignEngine(settings).run(
        db,
        campaign,
        gateway,
        requested_live=True,
        limit=25,
    )

    member = db.scalar(select(CampaignMember))
    assert result["live"] is False
    assert member.status == MemberStatus.READY_DIRECT_INVITE.value
    assert gateway.invite_calls == 0


@pytest.mark.asyncio
async def test_resume_from_dry_run_reuses_resolved_identity_and_invites(db):
    campaign = create_campaign(db, "resume", "@target")
    add_usernames(db, campaign, ["ready_user"])

    gateway = FakeGateway()
    settings = Settings(_env_file=None, dry_run=False, admin_api_key="x" * 40)
    engine = CampaignEngine(settings)

    await engine.run(
        db,
        campaign,
        gateway,
        requested_live=False,
        limit=25,
    )
    assert gateway.resolve_calls == 1

    campaign.live_enabled = True
    db.commit()

    result = await engine.run(
        db,
        campaign,
        gateway,
        requested_live=True,
        limit=25,
    )

    member = db.scalar(select(CampaignMember))
    assert result["live"] is True
    assert member.status == MemberStatus.DIRECT_INVITED.value
    assert gateway.resolve_calls == 1
    assert gateway.invite_calls == 1


@pytest.mark.asyncio
async def test_flood_wait_is_persisted_and_stops_batch(db):
    campaign = create_campaign(db, "flood", "@target")
    campaign.live_enabled = True
    add_usernames(db, campaign, ["flood_user", "ready_user"])
    db.commit()

    gateway = FakeGateway()
    retry_at = datetime.now(timezone.utc)
    gateway.invite_results["flood_user"] = InviteResult(
        MemberStatus.FLOOD_WAIT.value,
        "FloodWait",
        retry_at,
    )

    settings = Settings(_env_file=None, dry_run=False, admin_api_key="x" * 40)
    result = await CampaignEngine(settings).run(
        db,
        campaign,
        gateway,
        requested_live=True,
        limit=25,
    )

    rows = {
        row.username: row
        for row in db.scalars(select(CampaignMember)).all()
    }

    assert result["campaign_status"] == "FLOOD_WAIT"
    assert rows["flood_user"].status == MemberStatus.FLOOD_WAIT.value
    assert rows["flood_user"].retry_after is not None
    assert rows["ready_user"].status == MemberStatus.IMPORTED.value
    assert gateway.invite_calls == 1


@pytest.mark.asyncio
async def test_repeated_dry_run_advances_to_next_batch(db):
    campaign = create_campaign(db, "advance", "@target")
    add_usernames(db, campaign, ["ready_user", "privacy_user"])

    gateway = FakeGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)
    engine = CampaignEngine(settings)

    first = await engine.run(db, campaign, gateway, requested_live=False, limit=1)
    second = await engine.run(db, campaign, gateway, requested_live=False, limit=1)

    rows = {
        row.username: row.status
        for row in db.scalars(select(CampaignMember)).all()
    }
    assert first["processed"] == 1
    assert second["processed"] == 1
    assert gateway.resolve_calls == 2
    assert rows["ready_user"] == MemberStatus.READY_DIRECT_INVITE.value
    assert rows["privacy_user"] == MemberStatus.READY_DIRECT_INVITE.value


@pytest.mark.asyncio
async def test_duplicate_identity_keeps_first_member_as_canonical(db):
    campaign = create_campaign(db, "aliases", "@target")
    add_usernames(db, campaign, ["alias_one", "alias_two"])

    gateway = FakeGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)

    await CampaignEngine(settings).run(
        db, campaign, gateway, requested_live=False, limit=25
    )

    rows = {
        row.username: row.status
        for row in db.scalars(select(CampaignMember)).all()
    }
    assert rows["alias_one"] == MemberStatus.READY_DIRECT_INVITE.value
    assert rows["alias_two"] == MemberStatus.DUPLICATE_ID.value


class SlowGateway(FakeGateway):
    async def resolve_username(self, username):
        import asyncio
        await asyncio.sleep(31)


class ExplodingResolveGateway(FakeGateway):
    async def resolve_username(self, username):
        raise RuntimeError("temporary network failure")


@pytest.mark.asyncio
async def test_resolution_timeout_isolated_and_does_not_invite(db, monkeypatch):
    campaign = create_campaign(db, "timeout", "@target")
    add_usernames(db, campaign, ["ready_user"])
    gateway = SlowGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)

    real_wait_for = __import__("asyncio").wait_for

    async def timeout_resolution_only(awaitable, timeout):
        if getattr(awaitable, "cr_code", None) and awaitable.cr_code.co_name == "resolve_username":
            awaitable.close()
            raise TimeoutError
        return await real_wait_for(awaitable, timeout)

    monkeypatch.setattr("app.campaign_engine.asyncio.wait_for", timeout_resolution_only)
    result = await CampaignEngine(settings).run(db, campaign, gateway, requested_live=False, limit=25)
    member = db.scalar(select(CampaignMember))
    assert result["ok"] is True
    assert member.status == MemberStatus.FAILED_TEMPORARY.value
    assert gateway.invite_calls == 0


@pytest.mark.asyncio
async def test_unexpected_resolution_failure_isolated(db):
    campaign = create_campaign(db, "resolve-error", "@target")
    add_usernames(db, campaign, ["ready_user"])
    gateway = ExplodingResolveGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)
    result = await CampaignEngine(settings).run(db, campaign, gateway, requested_live=False, limit=25)
    member = db.scalar(select(CampaignMember))
    assert result["ok"] is True
    assert member.status == MemberStatus.FAILED_TEMPORARY.value
    assert "RuntimeError" in member.detail
    assert gateway.invite_calls == 0


@pytest.mark.asyncio
async def test_fresh_members_are_processed_before_transient_retries(db):
    campaign = create_campaign(db, "priority", "@target")
    add_usernames(db, campaign, ["old_failure", "ready_user"])
    rows = list(db.scalars(select(CampaignMember).order_by(CampaignMember.id)).all())
    rows[0].status = MemberStatus.FAILED_TEMPORARY.value
    db.commit()

    gateway = FakeGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)
    result = await CampaignEngine(settings).run(db, campaign, gateway, requested_live=False, limit=1)

    rows = {row.username: row for row in db.scalars(select(CampaignMember)).all()}
    assert result["processed"] == 1
    assert rows["ready_user"].status == MemberStatus.READY_DIRECT_INVITE.value
    assert rows["old_failure"].attempts == 0


@pytest.mark.asyncio
async def test_1700_member_dry_run_completes_in_100_batches(db):
    campaign = create_campaign(db, "scale", "@target")
    names = [f"user_{i:04d}" for i in range(1700)]
    add_usernames(db, campaign, names)

    class ScaleGateway(FakeGateway):
        async def resolve_username(self, username):
            self.resolve_calls += 1
            n = int(username.rsplit("_", 1)[1])
            return ResolvedUser(10000 + n, 20000 + n, username)

    gateway = ScaleGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)
    engine = CampaignEngine(settings)
    total = 0
    for _ in range(17):
        result = await engine.run(db, campaign, gateway, requested_live=False, limit=100)
        total += result["processed"]
    rows = list(db.scalars(select(CampaignMember)).all())
    assert total == 1700
    assert len(rows) == 1700
    assert all(row.status == MemberStatus.READY_DIRECT_INVITE.value for row in rows)
    assert gateway.invite_calls == 0
    final = await engine.run(db, campaign, gateway, requested_live=False, limit=100)
    assert final["processed"] == 0


@pytest.mark.asyncio
async def test_transient_failure_stops_after_three_attempts(db):
    campaign = create_campaign(db, "bounded", "@target")
    add_usernames(db, campaign, ["ready_user"])
    gateway = ExplodingResolveGateway()
    settings = Settings(_env_file=None, dry_run=True, admin_api_key="x" * 40)
    engine = CampaignEngine(settings)
    for _ in range(3):
        result = await engine.run(db, campaign, gateway, requested_live=False, limit=1)
        assert result["processed"] == 1
    fourth = await engine.run(db, campaign, gateway, requested_live=False, limit=1)
    row = db.scalar(select(CampaignMember))
    assert row.attempts == 3
    assert row.status == MemberStatus.FAILED_FINAL.value
    assert fourth["processed"] == 0


@pytest.mark.asyncio
async def test_invite_timeout_confirms_membership_before_retry(db, monkeypatch):
    campaign = create_campaign(db, "ambiguous", "@target")
    campaign.live_enabled = True
    add_usernames(db, campaign, ["ready_user"])
    db.commit()
    gateway = FakeGateway()
    settings = Settings(_env_file=None, dry_run=False, admin_api_key="x" * 40)
    real_wait_for = __import__("asyncio").wait_for
    invite_timed_out = False

    async def timeout_invite_only(awaitable, timeout):
        nonlocal invite_timed_out
        if getattr(awaitable, "cr_code", None) and awaitable.cr_code.co_name == "invite" and not invite_timed_out:
            invite_timed_out = True
            awaitable.close()
            gateway.members.add("ready_user")
            raise TimeoutError
        return await real_wait_for(awaitable, timeout)

    monkeypatch.setattr("app.campaign_engine.asyncio.wait_for", timeout_invite_only)
    await CampaignEngine(settings).run(db, campaign, gateway, requested_live=True, limit=1)
    row = db.scalar(select(CampaignMember))
    assert row.status == MemberStatus.DIRECT_INVITED.value
    assert "membership was confirmed" in row.detail
