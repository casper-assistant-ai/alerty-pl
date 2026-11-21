---
description: |
  Daily health report of the alerty-pl service and its agent team: data freshness,
  alerts parsed, regions unmatched, agent PRs merged or stuck, failures. One issue,
  replacing yesterday's.
on:
  schedule: daily
  workflow_dispatch:
permissions:
  contents: read
  actions: read
  issues: read
  pull-requests: read
strict: true
network: defaults
tools:
  bash: ["cat", "jq", "ls", "head", "wc", "date"]
  github:
    toolsets: [default, actions]
safe-outputs:
  create-issue:
    title-prefix: "[daily-status] "
    labels: [agent, report]
    max: 1
    close-older-issues: true
    expires: 3d
  noop:
    report-as-issue: false
timeout-minutes: 10
---

# Daily status

Read the Process block in `AGENTS.md` first: it says what the team needs from you this week.

Write a short status report for the last 24 hours (UTC) of this repository.

- **Service:** `docs/data/meta.json` (`checked_at`, `count`, `active`); count of failed and
  successful runs of "Update data"; whether the last run is older than 30 minutes.
- **Data:** alerts added in the last 24 h by category (from `docs/data/alerts.json`),
  and the items in `docs/data/unmatched.json`.
- **Agent team:** PRs opened, merged and still open by each agent (title prefixes
  `[parser-doctor]`, `[region-keeper]`, `[test-improver]`, `[docs-keeper]`), issues by
  `[ci-doctor]` and `[triage]`, and any PR labelled `needs-attention`.
- **Next:** at most three things the agents should do next.

Plain Markdown, short bullet lists, no tables over 6 rows.
