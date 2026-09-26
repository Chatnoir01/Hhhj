import asyncio
import getpass
from pathlib import Path

from telethon import TelegramClient

from app.config import get_settings
from app.security import harden_session_file, secure_session_path


async def main() -> None:
    settings = get_settings()

    missing = [
        name
        for name, value in {
            "TELEGRAM_API_ID": settings.telegram_api_id,
            "TELEGRAM_API_HASH": settings.telegram_api_hash,
            "TELEGRAM_PHONE": settings.telegram_phone,
        }.items()
        if value in (None, "")
    ]
    if missing:
        raise SystemExit(f"Missing configuration: {', '.join(missing)}")

    session_path = secure_session_path(settings, "community-manager")
    client = TelegramClient(
        str(session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    try:
        await client.start(
            phone=settings.telegram_phone,
            code_callback=lambda: input("Telegram login code: ").strip(),
            password=lambda: getpass.getpass("Telegram 2FA password: "),
        )
        me = await client.get_me()
        harden_session_file(Path(f"{session_path}.session"))
        username = f"@{me.username}" if me and me.username else "(no username)"
        print(f"Authorized Telegram session for user id {me.id} {username}")
        print("Session stored locally in the configured SESSION_DIR.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
