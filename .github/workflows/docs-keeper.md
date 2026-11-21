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
network: defaults
tools:
  bash: ["cat", "ls", "grep", "head", "find"]
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
timeout-minutes: 10
---

# Docs keeper

Compare `README.md` and `AGENTS.md` with the repository: the workflows in `.github/workflows/`
(their triggers and what they may change), the data files, the commands that run the tests and
the scraper. Fix only what is wrong or missing, keep the style, keep it short. Open one PR, or
call `noop` when the docs are current.
