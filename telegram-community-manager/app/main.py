from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import tempfile
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .campaign_engine import CampaignEngine
from .dashboard import dashboard_response
from .config import Settings, get_settings
from .db import get_db, init_db
from .importers import _dedupe, load_members, load_usernames
from .logging_config import get_logger
from .github_publish import public_codespace_url, publish_codespace_port
from .models import CampaignStatus, MemberStatus
from .repository import (
    add_usernames,
    add_member_mappings,
    campaign_stats,
    create_campaign,
    get_campaign,
    list_members,
    list_campaigns,
)
from .schemas import (
    CampaignCreate,
    CampaignRunRequest,
    LiveActivationRequest,
    LoginRequest,
    SetupRequest,
    TelegramCodeRequest,
    TelegramPasswordRequest,
    UsernameImport,
)
from .security import get_admin_token, require_admin
from .runtime_store import (
    effective_settings,
    initialize as initialize_runtime,
    is_configured as runtime_is_configured,
    login as runtime_login,
    logout as runtime_logout,
)
from .telegram_gateway import TelegramGateway
from .web_telegram_auth import (
    send_login_code,
    telegram_auth_status,
    verify_2fa_password,
    verify_login_code,
)

logger = get_logger()

_RUN_JOBS: dict[str, dict] = {}
_RUN_TASKS: set[asyncio.Task] = set()


async def _run_campaign_job(job_id: str, campaign_id: int, token: str, live: bool, limit: int) -> None:
    from .db import SessionLocal

    job = _RUN_JOBS[job_id]
    job["status"] = "running"
    db = SessionLocal()
    gateway = None
    try:
        campaign = _campaign_or_404(db, campaign_id)
        settings = effective_settings(token)
        _telegram_ready(settings)
        gateway = TelegramGateway(settings)
        if not await gateway.connect_authorized():
            raise RuntimeError("Telegram session is not authorized")
        engine = CampaignEngine(settings)
        job["result"] = await engine.run(
            db, campaign, gateway, requested_live=live,
            limit=min(limit, settings.max_batch_size),
        )
        job["status"] = "completed"
    except Exception as exc:
        logger.warning("Campaign background job failed: %s", type(exc).__name__)
        job["status"] = "failed"
        job["error"] = type(exc).__name__
    finally:
        if gateway is not None:
            await gateway.close()
        db.close()


def _remember_task(task: asyncio.Task) -> None:
    _RUN_TASKS.add(task)
    task.add_done_callback(_RUN_TASKS.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Telegram Community Manager",
    version="0.6.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def dashboard():
    return dashboard_response()


def _effective_settings_dependency(
    token: str = Depends(get_admin_token),
) -> Settings:
    return effective_settings(token)


@app.get("/setup/status")
def setup_status():
    return {
        "configured": runtime_is_configured(),
        "env_admin_configured": bool(get_settings().admin_api_key),
    }


@app.post("/setup/initialize")
def setup_initialize(payload: SetupRequest):
    if runtime_is_configured():
        raise HTTPException(status_code=409, detail="Setup already initialized")
    try:
        initialize_runtime(
            password=payload.admin_password,
            telegram_api_id=payload.telegram_api_id,
            telegram_api_hash=payload.telegram_api_hash,
            telegram_phone=payload.telegram_phone,
            telegram_bot_token=payload.telegram_bot_token,
        )
        token, _ = runtime_login(payload.admin_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "token": token}


@app.post("/auth/login")
def admin_login(payload: LoginRequest):
    if not runtime_is_configured():
        raise HTTPException(status_code=409, detail="Setup is not initialized")
    try:
        token, _ = runtime_login(payload.admin_password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid admin password") from exc
    return {"ok": True, "token": token}


@app.post("/auth/logout")
def admin_logout(token: str = Depends(get_admin_token)):
    runtime_logout(token)
    return {"ok": True}


@app.get("/github/public-url", dependencies=[Depends(require_admin)])
def github_public_url():
    return {
        "ok": True,
        "url": public_codespace_url(8000),
    }


@app.post("/github/publish", dependencies=[Depends(require_admin)])
def github_publish():
    result = publish_codespace_port(8000)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("detail"))
    return result


@app.get("/telegram/auth/status")
async def telegram_login_status(
    token: str = Depends(get_admin_token),
):
    settings = effective_settings(token)
    return {"ok": True, "authorized": await telegram_auth_status(settings)}


@app.post("/telegram/auth/send-code")
async def telegram_send_code(
    token: str = Depends(get_admin_token),
):
    settings = effective_settings(token)
    _telegram_ready(settings)
    try:
        return await send_login_code(token, settings)
    except Exception as exc:
        logger.warning("Telegram send-code failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=400,
            detail=f"Telegram login failed: {type(exc).__name__}",
        ) from exc


@app.post("/telegram/auth/verify-code")
async def telegram_verify_code(
    payload: TelegramCodeRequest,
    token: str = Depends(get_admin_token),
):
    settings = effective_settings(token)
    return await verify_login_code(token, settings, payload.code)


@app.post("/telegram/auth/verify-2fa")
async def telegram_verify_2fa(
    payload: TelegramPasswordRequest,
    token: str = Depends(get_admin_token),
):
    settings = effective_settings(token)
    return await verify_2fa_password(token, settings, payload.password)


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
        "member_count": sum(campaign_stats(db, campaign.id).values()),
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
        "configured": runtime_is_configured() or len(settings.missing_secrets()) == 0,
        "version": app.version,
    }


