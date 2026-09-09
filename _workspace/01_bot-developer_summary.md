# 01 — bot-developer: fix last_index regression (5004518 → 4569137)

## Root cause

Not a logic bug in the fetch/process path. `fetch_sql_alarms` uses
`WHERE A.AlarmIndex > ? ORDER BY A.AlarmIndex ASC` and `process_alarms` assigns
`self.last_index = alarm['index']` in ASC order inside a `finally`, so within one
process `last_index` is strictly monotonic — no code path lowers it.

The regression comes from **two processes running concurrently against the same
`last_index.json`** (old instance not fully killed on service restart, a manual exe
launch alongside the service copy, or a duplicate scheduled task). Each process:

- loads `last_index` once in `__init__` and never reloads it, and
- `save_last_index()` did a blind full overwrite with no locking.

So process A can race ahead to 5004518 and save, while process B — still holding a
stale in-memory value near 4569137 — writes that value over A's. Observed drop.

## Changes to `telegram_improved.py`

1. **Single-instance guard** (new module-level `acquire_single_instance_lock()` /
   `release_single_instance_lock()`, plus `LOCK_FILE = JSON_DB + '.lock'`).
   OS-level advisory lock on 1 byte of a lockfile sitting next to `JSON_DB`
   (`msvcrt.locking(LK_NBLCK)` on Windows, `fcntl.flock(LOCK_EX|LOCK_NB)` elsewhere),
   non-blocking. The file handle is kept in a module global so the lock survives the
   function return; the PID + timestamp are written into the lockfile for diagnosis.
   Called at the top of `main()`, **before** `UtiliCoreStableBot()` (which is where
   `load_last_index()` runs). If the lock can't be taken, it logs a CRITICAL naming
   the lockfile and `sys.exit(1)` — no duplicate instance, no DB/Telegram connect.
   Released in a `finally` around the whole run.

   The lock is held by the OS handle, so it disappears automatically if a process is
   killed — no stale-PID cleanup logic needed.

2. **Atomic `save_last_index()`** — writes to `.<name>.<pid>.tmp` in the same
   directory, `flush()` + `os.fsync()`, then `os.replace()` over `JSON_DB`. Prevents a
   truncated/corrupt JSON (which `load_last_index` would fall back to index 0 on) if
   the process dies mid-write. Secondary hardening, not the primary bug.

No changes to retry/backoff, health check, alarm processing, or the
"always advance `last_index` in `finally`" behavior.

## Verification done

Standalone harness against a temp dir:
- process 1 acquires → `True`; a second OS process on the same lockfile → `False`;
  after release, a third process → `True`.
- `save_last_index(5004518)` produces valid JSON, no leftover `.tmp`.

Not yet run end-to-end against live SQL/Mongo/Telegram.

## Notes for downstream

- **qa-tester:** worth exercising (a) launching the exe twice — the second must exit
  immediately with the CRITICAL log and never touch `last_index.json`; (b) service
  restart with the old process still alive; (c) kill -9 mid-write, then confirm
  `last_index.json` still parses and does not reset to 0.
- **deploy-ops-engineer:** a new file `last_index.json.lock` appears next to
  `JSON_DB` (same dir resolution as before, incl. frozen-exe path). If the service
  account can write `JSON_DB` it can write this. `msvcrt`/`fcntl` are stdlib —
  no PyInstaller hidden-import needed, but the imports are inside the functions,
  so confirm the spec's analysis still picks up `msvcrt` on the frozen build.
- Operationally, the guard turns a silent data-corruption race into a loud startup
  failure — check for the "Đã có instance khác" CRITICAL line if the bot won't start.
