import json
import os
from pathlib import Path

_FLAGS = Path("data/runtime_flags.json")


def live_enabled() -> bool:
    if not _FLAGS.exists():
        return False
    try:
        data = json.loads(_FLAGS.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(data.get("live_enabled", False))


def set_live_enabled(value: bool) -> None:
    _FLAGS.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        _FLAGS.parent.chmod(0o700)
    _FLAGS.write_text(
        json.dumps({"live_enabled": bool(value)}),
        encoding="utf-8",
    )
    if os.name == "posix":
        _FLAGS.chmod(0o600)