@app.get("/config/status", dependencies=[Depends(require_admin)])
def config_status(
    settings: Settings = Depends(_effective_settings_dependency),
):
    return {
        "dry_run": settings.dry_run,
        "configured": len(settings.missing_secrets()) == 0,
        "missing": settings.missing_secrets(),
        "bind_host": settings.bind_host,
        "max_upload_bytes": settings.max_upload_bytes,
        "max_batch_size": settings.max_batch_size,
    }


@app.get("/campaigns", dependencies=[Depends(require_admin)])
def list_campaigns_route(db: Session = Depends(get_db)):
    campaigns = list_campaigns(db)
    return {
        "ok": True,
        "campaigns": [
            {
                "id": campaign.id,
                "name": campaign.name,
                "target_group": campaign.target_group,
                "status": campaign.status,
                "stats": campaign_stats(db, campaign.id),
                "member_count": sum(campaign_stats(db, campaign.id).values()),
            }
            for campaign in campaigns
        ],
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
    settings: Settings = Depends(_effective_settings_dependency),
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
        if suffix in {".csv", ".xlsx"}:
            try:
                members = load_members(handle.name)
            except ValueError:
                members = None
        else:
            members = None

        if members is not None:
            result = add_member_mappings(db, campaign, members)
            return {
                "ok": True,
                "format": "telegram_id_username_mapping",
                "records": len(members),
                **result,
                "stats": campaign_stats(db, campaign.id),
            }

        usernames = load_usernames(handle.name)

    added = add_usernames(db, campaign, usernames)
    return {
        "ok": True,
        "format": "usernames",
        "valid_unique": len(usernames),
        "added": added,
        "stats": campaign_stats(db, campaign.id),
    }


@app.post("/campaigns/{campaign_id}/activate-live", dependencies=[Depends(require_admin)])
def activate_live_route(
    campaign_id: int,
    payload: LiveActivationRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(_effective_settings_dependency),
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
    settings: Settings = Depends(_effective_settings_dependency),
):
    campaign = _campaign_or_404(db, campaign_id)
    _telegram_ready(settings)
    gateway = TelegramGateway(settings)
    try:
        if not await gateway.connect_authorized():
            raise HTTPException(
                status_code=409,
                detail="Telegram session is not authorized; connect Telegram from the web panel",
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


@app.post("/campaigns/{campaign_id}/run-async")
async def run_campaign_async_route(
    campaign_id: int,
    payload: CampaignRunRequest,
    token: str = Depends(get_admin_token),
    db: Session = Depends(get_db),
    settings: Settings = Depends(_effective_settings_dependency),
):
    campaign = _campaign_or_404(db, campaign_id)
    _telegram_ready(settings)
    if campaign.status == CampaignStatus.PAUSED.value:
        raise HTTPException(status_code=409, detail="Campaign is paused; resume it first")
    if payload.live and settings.dry_run:
        raise HTTPException(status_code=409, detail="Global DRY_RUN blocks live invitations")
    if payload.live and not campaign.live_enabled:
        raise HTTPException(status_code=409, detail="Campaign live mode is not activated")

    job_id = uuid.uuid4().hex
    _RUN_JOBS[job_id] = {
        "id": job_id,
        "campaign_id": campaign_id,
        "status": "queued",
        "live": payload.live,
        "limit": min(payload.limit, settings.max_batch_size),
        "result": None,
        "error": None,
    }
    task = asyncio.create_task(
        _run_campaign_job(job_id, campaign_id, token, payload.live, payload.limit)
    )
    _remember_task(task)
    return {"ok": True, "job_id": job_id, "status": "queued"}


@app.get("/campaign-runs/{job_id}")
def campaign_run_status(
    job_id: str,
    token: str = Depends(get_admin_token),
):
    job = _RUN_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Campaign run not found")
    return job


@app.post("/campaigns/{campaign_id}/run", dependencies=[Depends(require_admin)])
async def run_campaign_route(
    campaign_id: int,
    payload: CampaignRunRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(_effective_settings_dependency),
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
                detail="Telegram session is not authorized; connect Telegram from the web panel",
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
    settings: Settings = Depends(_effective_settings_dependency),
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
