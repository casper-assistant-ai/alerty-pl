---
description: |
  Weekly: adds tests for parser cases that are not covered yet, using real RCB pages
  saved as fixtures. Opens one PR for the Agent PR gate.
on:
  schedule:
    - cron: "22 10 * * 0"
  workflow_dispatch:
permissions:
  contents: read
  pull-requests: read
strict: true
engine:
  # Temporary (26.11.2026, CAS-397): z.ai 5-hour quota ran out at 08:50 Warsaw, reset 12:03.
  # Copilot runs the agents until then; back to claude + glm-5.4 after the reset.
  id: copilot
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
  # One self-closing issue per workflow comes from agent-health.yml instead of an issue per failure.
  report-failure-as-issue: false
  # Detector failures stay in the run diagnostics; no ever-growing «[aw] Detection Runs» tracker.
  threat-detection:
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
