---
name: windows-build-deploy
description: Build/packaging checklist for build.bat (PyInstaller), telegram_improved.spec, telegram-bot.service (systemd), and .env config for the alarm bot. Use for build failures, packaging changes, new deployment targets, or adding/removing environment variables.
---

# Windows Build & Deploy

## Why frozen-path handling matters
`telegram_improved.py` computes `_exe_dir` differently depending on whether it's running as a script or as a PyInstaller-frozen exe (`sys.frozen`), because `JSON_DB` and relative paths (like `logs/`) need to resolve next to the actual executable, not next to a temp extraction dir. Any build change that affects working directory or entrypoint must be re-verified against both run modes.

## build.bat / .spec checklist
- Confirm `requirements.txt` is fully reflected in the `.spec`'s hidden imports if PyInstaller misses dynamic imports (common with `pyodbc`, `motor`/`pymongo` C extensions, `loguru`).
- ODBC Driver 18 for SQL Server must be present on the target machine — packaging the Python code doesn't bundle the system ODBC driver; document this as an external dependency, don't try to embed it.
- After a `.spec` change, do a clean build (`build.bat`, removing prior `dist/`/`build/` output) rather than an incremental one — stale PyInstaller caches hide real packaging breaks.

## .env checklist
- Every var read via `os.getenv(...)` in code must appear in the README's env-var table with its default.
- Required vars with no sane default (`TELEGRAM_BOT_TOKEN`, `SQL_SERVER`, `SQL_DATABASE`, `SQL_USER`, `SQL_PASSWORD`) must fail fast with a clear error (see `TG_TOKEN` validation in `__init__`) rather than silently connecting with empty credentials.
- Never commit real values — `.env` must stay gitignored; if you add a new secret var, remind the user to keep it out of version control.

## systemd service checklist
- `telegram-bot.service` is a template — `your_username` and path placeholders must stay generic. Don't replace them with a real machine's paths in the committed file.
- After editing the service file, the deploy steps are: copy to `/etc/systemd/system/`, `daemon-reload`, `enable`, `restart` (not just `start`, if already running) to pick up changes.

## Log rotation
Managed entirely by loguru's `logger.add(...)` config in the script (daily rotation at 00:00, 30-day retention, zip compression) — there's no external logrotate config to keep in sync. If retention/rotation requirements change, that config block is the only place to edit.
