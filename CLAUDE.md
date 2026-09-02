## Harness: UtiliCore Telegram Alarm Bot

**Goal:** Coordinate feature/bugfix/DB/deploy work on `telegram_improved.py` across SQL Server, MongoDB, and Telegram without breaking the seams between them.

**Trigger:** For any nontrivial work on `telegram_improved.py` or its build/deploy config (features, bugfixes, refactors, DB query changes, build/deploy changes) — including follow-ups ("redo", "update", "fix just X") — use the `utilicore-bot-harness` skill. Simple questions can be answered directly.

**Change history:**
| Date | Change | Target | Reason |
|------|--------|--------|--------|
| 2026-07-03 | Initial harness setup | all (5 agents + orchestrator skill) | User requested full agent-team harness |
