from __future__ import annotations

import os
import shutil
import subprocess


def public_codespace_url(port: int = 8000) -> str | None:
    name = os.getenv("CODESPACE_NAME", "").strip()
    domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "").strip()
    if not name or not domain:
        return None
    return f"https://{name}-{port}.{domain}"


def publish_codespace_port(port: int = 8000) -> dict:
    name = os.getenv("CODESPACE_NAME", "").strip()
    if not name:
        return {
            "ok": False,
            "detail": "This action is only available inside GitHub Codespaces",
        }

    if shutil.which("gh") is None:
        return {"ok": False, "detail": "GitHub CLI is not available in this Codespace"}

    env = os.environ.copy()
    result = subprocess.run(
        [
            "gh",
            "codespace",
            "ports",
            "visibility",
            f"{port}:public",
            "-c",
            name,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )

    if result.returncode != 0:
        return {
            "ok": False,
            "detail": "GitHub refused public port visibility. Check Codespaces port-visibility policy or authentication.",
        }

    return {
        "ok": True,
        "visibility": "public",
        "port": port,
        "url": public_codespace_url(port),
    }
