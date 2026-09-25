from dataclasses import asdict

from sqlalchemy.orm import Session

from .config import Settings
from .models import Campaign, CampaignStatus, MemberStatus
from .repository import campaign_stats, pending_members
from .telegram_gateway import ResolvedUser


class CampaignEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(
        self,
        db: Session,
        campaign: Campaign,
        gateway,
        *,
        requested_live: bool = False,
        limit: int = 25,
    ) -> dict:
        effective_live = requested_live and campaign.live_enabled and not self.settings.dry_run

        preflight = await gateway.preflight(campaign.target_group)
        if not preflight.ok:
            campaign.status = CampaignStatus.FAILED.value
            campaign.last_error = preflight.detail
            db.commit()
            return {
                "ok": False,
                "live": effective_live,
                "preflight": asdict(preflight),
                "stats": campaign_stats(db, campaign.id),
            }

        campaign.status = CampaignStatus.RUNNING.value
        campaign.last_error = None
        db.commit()

        processed = 0
        stopped_on_flood_wait = False

        for member in pending_members(db, campaign.id, max(1, min(limit, 100))):
            processed += 1
            member.attempts += 1

            if member.telegram_user_id and member.access_hash:
                resolved = ResolvedUser(
                    user_id=member.telegram_user_id,
                    access_hash=member.access_hash,
                    username=member.username,
                )
            else:
                resolved = await gateway.resolve_username(member.username)
                if resolved is None:
                    member.status = MemberStatus.INVALID.value
                    member.detail = "username could not be resolved"
                    db.commit()
                    continue

                member.telegram_user_id = resolved.user_id
                member.access_hash = resolved.access_hash
                member.status = MemberStatus.RESOLVED.value
                member.detail = None

                if resolved.deleted:
                    member.status = MemberStatus.DELETED_ACCOUNT.value
                    member.detail = "deleted Telegram account"
                    db.commit()
                    continue
                if resolved.is_bot:
                    member.status = MemberStatus.BOT_ACCOUNT.value
                    member.detail = "bot accounts are not migrated"
                    db.commit()
                    continue
                db.commit()

            try:
                if await gateway.is_member(resolved):
                    member.status = MemberStatus.ALREADY_MEMBER.value
                    member.detail = None
                    db.commit()
                    continue
            except Exception as exc:
                member.status = MemberStatus.FAILED_TEMPORARY.value
                member.detail = f"membership check: {type(exc).__name__}"
                db.commit()
                continue

            if not effective_live:
                member.status = MemberStatus.READY_DIRECT_INVITE.value
                member.detail = "dry-run: eligible for a direct invite attempt"
                db.commit()
                continue

            result = await gateway.invite(resolved)
            member.status = result.status
            member.detail = result.detail
            member.retry_after = result.retry_after
            db.commit()

            if result.status == MemberStatus.FLOOD_WAIT.value:
                campaign.status = CampaignStatus.FLOOD_WAIT.value
                campaign.last_error = result.detail
                db.commit()
                stopped_on_flood_wait = True
                break

        if not stopped_on_flood_wait:
            remaining = pending_members(db, campaign.id, 1)
            if effective_live and not remaining:
                campaign.status = CampaignStatus.COMPLETED.value
            else:
                campaign.status = CampaignStatus.READY.value
            db.commit()

        return {
            "ok": True,
            "live": effective_live,
            "processed": processed,
            "preflight": asdict(preflight),
            "campaign_status": campaign.status,
            "stats": campaign_stats(db, campaign.id),
        }
