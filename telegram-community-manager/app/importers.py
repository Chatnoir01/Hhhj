import csv
import re
from dataclasses import dataclass
from pathlib import Path
from openpyxl import load_workbook

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
TELEGRAM_ID_RE = re.compile(r"^\d{5,20}$")


@dataclass(frozen=True)
class MemberImport:
    telegram_user_id: int | None
    username: str | None
    detail: str | None = None


def normalize_username(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
    raw = raw.split("?", 1)[0].split("/", 1)[0].lstrip("@").strip()
    return raw.lower() if USERNAME_RE.fullmatch(raw) else None


def normalize_telegram_id(value: object) -> int | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    return int(raw) if TELEGRAM_ID_RE.fullmatch(raw) else None


def _dedupe(values):
    seen = set()
    out = []
    for value in values:
        username = normalize_username(value)
        if username and username not in seen:
            seen.add(username)
            out.append(username)
    return out


def _header_index(row: list[object]) -> dict[str, int]:
    return {str(value).strip().lower(): i for i, value in enumerate(row) if value is not None}


def _mapping_rows(rows: list[list[object]]) -> list[MemberImport] | None:
    if not rows:
        return []
    header = _header_index(rows[0])
    id_col = header.get("telegram_id")
    username_col = header.get("username")
    all_usernames_col = header.get("all_usernames_seen")
    if id_col is None or (username_col is None and all_usernames_col is None):
        return None

    out: list[MemberImport] = []
    seen: set[tuple[int | None, str | None]] = set()
    for row in rows[1:]:
        tid = normalize_telegram_id(row[id_col] if id_col < len(row) else None)
        candidates: list[str] = []
        if username_col is not None and username_col < len(row):
            username = normalize_username(row[username_col])
            if username:
                candidates.append(username)
        if all_usernames_col is not None and all_usernames_col < len(row):
            for raw in str(row[all_usernames_col] or "").split("|"):
                username = normalize_username(raw)
                if username and username not in candidates:
                    candidates.append(username)

        if not candidates and tid is not None:
            key = (tid, None)
            if key not in seen:
                seen.add(key)
                out.append(MemberImport(tid, None, "ID_ONLY_NO_USERNAME"))
        for username in candidates:
            key = (tid, username)
            if key not in seen:
                seen.add(key)
                out.append(MemberImport(tid, username))
    return out


def load_members(path: str | Path) -> list[MemberImport]:
    path = Path(path)
    suffix = path.suffix.lower()
    rows: list[list[object]]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [list(row) for row in csv.reader(handle)]
    elif suffix == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        rows = [[cell.value for cell in row] for row in sheet.iter_rows()]
    else:
        raise ValueError("Mapping ID + username accepté en .csv ou .xlsx")

    mapped = _mapping_rows(rows)
    if mapped is None:
        raise ValueError("Colonnes requises: telegram_id et username/all_usernames_seen")
    return mapped


def load_usernames(path: str | Path) -> list[str]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _dedupe(path.read_text(encoding="utf-8").splitlines())
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [list(row) for row in csv.reader(handle)]
        mapped = _mapping_rows(rows)
        if mapped is not None:
            return _dedupe(item.username for item in mapped if item.username)
        return _dedupe(cell for row in rows for cell in row)
    if suffix == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        rows = [[cell.value for cell in row] for sheet in workbook.worksheets for row in sheet.iter_rows()]
        mapped = _mapping_rows(rows)
        if mapped is not None:
            return _dedupe(item.username for item in mapped if item.username)
        return _dedupe(cell for row in rows for cell in row)
    raise ValueError("Formats acceptés: .txt, .csv, .xlsx")
