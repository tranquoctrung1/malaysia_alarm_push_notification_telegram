---
name: bot-e2e-verification
description: End-to-end verification method for the alarm bot's SQL-to-Mongo-to-Telegram pipeline — checks that data shapes actually match across boundaries, not just that each piece runs in isolation. Use after any change touching the alarm fetch, chat_id resolution, or message-send path, before calling the feature done.
---

# Bot End-to-End Verification

## Why boundary-crossing checks, not unit checks
The bot's biggest risk isn't any single function failing — it's two correct-looking pieces disagreeing about a shape at the seam between them (SQL row → alarm dict → Mongo query input → message template). Verify the seams, not just the pieces.

## Checklist per change
1. **SQL row → alarm dict**: confirm every field accessed downstream (`alarm['time']`, `alarm['device_id']`, `alarm['priority']`, `alarm['desc']`) is actually produced by `fetch_sql_alarms`'s dict construction, with the same key names.
2. **alarm dict → Mongo query input**: `get_target_chat_ids(device_id)` calls `int(device_id)` — confirm the SQL column feeding `device_id` (`A.Id`) is compatible with int conversion, and that the `except` around it doesn't swallow a real config problem silently.
3. **Mongo pipeline output → message template**: the message string interpolates `alarm['site']`, `alarm['desc']`, `alarm['device_id']`, `priority_tag`, `alarm_time` — confirm each is never `None` in a way that renders literally as `None` in a message users see (check the `or "N/A"` / `or "Không có mô tả"` fallbacks stay in place).
4. **Type mismatches**: `alarm['time'].strftime(...)` only works if `time` is a `datetime` — verify the `isinstance` guard before it stays, since pyodbc can return other types for some SQL column configs.

## How to verify without live DB access
- Static: trace the exact field names end-to-end through the diff, confirm no rename broke a downstream reference.
- Syntax/import check: `python -m py_compile telegram_improved.py` catches at least syntax errors and undefined-name issues at parse time (not full type safety, but a cheap first gate).
- Log-based: if the bot can be run against a test/staging DB, watch `logs/alarm_bot_*.log` for the exact success/failure counts and warning patterns (`✅ Alarm ... Gửi thành công`, `⚠️ ... Không tìm thấy chat_id`) to confirm the flow actually executed as expected.

## Reporting
State pass/fail per checklist item with the concrete line reference. If something can't be verified (e.g. no DB access in this environment), say so explicitly rather than assuming it passes.
