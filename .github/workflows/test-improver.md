---
description: |
  Weekly: adds tests for parser cases that are not covered yet, using real RCB pages
  saved as fixtures. Opens one PR for the Agent PR gate.
on:
  schedule: weekly
  workflow_dispatch:
permissions:
  contents: read
  pull-requests: read
strict: true
engine:
  id: claude
  model: glm-5.4
  env:
    ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic
imports:
  - shared/zai.md
network:
  allowed: [defaults, python, "www.gov.pl"]
tools:
  bash: ["python3:*", "curl:*", "cat:*", "ls:*", "grep:*", "head:*", "tail:*", "wc:*"]
  edit:
safe-outputs:
  create-pull-request:
    title-prefix: "[test-improver] "
    labels: [agent, tests]
    draft: false
    allowed-files: ["tests/**"]
    protected-files: blocked
    expires: 7d
  noop:
    report-as-issue: false
timeout-minutes: 20
---

# Test improver

Read `AGENTS.md` and `tests/test_rcb.py`. Pick up to three alert kinds from
`docs/data/alerts.json` that no test covers yet (for example a nationwide alert, a drill
with a time window, a weather or fire alert, an alert with several updates). Save each
gov.pl page into `tests/fixtures/` and add a test that checks category, regions, updates and
status. Do not change `scripts/`; if a test shows a parser bug, keep the test, mark it
`@unittest.expectedFailure` and describe the bug in the PR body for the parser doctor.
Run the tests, then open one PR, or call `noop` when coverage is already good.
