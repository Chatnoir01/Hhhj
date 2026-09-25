from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
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


def pending_members(db: Session, campaign_id: int, limit: int) -> list[CampaignMember]:
    now = datetime.now(timezone.utc)
    immediately_resumable = (
        MemberStatus.IMPORTED.value,
        MemberStatus.RESOLVED.value,
        MemberStatus.READY_DIRECT_INVITE.value,
        MemberStatus.FAILED_TEMPORARY.value,
    )
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
        .order_by(CampaignMember.id.asc())
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
