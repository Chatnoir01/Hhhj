from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from .models import Campaign, CampaignMember, CampaignStatus, MemberStatus


def create_campaign(db: Session, name: str, target_group: str) -> Campaign:
    campaign = Campaign(name=name.strip(), target_group=target_group.strip())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def get_campaign(db: Session, campaign_id: int) -> Campaign | None:
    return db.get(Campaign, campaign_id)


def add_usernames(db: Session, campaign: Campaign, usernames: list[str]) -> int:
    existing = set(
        db.scalars(
            select(CampaignMember.username).where(CampaignMember.campaign_id == campaign.id)
        ).all()
    )
    added = 0
    for username in usernames:
        if username not in existing:
            db.add(CampaignMember(campaign_id=campaign.id, username=username))
            existing.add(username)
            added += 1
    if added:
        campaign.status = CampaignStatus.READY.value
    db.commit()
    return added


def add_member_mappings(db: Session, campaign: Campaign, members) -> dict[str, int]:
    existing_usernames = set(
        db.scalars(
            select(CampaignMember.username).where(CampaignMember.campaign_id == campaign.id)
        ).all()
    )
    added = 0
    id_only = 0
    aliases = 0
    for item in members:
        if not item.username:
            # Keep ID-only records out of the invite queue: Telegram MTProto cannot
            # safely address a bare ID without an access_hash/entity.
            id_only += 1
            continue
        if item.username in existing_usernames:
            continue
        db.add(
            CampaignMember(
                campaign_id=campaign.id,
                username=item.username,
                telegram_user_id=item.telegram_user_id,
                detail=item.detail,
            )
        )
        existing_usernames.add(item.username)
        added += 1
        if item.telegram_user_id is not None:
            aliases += 1
    if added:
        campaign.status = CampaignStatus.READY.value
    db.commit()
    return {"added": added, "with_telegram_id": aliases, "id_only_skipped": id_only}


def duplicate_telegram_identity(
    db: Session, campaign_id: int, member_id: int, telegram_user_id: int
) -> CampaignMember | None:
    stmt = (
        select(CampaignMember)
        .where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.id < member_id,
            CampaignMember.telegram_user_id == telegram_user_id,
            CampaignMember.status.notin_((MemberStatus.INVALID.value, MemberStatus.DUPLICATE_ID.value)),
        )
        .order_by(CampaignMember.id.asc())
        .limit(1)
    )
    return db.scalar(stmt)


def pending_members(
    db: Session,
    campaign_id: int,
    limit: int,
    *,
    include_ready_direct_invite: bool = True,
) -> list[CampaignMember]:
    now = datetime.now(timezone.utc)
    immediately_resumable = [
        MemberStatus.IMPORTED.value,
        MemberStatus.RESOLVED.value,
        MemberStatus.FAILED_TEMPORARY.value,
    ]
    if include_ready_direct_invite:
        immediately_resumable.append(MemberStatus.READY_DIRECT_INVITE.value)
    stmt = (
        select(CampaignMember)
        .where(
            CampaignMember.campaign_id == campaign_id,
            or_(
                CampaignMember.status.in_(immediately_resumable),
                and_(
                    CampaignMember.status == MemberStatus.FLOOD_WAIT.value,
                    CampaignMember.retry_after.is_not(None),
                    CampaignMember.retry_after <= now,
                ),
            ),
        )
        .order_by(
            case(
                (CampaignMember.status == MemberStatus.IMPORTED.value, 0),
                (CampaignMember.status == MemberStatus.RESOLVED.value, 1),
                (CampaignMember.status == MemberStatus.READY_DIRECT_INVITE.value, 2),
                (CampaignMember.status == MemberStatus.FAILED_TEMPORARY.value, 3),
                else_=4,
            ),
            CampaignMember.id.asc(),
        )
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def has_unfinished_members(db: Session, campaign_id: int) -> bool:
    unfinished = (
        MemberStatus.IMPORTED.value,
        MemberStatus.RESOLVED.value,
        MemberStatus.READY_DIRECT_INVITE.value,
        MemberStatus.FAILED_TEMPORARY.value,
        MemberStatus.FLOOD_WAIT.value,
    )
    stmt = (
        select(CampaignMember.id)
        .where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.status.in_(unfinished),
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def has_flood_wait_members(db: Session, campaign_id: int) -> bool:
    stmt = (
        select(CampaignMember.id)
        .where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.status == MemberStatus.FLOOD_WAIT.value,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def campaign_stats(db: Session, campaign_id: int) -> dict[str, int]:
    rows = db.scalars(
        select(CampaignMember.status).where(CampaignMember.campaign_id == campaign_id)
    ).all()
    return dict(Counter(rows))


def list_members(db: Session, campaign_id: int, limit: int = 200) -> list[CampaignMember]:
    stmt = (
        select(CampaignMember)
        .where(CampaignMember.campaign_id == campaign_id)
        .order_by(CampaignMember.id.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def list_campaigns(db: Session, limit: int = 100) -> list[Campaign]:
    stmt = select(Campaign).order_by(Campaign.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def members_by_status(
    db: Session,
    campaign_id: int,
    statuses: set[str] | tuple[str, ...],
    limit: int = 1000,
) -> list[CampaignMember]:
    stmt = (
        select(CampaignMember)
        .where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.status.in_(tuple(statuses)),
        )
        .order_by(CampaignMember.id.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
