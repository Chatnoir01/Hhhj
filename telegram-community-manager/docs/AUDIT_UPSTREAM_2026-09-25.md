# Security & dependency audit — upstream Telegram Member Migration Tool

Audit date: 2026-09-25
Upstream: Nayan-Bebale/Telegram-Member-Migration-Tool
Pinned commit: 0619887480abe6a19b6652e8a8aafe6ceaa93a66

## Verdict

Do not put production Telegram credentials into the upstream web app as-is. The functional core is reusable as a design reference, but the web/auth/session layer needs hardening before real credentials or real member data are used.

## Critical

1. Authentication code is logged in plaintext.
   - app.py logs the Telegram login code submitted by the user.
   - Fix: never log OTP/code/password/token/API hash; add a redaction filter and tests.

2. Session-deletion endpoint kills every python.exe process on Windows.
   - app.py invokes taskkill /F /IM python.exe.
   - This can terminate unrelated Python programs and is an unsafe destructive side effect.
   - Fix: remove subprocess/taskkill entirely; close only the Telethon client/session owned by this process.

3. Web API has no application-level authentication/authorization.
   - Sensitive routes can initiate Telegram login, submit OTP/2FA, scrape, add members, delete sessions, upload files, etc.
   - A browser cookie session ID is not authorization.
   - Fix: bind the dashboard to localhost by default; require an admin secret/login for remote deployment; authorize every mutating route.

## High

4. Socket.IO accepts every origin.
   - cors_allowed_origins="*".
   - Fix: same-origin by default; explicit allow-list only when required.

5. No CSRF protection is visible on state-changing Flask routes.
   - Fix: CSRF tokens or strict same-origin + authenticated API design; reject unexpected Origin/Content-Type.

6. Flask SECRET_KEY is regenerated on every process start.
   - Existing session cookies become invalid and multi-worker deployments cannot share sessions.
   - Fix: load a persistent high-entropy secret from environment/secret store.

7. Telegram session files are plaintext SQLite session credentials on disk.
   - Possession of a valid session file can grant account access.
   - Fix: private directory, restrictive permissions, never commit/back up casually; optional StringSession encrypted at rest if remote deployment is required.

8. /api/session_status returns the authenticated account phone number.
   - Fix: do not expose phone number to the frontend unless explicitly needed; mask it.

9. Scraped member data includes user IDs/access hashes and is persisted/exported.
   - Upstream even previews access_hash fragments in the UI.
   - Fix: minimize collection; never display access hashes; encrypt/restrict exports; retention/purge controls.

10. Global in-memory dictionaries hold auth futures, Telegram clients, and scraped member data.
    - Unsafe with multiple workers/restarts; memory leaks/stale sessions possible.
    - Fix: one controlled worker for Telegram operations + persistent DB for campaign state; ephemeral auth state with TTL.

## Medium

11. Dry-run is opt-in rather than safe-by-default in upstream web/API.
    - /api/add_members defaults dry_run=False.
    - Fix: DRY_RUN=true globally by default and require an explicit activation step for real writes.

12. Broad `except Exception` handling is pervasive.
    - This conflates auth failures, privacy errors, RPC failures, programming bugs, and I/O failures.
    - Fix: catch explicit Telethon/RPC exceptions and map them to typed statuses.

13. 2FA detection relies on searching "password" in an exception string.
    - Fragile across versions/localization.
    - Fix: catch SessionPasswordNeededError explicitly.

14. Existing-member checks can fetch the full participant list.
    - Expensive and potentially unavailable for large/restricted groups.
    - Fix: use targeted membership checks when possible and cache known results.

15. Post-invite verification fetches the last 200 participants.
    - It does not prove the invited member is absent; participant ordering is not a reliable membership oracle.
    - Fix: use a direct participant/membership query for the specific user.

16. Progress persistence is a single JSON file.
    - No locking/atomic replace; concurrent operations can corrupt or overwrite state.
    - Fix: SQLite/PostgreSQL transactions; at minimum write-temp + fsync + atomic rename.

17. Uploaded CSV handling has minimal validation.
    - Extension-only check; no explicit size/row limit and uploaded files remain on disk.
    - Fix: MIME/structure validation, MAX_CONTENT_LENGTH, row cap, generated filenames, retention cleanup.

18. User-supplied values and raw exception strings are emitted to browser/logs.
    - Fix: structured safe error messages; server-side detailed exceptions without credentials/PII.

19. Production paths use /tmp for Telegram sessions/data.
    - Ephemeral storage can unexpectedly destroy session/progress after restart.
    - Fix: explicit persistent volume or intentionally ephemeral encrypted session strategy.

20. No visible automated test suite in upstream.
    - Fix: pytest + pytest-asyncio; mock Telegram RPC; security regression tests.

## Dependency audit

Upstream requirements are completely unpinned:
- telethon
- python-dotenv
- Flask
- flask-socketio
- python-socketio
- gunicorn
- eventlet

This makes builds non-reproducible and allows future breaking releases to enter silently.

Telethon's current stable v1 documentation is 1.45.0 and explicitly recommends constraining dependency versions. The upstream code is written against Telethon v1 APIs, so an uncontrolled migration to v2 should not happen during security cleanup.

Actions:
- Pin compatible direct dependencies.
- Generate a lock/constraints file with hashes for deployment.
- Add Dependabot/Renovate and CI dependency audit.
- Test Python 3.11/3.12/3.13/3.14 as appropriate before claiming compatibility.
- Evaluate removal of eventlet. The current architecture mixes Flask threads, eventlet Socket.IO, and asyncio/Telethon loops, which substantially increases concurrency complexity.

## Functional corrections

Priority P0:
- Remove OTP logging.
- Remove taskkill.
- Add dashboard/API authentication.
- Same-origin Socket.IO.
- Persistent SECRET_KEY.
- DRY_RUN true by default.
- Protect Telegram session files.

Priority P1:
- Replace exception-string 2FA detection.
- Typed Telegram error mapping.
- Direct per-user membership verification.
- Persistent transactional campaign database.
- File upload limits/cleanup.
- Remove access_hash/phone exposure from UI.

Priority P2:
- Refactor the ~75 KB app.py into routes/services/workers.
- Replace global dictionaries with explicit state objects/repository.
- Add structured redacted logging.
- Add health/readiness endpoints.
- Add unit/integration tests and CI.
- Add Docker with non-root user and persistent data volume.

## Recommended disposition

Keep our existing clean project as the production base. Port only the useful Telegram behavior after tests are written. Do not deploy or enter real API_HASH/OTP/2FA into the upstream web application before P0 is green.
