---
description: |
  Investigates failed runs of CI, Update data and Agent PR gate on main and files one
  issue per distinct cause with the evidence and the fix it suggests.
on:
  workflow_run:
    workflows: ["CI", "Update data", "Agent PR gate"]
    types: [completed]
    branches: [main]
if: ${{ github.event.workflow_run.conclusion == 'failure' }}
permissions:
  actions: read
  contents: read
  issues: read
  pull-requests: read
strict: true
network: defaults
tools:
  github:
    toolsets: [default, actions]
safe-outputs:
  create-issue:
    title-prefix: "[ci-doctor] "
    labels: [agent, ci]
    max: 1
    deduplicate-by-title: true
    expires: 7d
  add-comment:
    max: 1
    target: "*"
  noop:
timeout-minutes: 10
---

# CI doctor

Read the Process block in `AGENTS.md` first: it says what the team needs from you this week.

Run: ${{ github.event.workflow_run.html_url }} (run id ${{ github.event.workflow_run.id }},
head ${{ github.event.workflow_run.head_sha }}).

1. Read the failed jobs' logs and find the first real error.
2. Classify it: parser broke on new gov.pl HTML, gov.pl unreachable (transient), test failure,
   workflow or permission problem, or Pages deployment problem.
3. Search open issues titled "[ci-doctor]". If one has the same cause, add one comment with this
   run's link and stop.
4. A single transient network error with the next run green: call `noop`.
5. Otherwise create one issue: the error line, the cause with a confidence level, and the fix.
   When the parser broke, say that the parser doctor was dispatched and should fix it.
