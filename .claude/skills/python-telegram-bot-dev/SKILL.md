---
name: python-telegram-bot-dev
description: How to extend telegram_improved.py's monitoring loop, alarm processing, and Telegram send logic while preserving this bot's retry, health-check, and rate-limit conventions. Use whenever adding/changing bot features — new message fields, new alarm sources, altered scan cadence, chat routing changes, or send-failure handling.
---

# Python Telegram Bot Dev

## Why these patterns exist
This bot runs unattended for long periods (systemd service). Every pattern below exists to survive that: never crash the loop, never get stuck on one alarm, never get banned by Telegram for flooding.

## Monitoring loop shape
`start_monitoring()` is a `while self.is_running` loop with a fixed target cadence (`SCAN_INTERVAL`). It measures elapsed time each iteration and sleeps `max(1, SCAN_INTERVAL - elapsed)` — this keeps cadence stable even if a scan takes a while. If you add work inside the loop body, keep it inside the existing `try/except` so one bad iteration doesn't kill the process.

## The "never stuck" rule
`process_alarms` updates and persists `self.last_index` in the `finally` block of every alarm, even on failure. This is deliberate: if an alarm can never be processed (bad chat_id, malformed data), the bot must still move past it next scan instead of retrying it forever. Any new alarm-handling code must preserve this — don't add a `continue` or early return that skips the `last_index` update.

## Retry conventions
- SQL fetch: bounded retries (`MAX_RETRIES`) with a fixed 5s backoff between attempts, then give up and return `[]` for this cycle (next cycle picks up from unchanged `last_index`).
- Telegram send: `RetryAfter` (flood control) is handled by sleeping `retry_after + 1`s and recursing up to `MAX_RETRIES`; if the wait exceeds 30s, skip the message rather than blocking the whole batch.
- New retry logic should follow the same shape: bounded attempts, explicit give-up path, never an unbounded loop.

## Rate limiting
`send_telegram_safe` sleeps 0.5s after every successful send to stay under Telegram's per-second limits. If you add a new send path (e.g. broadcast to `get_all_chat_ids()`), reuse `send_telegram_safe` rather than calling `bot.send_message` directly — it's the only place flood control is handled.

## Health check
`health_check()` runs every 10 loop iterations and pings MongoDB/SQL/Telegram independently, each wrapped in its own try/except so one dead dependency doesn't hide the others' status. New dependencies added to the bot should get the same isolated-check treatment.

## Message format
Messages are HTML-formatted (`parse_mode='HTML'`) with a fixed emoji/label structure (🚨 title, 🆔 Site ID, 📍 Site Name, 📄 Description, 📊 Priority, ⏰ Time). New fields should slot into this structure rather than introducing a different format, so operators reading Telegram don't see inconsistent alarms.

## Logging convention
loguru with emoji-prefixed Vietnamese messages (✅ success, ❌ error, ⚠️ warning, ℹ️ info). Match this style for new log lines — mixing languages/styles makes grepping logs harder for the operator.
