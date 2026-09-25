from contextlib import asynccontextmanager
from pathlib import Path
import tempfile

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .campaign_engine import CampaignEngine
from .config import Settings, get_settings
from .db import get_db, init_db
from .importers import _dedupe, load_usernames
from .logging_config import get_logger
from .models import CampaignStatus, MemberStatus
from .repository import (
    add_usernames,
    campaign_stats,
    create_campaign,
    get_campaign,
    list_members,
)
from .schemas import CampaignCreate, CampaignRunRequest, LiveActivationRequest, UsernameImport
from .security import require_admin
from .telegram_gateway import TelegramGateway

logger = get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Telegram Community Manager",
    version="0.5.0",
    lifespan=lifespan,
)


def _campaign_or_404(db: Session, campaign_id: int):
    campaign = get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _telegram_ready(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "TELEGRAM_API_ID": settings.telegram_api_id,
            "TELEGRAM_API_HASH": settings.telegram_api_hash,
        }.items()
        if value in (None, "")
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Missing Telegram configuration: {', '.join(missing)}",
        )


def _serialize_campaign(db: Session, campaign) -> dict:
    members = list_members(db, campaign.id, limit=200)
    return {
        "id": campaign.id,
        "name": campaign.name,
        "target_group": campaign.target_group,
        "status": campaign.status,
        "live_enabled": campaign.live_enabled,
        "last_error": campaign.last_error,
        "stats": campaign_stats(db, campaign.id),
        "members": [
            {
                "id": member.id,
                "username": member.username,
                "status": member.status,
                "detail": member.detail,
                "attempts": member.attempts,
                "retry_after": member.retry_after,
            }
            for member in members
        ],
    }


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "ok": True,
        "dry_run": settings.dry_run,
        "configured": len(settings.missing_secrets()) == 0,
        "version": app.version,
    }


@app.get("/config/status", dependencies=[Depends(require_admin)])
def config_status():
    settings = get_settings()
    return {
        "dry_run": settings.dry_run,
        "configured": len(settings.missing_secrets()) == 0,
        "missing": settings.missing_secrets(),
        "bind_host": settings.bind_host,
        "max_upload_bytes": settings.max_upload_bytes,
        "max_batch_size": settings.max_batch_size,
    }


@app.post("/campaigns", dependencies=[Depends(require_admin)])
def create_campaign_route(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
):
    campaign = create_campaign(db, payload.name, payload.target_group)
    return _serialize_campaign(db, campaign)


