# Feature parity target

The clean-room implementation targets the useful behavior observed in the reference project while keeping our own architecture and safety defaults.

- Telegram user session via MTProto
- Target group validation
- TXT / CSV / XLSX import
- Username normalization and deduplication
- Dry-run enabled by default
- Persistent campaign state
- Resume after restart
- FloodWait handling
- Privacy / invalid-user classification
- Already-member detection
- Invite-link fallback
- Pause / resume
- CSV / JSON reports
- Web health and configuration status
- Secrets only from environment variables

No upstream source code is copied into this project.
