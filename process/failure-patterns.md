# Agent failure patterns

The process-doctor keeps this ledger (`.github/workflows/process-doctor.md`): one row per failure
signature and scope, what caused it and what fixed it. A signature that fails again after its fix
date is a pattern that needs a rule in the Reliability rules block of `AGENTS.md`. Signatures and
counts come from `scripts/agent_failures.py` (`/tmp/gh-aw/agent/failures.md` in a doctor run).

| signature | agents | first seen | last seen | runs (7 d) | cause | fix (date, PR/issue/commit) | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| timeout | site-fixer, region-keeper | 2026-11-23 | 2026-11-23 | 3 (+1 unread) | the CLI step stopped at the workflow's limit (25 and 20 min) with nothing sent: two site-fixer runs on one site-error evening, the second dispatched while the first still ran (45244945359 19:03, 45248741714 19:25 UTC), region-keeper 45227118220 | rule «by 80% of the limit send what is done» and a workflow-change issue for one site-fixer at a time (2026-11-24, this PR) | open |
| unknown | every agent whose log the doctor did not read | 2026-11-24 | 2026-11-24 | 35 | `gh api …/jobs/<id>/logs` refused the log («terminal escape sequences»), so 39 of 41 failed runs got no signal lines and fell to `unknown`; 23 of them are the z.ai outage below | reliability item for `scripts/agent_failures.py` (2026-11-24, this PR) | open |
| safe-outputs | pr-fixer, issue-worker | 2026-11-22 | 2026-11-22 | 4 | not read: the safe-output job's `Process Safe Outputs` failed three times in 40 minutes on the PR fixer (45009763031, 45011310218, 45013053478) and once on the issue-worker (45047520996), after the agent step | none; 31 good PR-fixer runs since. The next one's signal lines should name the safe output | open |
| provider-overload | all z.ai agents | 2026-11-23 | 2026-11-24 | 25 (23 on 11-24, 01:39 to 09:01 UTC) | z.ai answers 529 [1305] «temporarily overloaded» for one model at peak hours; each 2-minute failure also woke the CI doctor again through its `workflow_run` trigger (#96) | fallback-models glm-5.3, glm-5.1 and CLAUDE_CODE_MAX_RETRIES 6 (2026-11-24, acb72e9); green after it: PR fixer 45379348606, 45380229047, 45384342659 | fixed |
| timeout | issue-worker | 2026-11-24 | 2026-11-24 | 1 | the 30-minute step limit stopped a 32-minute session finishing PR #94 | timeout-minutes 30 -> 50 (2026-11-24, fccf91c) and a reliability rule | fixed |
| parser-crash | issue-worker, long sessions | 2026-11-24 | 2026-11-24 | 2 | gh-aw v1.2.2 «Parse agent logs for step summary» throws «Maximum call stack size exceeded» after the agent's work went out; the conclusion job's mirror step `Handle agent failure` still made the script count the run as failed (parser-doctor 45288784687, 45296603145) | not a failure: agent-health and agent_failures.py leave that step out (2026-11-24, fccf91c); the mirror goes with the `scripts/agent_failures.py` item | outside |

## Archive