@app.get("/campaigns/{campaign_id}", dependencies=[Depends(require_admin)])
def get_campaign_route(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    return _serialize_campaign(db, _campaign_or_404(db, campaign_id))


@app.post("/campaigns/{campaign_id}/import", dependencies=[Depends(require_admin)])
def import_usernames_route(
    campaign_id: int,
    payload: UsernameImport,
    db: Session = Depends(get_db),
):
    campaign = _campaign_or_404(db, campaign_id)
    usernames = _dedupe(payload.usernames)
    added = add_usernames(db, campaign, usernames)
    return {
        "ok": True,
        "received": len(payload.usernames),
        "valid_unique": len(usernames),
        "added": added,
        "stats": campaign_stats(db, campaign.id),
    }


@app.post("/campaigns/{campaign_id}/import-file", dependencies=[Depends(require_admin)])
async def import_file_route(
    campaign_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    campaign = _campaign_or_404(db, campaign_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".csv", ".xlsx"}:
        raise HTTPException(status_code=400, detail="Only .txt, .csv and .xlsx are accepted")

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload too large")

    with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
        handle.write(data)
        handle.flush()
        usernames = load_usernames(handle.name)

    added = add_usernames(db, campaign, usernames)
    return {
        "ok": True,
        "valid_unique": len(usernames),
        "added": added,
        "stats": campaign_stats(db, campaign.id),
    }


@app.post("/campaigns/{campaign_id}/activate-live", dependencies=[Depends(require_admin)])
def activate_live_route(
    campaign_id: int,
    payload: LiveActivationRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    campaign = _campaign_or_404(db, campaign_id)
    if settings.dry_run:
        raise HTTPException(
            status_code=409,
            detail="Global DRY_RUN is enabled; set DRY_RUN=false before live activation",
        )
    if payload.confirmation != "ENABLE_LIVE_INVITES":
        raise HTTPException(status_code=400, detail="Invalid live activation confirmation")
    campaign.live_enabled = True
    campaign.status = CampaignStatus.READY.value
    db.commit()
    return {"ok": True, "live_enabled": True}


@app.post("/campaigns/{campaign_id}/pause", dependencies=[Depends(require_admin)])
def pause_campaign_route(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    campaign = _campaign_or_404(db, campaign_id)
    campaign.status = CampaignStatus.PAUSED.value
    db.commit()
    return {"ok": True, "status": campaign.status}


@app.post("/campaigns/{campaign_id}/resume", dependencies=[Depends(require_admin)])
def resume_campaign_route(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    campaign = _campaign_or_404(db, campaign_id)
    campaign.status = CampaignStatus.READY.value
    db.commit()
    return {"ok": True, "status": campaign.status}


@app.post("/campaigns/{campaign_id}/preflight", dependencies=[Depends(require_admin)])
async def preflight_route(
    campaign_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    campaign = _campaign_or_404(db, campaign_id)
    _telegram_ready(settings)
    gateway = TelegramGateway(settings)
    try:
        if not await gateway.connect_authorized():
            raise HTTPException(
                status_code=409,
                detail="Telegram session is not authorized; run scripts/auth_telegram.py locally",
            )
        result = await gateway.preflight(campaign.target_group)
        return {
            "ok": result.ok,
            "target_title": result.target_title,
            "can_invite": result.can_invite,
            "detail": result.detail,
        }
    finally:
        await gateway.close()


@app.post("/campaigns/{campaign_id}/run", dependencies=[Depends(require_admin)])
async def run_campaign_route(
    campaign_id: int,
    payload: CampaignRunRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    campaign = _campaign_or_404(db, campaign_id)
    _telegram_ready(settings)

    if campaign.status == CampaignStatus.PAUSED.value:
        raise HTTPException(status_code=409, detail="Campaign is paused; resume it first")

    if payload.live and settings.dry_run:
        raise HTTPException(status_code=409, detail="Global DRY_RUN blocks live invitations")
    if payload.live and not campaign.live_enabled:
        raise HTTPException(
            status_code=409,
            detail="Campaign live mode is not activated",
        )

    gateway = TelegramGateway(settings)
    try:
        if not await gateway.connect_authorized():
            raise HTTPException(
                status_code=409,
                detail="Telegram session is not authorized; run scripts/auth_telegram.py locally",
            )
        engine = CampaignEngine(settings)
        return await engine.run(
            db,
            campaign,
            gateway,
            requested_live=payload.live,
            limit=min(payload.limit, settings.max_batch_size),
        )
    finally:
        await gateway.close()


@app.post("/campaigns/{campaign_id}/invite-link", dependencies=[Depends(require_admin)])
async def invite_link_route(
    campaign_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    campaign = _campaign_or_404(db, campaign_id)
    _telegram_ready(settings)
    gateway = TelegramGateway(settings)
    try:
        if not await gateway.connect_authorized():
            raise HTTPException(
                status_code=409,
                detail="Telegram session is not authorized",
            )
        preflight = await gateway.preflight(campaign.target_group)
        if not preflight.ok:
            raise HTTPException(status_code=409, detail=preflight.detail)
        link = await gateway.export_invite_link()
        return {"ok": True, "invite_link": link}
    finally:
        await gateway.close()


@app.get("/campaigns/{campaign_id}/fallback", dependencies=[Depends(require_admin)])
def fallback_members_route(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    _campaign_or_404(db, campaign_id)
    fallback_statuses = {
        MemberStatus.PRIVACY_RESTRICTED.value,
        MemberStatus.NOT_MUTUAL_CONTACT.value,
        MemberStatus.TOO_MANY_CHANNELS.value,
        MemberStatus.LINK_REQUIRED.value,
    }
    members = [
        member
        for member in list_members(db, campaign_id, limit=1000)
        if member.status in fallback_statuses
    ]
    return {
        "count": len(members),
        "members": [
            {
                "username": member.username,
                "status": member.status,
                "detail": member.detail,
            }
            for member in members
        ],
    }
