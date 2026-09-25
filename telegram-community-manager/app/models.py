import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FLOOD_WAIT = "FLOOD_WAIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MemberStatus(str, enum.Enum):
    IMPORTED = "IMPORTED"
    RESOLVED = "RESOLVED"
    INVALID = "INVALID"
    BOT_ACCOUNT = "BOT_ACCOUNT"
    ALREADY_MEMBER = "ALREADY_MEMBER"
    READY_DIRECT_INVITE = "READY_DIRECT_INVITE"
    DIRECT_INVITED = "DIRECT_INVITED"
    PRIVACY_RESTRICTED = "PRIVACY_RESTRICTED"
    NOT_MUTUAL_CONTACT = "NOT_MUTUAL_CONTACT"
    TOO_MANY_CHANNELS = "TOO_MANY_CHANNELS"
    DELETED_ACCOUNT = "DELETED_ACCOUNT"
    FLOOD_WAIT = "FLOOD_WAIT"
    LINK_REQUIRED = "LINK_REQUIRED"
    FAILED_TEMPORARY = "FAILED_TEMPORARY"
    FAILED_FINAL = "FAILED_FINAL"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_group: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default=CampaignStatus.DRAFT.value, index=True)
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    members: Mapped[list["CampaignMember"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignMember(Base):
    __tablename__ = "campaign_members"
    __table_args__ = (UniqueConstraint("campaign_id", "username", name="uq_campaign_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    username: Mapped[str] = mapped_column(String(32), index=True)
    telegram_user_id: Mapped[int | None] = mapped_column(nullable=True)
    access_hash: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(40), default=MemberStatus.IMPORTED.value, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="members")
