# Security & dependency audit — upstream Telegram Member Migration Tool

Audit date: 2026-09-25  
Upstream: Nayan-Bebale/Telegram-Member-Migration-Tool  
Pinned commit: `0619887480abe6a19b6652e8a8aafe6ceaa93a66`

## Verdict

**Do not put real Telegram credentials or a real Telegram session into the upstream web app as-is.**

The project has a useful functional core, but the Web/auth/session layer has several P0 issues. The mandatory order is: lock down access, remove secret leakage/destructive session deletion/XSS, make dry-run fail-safe, then repair persistence and async architecture.

## P0 — Critical

### 1. Unauthenticated control plane
`app.py` exposes POST routes for connection/authentication, scraping, adding members, broadcasting DMs, generating invite links, deleting sessions, verification and CSV upload. There is no application-level login/authorization decorator. The local server also binds to `0.0.0.0`.

**Impact:** if the service becomes reachable from another machine, an unauthorised caller can exercise sensitive Telegram actions available to that web session.

**Fix:** bind to localhost by default; require an admin secret/session on every API and Socket.IO connection; fail closed when auth is not configured.

### 2. Telegram OTP logged in clear text
`app.py` logs both the submitted OTP and the callback result.

**Impact:** anyone who can read the log can recover a live login code during the authentication window.

**Fix:** never log OTP, 2FA passwords, API hash, tokens or session strings. Add a central redaction filter and a regression test.

### 3. Destructive Windows session deletion
`delete_session()` executes `taskkill /F /IM python.exe`.

**Impact:** kills every Python process owned/visible to that Windows session, potentially including unrelated applications and the server itself.

**Fix:** remove this code entirely. Disconnect the Telethon client on its owning loop, join its worker thread, then delete only the expected session file.

### 4. DOM XSS
`templates/index.html` renders Telegram/user-controlled values using `innerHTML` in `displayMembers()` and `addLog()`.

**Impact:** a crafted name, group string or error text can execute HTML/JS in the dashboard context.

**Fix:** render untrusted values with `textContent` / DOM nodes only. Add a strict CSP.

## P1 — High

### 5. Socket.IO wildcard origin
`cors_allowed_origins="*"`.

**Fix:** same-origin by default or a small allow-list; validate Origin and require Socket.IO authentication.

### 6. Ephemeral Flask SECRET_KEY
`app.config['SECRET_KEY'] = secrets.token_hex(16)` changes on every process start.

**Impact:** cookies die on restart; different Gunicorn workers would use different keys.

**Fix:** persistent secret from environment/secret store.

### 7. In-memory mutable global state
`telegram_services`, `scraped_data`, `auth_state` are process-local dictionaries accessed across Flask requests, background threads and asyncio loops.

**Impact:** races, memory leaks, restart loss, multi-worker inconsistency.

**Fix:** persistent campaign store + explicit concurrency control. Use one worker until state is externalized.

### 8. Dry-run defaults to real execution
Web route: `data.get('dry_run', False)`.  
Service default: `dry_run=False`.

**Fix:** default TRUE server-side; real mode requires explicit confirmation tied to the validated target.

### 9. No server-side bounds on action parameters
`start_index`, `batch_size`, `min_delay`, `max_delay`, scrape `limit` are accepted directly.

**Impact:** negative indexing, `random.randint()` crashes when min > max, huge batches, zero delays and accidental overload.

**Fix:** strict schemas/types/ranges and reject invalid values before starting work.

### 10. Sensitive Telegram data persisted/exported in clear text
`Member` contains user id, access hash, username, name and phone. `CSVHandler.save_members()` exports the full dataclass. The upstream repository also tracks runtime `members.csv`, logs, progress and compiled `.pyc` artifacts.

**Fix:** data minimization; exclude phone by default; runtime data outside Git; purge policy; restrictive file permissions.

### 11. Production session path mismatch
`get_telegram_service()` uses `Config.SESSION_DIR/session_<id>` in production, while `session_status()` and `delete_session()` inspect `session_<id>.session` in the current directory.

**Impact:** incorrect status and failure to delete the actual production session.

**Fix:** a single canonical `session_path(session_id)` helper.

### 12. Disconnect on the wrong event loop
The code stops the client's loop, then creates a new event loop and calls `client.disconnect()` there.

**Fix:** disconnect on the owning loop first, then stop/close the loop and join the thread.

## P2 — Important

### 13. Eventlet + asyncio + threads
The app calls `eventlet.monkey_patch()` and also creates native threads plus per-session asyncio loops. This is a fragile concurrency mix.

Eventlet itself officially discourages new usages and is being moved toward retirement/migration.

