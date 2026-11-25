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
  id: claude
  model: glm-5.4
  # z.ai answers 529 (1305 «temporarily overloaded») for one model at a time at peak hours;
  # the api-proxy then retries the same request on the next model.
  fallback-models: [glm-5.3, glm-5.1]
  env:
    ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic
    # gh-aw sets 0 so its harness retries; the harness does not count 1305 as overloaded.
    CLAUDE_CODE_MAX_RETRIES: "6"
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
