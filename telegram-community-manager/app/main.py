from fastapi import Depends, FastAPI

from .config import get_settings
from .security import require_admin

app = FastAPI(title="Telegram Community Manager", version="0.2.0")


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "ok": True,
        "dry_run": settings.dry_run,
        "configured": len(settings.missing_secrets()) == 0,
    }


@app.get("/config/status", dependencies=[Depends(require_admin)])
def config_status():
    settings = get_settings()
    return {
        "dry_run": settings.dry_run,
        "configured": len(settings.missing_secrets()) == 0,
        "missing": settings.missing_secrets(),
        "bind_host": settings.bind_host,
    }
