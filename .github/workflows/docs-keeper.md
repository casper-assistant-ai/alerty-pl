---
description: |
  Weekly: keeps README.md and AGENTS.md true to the code and the agent roster in
  .github/workflows. Opens one PR for the Agent PR gate.
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
  # z.ai answers 529 (1305 «temporarily overloaded») for one model at a time at peak hours;
  # the api-proxy then retries the same request on the next model.
  fallback-models: [glm-5.3, glm-5.1]
  env:
    ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic
    # gh-aw sets 0 so its harness retries; the harness does not count 1305 as overloaded.
    CLAUDE_CODE_MAX_RETRIES: "6"
imports:
  - shared/zai.md
network: defaults
tools:
  bash: ["cat:*", "ls:*", "grep:*", "head:*", "find:*"]
  edit:
safe-outputs:
  create-pull-request:
    title-prefix: "[docs-keeper] "
    labels: [agent, docs]
    draft: false
    allowed-files: ["README.md", "AGENTS.md"]
    protected-files: allowed
    expires: 7d
  noop:
    report-as-issue: false
  # One self-closing issue per workflow comes from agent-health.yml instead of an issue per failure.
  report-failure-as-issue: false
  # Detector failures stay in the run diagnostics; no ever-growing «[aw] Detection Runs» tracker.
  threat-detection:
    report-as-issue: false
# its one good run of the week took 9 of 10 minutes (#107, process-doctor)
timeout-minutes: 20
---

# Docs keeper

Compare `README.md` and `AGENTS.md` with the repository: the workflows in `.github/workflows/`
(their triggers and what they may change), the data files, the commands that run the tests and
the scraper. Fix only what is wrong or missing, keep the style, keep it short. Open one PR, or
call `noop` when the docs are current.