**Fix:** remove Eventlet; use one asyncio/ASGI architecture.

### 14. Dependencies are completely unpinned
`requirements.txt` lists names only.

**Impact:** installs are not reproducible, compatibility can change overnight, and a dependency audit cannot determine which vulnerable version is actually deployed.

**Fix:** `pyproject.toml` + lockfile/hash-pinned deployment set + CI.

### 15. Telethon v1 is in maintenance mode
Telethon is still actively released, but its v1 line is mostly maintenance and its source moved away from the old GitHub repository.

**Fix:** isolate MTProto behind an adapter, pin the tested version and add compatibility tests.

### 16. CSV upload has no size limit
`/api/upload_csv` checks filename suffix only. No `MAX_CONTENT_LENGTH`, row cap or field cap.

**Impact:** disk/RAM denial of service and pathological parsing.

**Fix:** request-size limit, streaming parser, row/column limits and temporary-file cleanup.

### 17. Spreadsheet formula injection in CSV exports
Telegram-controlled fields are emitted verbatim to CSV.

**Fix:** neutralize leading `=`, `+`, `-`, `@` for spreadsheet-oriented exports.

### 18. Web resume is not persistent
The reusable `AdderService` uses `ProgressTracker`, but the Web route `/api/add_members` duplicates the logic instead of using that service. Web state lives in `scraped_data` RAM.

**Impact:** restart loses the campaign/list and resume state.

**Fix:** one shared campaign engine used by CLI and Web, backed by SQLite/PostgreSQL.

### 19. Post-invite verification is unreliable and expensive
After each add, the Web route sleeps and fetches up to 200 participants, then treats absence from that sample as likely decline/privacy.

**Impact:** false negatives and excessive Telegram calls.

**Fix:** rely on RPC result/state and targeted checks; do not rescan 200 members per invite.

### 20. Full participant scans accumulate everything in RAM
`get_participants(..., limit=None)` builds a full Python list from `iter_participants`.

**Fix:** stream/paginate and cache only what is necessary.

### 21. 2FA detection uses exception text
The code detects 2FA with `'password' in str(e).lower()`.

**Fix:** catch the specific Telethon `SessionPasswordNeededError`.

### 22. Broad exception handling
Many `except Exception` and bare `except:` blocks hide programming errors and leave partial state.

**Fix:** typed exceptions; unexpected failures stop safely and log a redacted structured error.

## P3 — Quality/performance

- `app.py` is roughly 1,744 lines and the single HTML template roughly 1,654 lines.
- Add-member logic is duplicated between `app.py` and `AdderService`.
- No upstream automated test suite/CI is present.
- Naive UTC timestamps are used; prefer timezone-aware UTC.
- Comments such as “FIXED” / “ACTUALLY WORKS” replace evidence that should come from tests.
- Upstream `.gitignore` is far too small: it ignores only `.env`, `members.json`, and one session filename.

## Dependency status on 2026-09-25

Upstream pins **none** of these versions, so the exact deployed versions are unknowable from the repository alone.

Current releases checked:
- Telethon 1.45.0 — 2026-09-10; v1 mainly maintenance.
- Flask 3.1.3 — 2026-02-19.
- Flask-SocketIO 5.6.1 — 2026-02-21.
- python-socketio 5.17.0 — 2026-09-14.
- gunicorn 26.2.0 — 2026-08-24.
- python-dotenv 1.2.3 — 2026-08-16.
- eventlet 0.41.2 — 2026-08-14, but new usage is officially discouraged.

## Required red tests before real credentials

1. `test_api_requires_admin_auth`
2. `test_otp_never_logged`
3. `test_socket_rejects_foreign_origin`
4. `test_dashboard_escapes_telegram_names`
5. `test_delete_session_never_kills_other_python_processes`
6. `test_dry_run_default_is_true`
7. `test_invalid_batch_and_delay_are_rejected`
8. `test_production_session_path_is_canonical`
9. `test_restart_resumes_campaign`
10. `test_upload_size_limit`
11. `test_export_neutralizes_spreadsheet_formula`
12. `test_secrets_sessions_logs_are_gitignored`

## Correction gates

**Gate P0 — before any real key/session:** auth, localhost bind, CORS, OTP redaction, delete-session rewrite, XSS fixes, fail-safe dry-run, input validation.

**Gate P1 — before a real campaign:** persistent DB, shared campaign engine, lifecycle/event-loop fix, canonical session paths, PII cleanup, upload limits, red tests green.

**Gate P2 — hardening:** remove Eventlet, lock dependencies, CI/audit, optimize membership checks, CSP/security headers, structured redacted logs.
