---
name: mongodb-sql-integration
description: Schema relationships and query patterns bridging SQL Server (ALARMLOG/SITELIST) and MongoDB (t_ranges/t_telegram_ranges/t_telegrams) in the alarm bot. Use for any change to the SQL alarm query, the Mongo aggregation pipeline that maps device_id to chat_id, or connection pooling for either DB.
---

# MongoDB + SQL Integration

## Why read this before touching a query
The device_id → chat_id resolution is the single most failure-prone part of this bot: get it wrong and alarms silently go to nobody, or to the wrong operators. It happens once per alarm via a MongoDB aggregation pipeline against three collections.

## Schema relationships
- **SQL Server**: `ALARMLOG` (AlarmIndex, AlarmTime, Description, HighPriority, Id) LEFT JOIN `SITELIST` (Name) on `Id`. `AlarmIndex` is the monotonic cursor (`last_index`).
- **MongoDB `t_ranges`**: each doc defines either a numeric `start`/`end` device_id range, or (`isCheckList: true` + `listSiteId`, a comma-separated string of device ids matched via regex).
- **MongoDB `t_telegram_ranges`**: join table, `rangeId` → `t_ranges._id`, `telegramId` → `t_telegrams._id`.
- **MongoDB `t_telegrams`**: has `chatId`, the actual Telegram chat to notify.

## The two-branch match logic
A device_id matches a range doc if EITHER:
1. `start <= device_id <= end`, regardless of `isCheckList`, OR
2. `isCheckList == true` AND `device_id` appears in `listSiteId` (comma-separated string, matched with a word-boundary-ish regex `(^|,)\s*{id}\s*(,|$)`).

If you change this logic, verify both branches still work — it's easy to accidentally require both conditions (AND) instead of either (OR), which would silently drop the checklist-based routing.

## Pipeline shape to preserve
`$match` (the two-branch condition above) → `$lookup` into `t_telegram_ranges` → `$unwind` → `$lookup` into `t_telegrams` → `$unwind` → `$project` to `chat_id`. Each `$lookup`+`$unwind` pair is how the join table pattern is expressed in Mongo — don't collapse them into a single `$lookup` unless you also add pipeline-style lookup with matching stages.

## Connection pooling
- SQL: `pyodbc.connect()` is reused via `self.sql_conn`, liveness checked with a cheap `SELECT 1` (`_is_sql_alive`). Reconnect happens lazily on failure, not proactively — keep it lazy, a connection-check-every-call approach adds latency to every alarm.
- Mongo: `AsyncIOMotorClient` with `maxPoolSize=10`, connected once at startup and pinged via `admin.command('ping')`. Don't recreate the client on every query — it manages pooling internally.

## SQL injection guard
`fetch_sql_alarms` uses parameterized queries (`WHERE A.AlarmIndex > ?`, params passed as a tuple). Any new SQL query must keep parameter binding — never interpolate a value into the query string directly.

## Common bug patterns to check for
- Forgetting `list(set(chat_ids))` dedup when a device_id matches multiple ranges routing to the same chat.
- Treating `alarm['time']` as always a `datetime` — the SQL driver can return other types depending on column type; guard with `isinstance` before `.strftime()`.
- Assuming `device_id` is always numeric — `int(device_id)` will throw on malformed data; that's caught by the outer try/except in `get_target_chat_ids`, don't remove it.
