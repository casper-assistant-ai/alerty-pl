# Agent failure patterns

The process-doctor keeps this ledger (`.github/workflows/process-doctor.md`): one row per failure
signature and scope, what caused it and what fixed it. A signature that fails again after its fix
date is a pattern that needs a rule in the Reliability rules block of `AGENTS.md`. Signatures and
counts come from `scripts/agent_failures.py` (`/tmp/gh-aw/agent/failures.md` in a doctor run).

| signature | agents | first seen | last seen | runs (7 d) | cause | fix (date, PR/issue/commit) | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| provider-overload | all z.ai agents | 2026-11-23 | 2026-11-24 | 25 | z.ai answers 529 [1305] «temporarily overloaded» for one model at peak hours | fallback-models glm-5.3, glm-5.1 and CLAUDE_CODE_MAX_RETRIES 6 (2026-11-24, acb72e9) | fixed |
| timeout | issue-worker | 2026-11-24 | 2026-11-24 | 1 | the 30-minute step limit stopped a 32-minute session finishing PR #94 | timeout-minutes 30 -> 50 (2026-11-24, fccf91c) and a reliability rule | fixed |
| parser-crash | issue-worker, long sessions | 2026-11-24 | 2026-11-24 | - | gh-aw v1.2.2 «Parse agent logs for step summary» throws «Maximum call stack size exceeded» after the agent's work went out | not a failure: agent-health and agent_failures.py leave that step out (2026-11-24, fccf91c) | outside |

## Archive
