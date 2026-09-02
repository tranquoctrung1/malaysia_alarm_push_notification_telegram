---
name: security-config-review
description: Security and correctness review checklist for the alarm bot — credential handling, SQL injection, exception safety, and Telegram rate-limit compliance. Use before approving any diff to telegram_improved.py, .env handling, or deploy config.
---

# Security & Config Review Checklist

## Why this order of priority
In an unattended bot with DB + bot-token credentials and a public-facing Telegram surface, the failure modes that matter most are: leaked secrets, injectable queries, and crashes that stop alarms from ever being delivered. Style issues don't cause incidents; these do.

## 1. Credential exposure
- No `.env` values (`TG_TOKEN`, `SQL_PASSWORD`, `MONGO_URI`, etc.) hardcoded or logged in plaintext. Check any new `logger.info/debug` call doesn't print a full connection string or token.
- `.env` stays in `.gitignore`; don't add code that writes secrets to a world-readable file.

## 2. SQL injection
- Every SQL query must use `?` parameter placeholders with values passed via the `cursor.execute(query, (params,))` tuple — never f-string/`.format()`/`%`-interpolate a value into the query text.
- Watch for indirect injection: values sourced from Mongo (e.g. `device_id`, `chat_id`) that later flow into a SQL query.

## 3. Exception safety / "never stuck"
- Every alarm-processing path must reach the `last_index` update, even on error — verify no new `return`/`continue` bypasses the `finally` block in `process_alarms`.
- New I/O calls (SQL, Mongo, Telegram) must be wrapped so a failure logs and degrades gracefully rather than propagating up and killing `start_monitoring`'s loop.

## 4. Telegram rate limits
- All outbound messages must go through `send_telegram_safe` (handles `RetryAfter`/flood control and the 0.5s inter-message delay) — flag any direct `bot.send_message(...)` call that bypasses it.
- Broadcast-style features (sending to many chat_ids) must not remove the per-message delay just to go faster.

## Severity labeling
When reporting findings, mark each CONFIRMED (reproduced/clearly reasoned from code) or PLAUSIBLE (suspected but unverified) — don't present a guess as a confirmed bug.
