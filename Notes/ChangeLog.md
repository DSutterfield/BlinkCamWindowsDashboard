# Change Log

## 2026-07-24 — Initial project documentation

Added:

- `Developer_Notes.md`
- `ChangeLog.md`
- `Local_Modifications.md`

No source-code changes were made during this documentation step.

## 2026-07-29 — Capability reporting and login setup

Added:

- `capability_probe.py`
- `capability_matrix.py`

Updated:

- `first_login.py`
  - Added input validation.
  - Added required 2FA handling.
  - Save credentials only after successful Blink setup and camera discovery.

Repository maintenance:

- Added `.gitignore` rules for local environments, Visual Studio files,
  credentials, generated reports, and user-specific project settings.