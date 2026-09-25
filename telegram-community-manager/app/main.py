from fastapi import FastAPI
from .config import get_settings

app = FastAPI(title="Telegram Community Manager", version="0.1.0")


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "ok": True,
        "dry_run": settings.dry_run,
        "missing_secrets": settings.missing_secrets(),
    }


@app.get("/config/status")
def config_status():
    settings = get_settings()
    return {
        "dry_run": settings.dry_run,
        "configured": len(settings.missing_secrets()) == 0,
        "missing": settings.missing_secrets(),
    }
