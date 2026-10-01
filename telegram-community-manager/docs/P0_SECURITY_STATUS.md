# P0 security status

Date: 2026-09-25

## Green controls implemented

- DRY_RUN is true by default.
- Admin-only API protection uses a Bearer token with constant-time comparison.
- ADMIN_API_KEY must be at least 32 characters when configured.
- No permissive CORS middleware is enabled.
- The API binds to 127.0.0.1 by default through configuration.
- Health/config responses do not expose Telegram secrets.
- Secret redaction utility covers OTP/code, API hash, bot token, 2FA/password patterns.
- Telegram session paths reject traversal-style names.
- POSIX session directories/files are hardened to 0700/0600.
- No taskkill/subprocess-run mechanism exists in the clean application code.
- Flask runtime-random SECRET_KEY issue is eliminated by not using Flask cookie sessions in the clean API.

## Test evidence

Local security test run:

```
7 passed in 0.26s
```

The first test invocation failed during collection because PYTHONPATH was not set for the temporary test workspace. After correcting the test environment, all seven security tests passed.

## Remaining before real Telegram credentials

- Wire the redacting filter into the application logger.
- Implement the Telegram client/session lifecycle using secure_session_path().
- Add explicit protected endpoints for login/start/pause/resume.
- Add typed Telethon authentication and RPC errors.
- Add transactional persistent campaign storage.
- Pin/lock tested dependency versions and run dependency vulnerability checks.
