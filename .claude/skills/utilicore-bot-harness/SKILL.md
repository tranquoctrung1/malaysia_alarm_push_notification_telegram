---
name: utilicore-bot-harness
description: Orchestrates the UtiliCore Telegram alarm bot's 5-agent team (bot-developer, db-integration-specialist, deploy-ops-engineer, code-reviewer, qa-tester) for any nontrivial work on telegram_improved.py or its build/deploy config. Use for feature requests, bugfixes, refactors, DB query changes, build/deploy changes touching this project — and for follow-ups: "redo", "update", "fix just the X part", "improve on the last result". Not needed for a one-line question that doesn't touch code.
---

# UtiliCore Bot Harness

## Why a team, not a solo edit
This bot spans three trust-sensitive surfaces at once — SQL Server, MongoDB, and Telegram delivery — where a change in one place (a query field rename, a message format tweak) silently breaks another. The team exists to catch that: a specialist per surface, a reviewer for security/correctness, and QA that checks the seams between them, not just each piece alone.

## Phase 0: Context check (run first, every time)
Check for `_workspace/` in the project root.
- **No `_workspace/`** → initial run. Proceed to Phase 1.
- **`_workspace/` exists + user asks to redo/update/fix a specific part** → partial rerun: only recall and re-task the relevant agent(s), skip full team spin-up for untouched parts.
- **`_workspace/` exists + user gives a genuinely new request** → move `_workspace/` to `_workspace_prev/`, start fresh.

## Phase 1: Scope the request
Classify the request into one or more of: feature/bugfix (bot-developer lead), DB/query change (db-integration-specialist lead), build/deploy change (deploy-ops-engineer lead). Most requests need bot-developer + code-reviewer at minimum; DB-touching or deploy-touching requests pull in the matching specialist. qa-tester runs on any change that touches the SQL→Mongo→Telegram data path.

## Phase 2: Team stand-up
**Execution mode: agent team.**

Create the team with the agents relevant to the scoped request (not always all 5 — e.g. a pure `.env` var addition doesn't need `db-integration-specialist`). Assign tasks via TaskCreate with dependencies:

```
bot-developer / db-integration-specialist / deploy-ops-engineer (implement, parallel if independent)
        -> code-reviewer (reviews each diff, SendMessage back to author on findings)
        -> qa-tester (verifies the integrated flow once review-approved changes land)
```

Data flow: authors write diffs directly to `telegram_improved.py` / config files (the real deliverable). Working notes go to `_workspace/{phase}_{agent}_{artifact}.md` (e.g. `01_bot-developer_summary.md`, `02_code-reviewer_findings.md`, `03_qa_report.md`) so the trail survives for audit and reruns.

## Phase 3: Review & fix loop
code-reviewer's findings go by SendMessage to the authoring agent, not through the orchestrator — agents self-coordinate on fixes. The orchestrator only re-enters if code-reviewer escalates a serious security issue directly, or if an agent reports being blocked.

## Phase 4: QA gate
qa-tester runs incrementally per finished module (not once at the very end) and reports pass/fail with repro scenarios to whichever agent owns the affected code. A module isn't "done" until qa-tester has checked it against `bot-e2e-verification`'s boundary-crossing checklist.

## Error handling
- Any agent stuck/failing: one retry with the same task; on second failure, report the gap explicitly in the final summary rather than silently dropping it.
- Conflicting recommendations between two agents (e.g. bot-developer vs code-reviewer on message format): surface both positions to the user rather than picking silently.

## Phase 5: Wrap-up
Summarize what changed, what qa-tester verified, and what (if anything) remains open. Ask the user for feedback on the harness itself (agent split, workflow order) — but only note it as worth revisiting if the same friction comes up twice.

## Test scenarios
- **Happy path**: "Add a new field to the alarm message showing SITELIST.Region" → bot-developer edits SQL query + message template → code-reviewer checks param binding stays intact → qa-tester verifies the new field flows from SQL row to message string without a None-rendering bug.
- **Error path**: db-integration-specialist can't determine a Mongo field's type without live DB access → surfaces uncertainty to the user instead of guessing, per its error-handling protocol.
