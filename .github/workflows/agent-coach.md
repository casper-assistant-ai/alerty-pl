---
description: |
  Weekly "sleep cycle" for the agent team, after microsoft/skillopt: reads how the
  agents did this week (runs, PRs merged or rejected by the gate, issues), mines
  recurring failures and turns the validated lessons into bounded edits of the
  "Learned rules" block in AGENTS.md, which every agent reads. One PR for the gate.
on:
  schedule: weekly
  workflow_dispatch:
permissions:
  contents: read
  actions: read
  issues: read
  pull-requests: read
strict: true
engine:
  id: claude
  model: glm-5.3
  env:
    ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic
imports:
  - shared/zai.md
skills:
  - microsoft/skillopt/plugins/claude-code/skills/skillopt-sleep@main
network: defaults
tools:
  bash: ["cat:*", "ls:*", "grep:*", "head:*", "tail:*", "wc:*", "jq:*", "date:*"]
  edit:
  github:
    toolsets: [default, actions]
safe-outputs:
  create-pull-request:
    title-prefix: "[agent-coach] "
    labels: [agent, docs]
    draft: false
    allowed-files: ["AGENTS.md"]
    protected-files: allowed
    expires: 7d
  noop:
timeout-minutes: 25
---

# Agent coach

Read the `skillopt-sleep` skill: use its cycle (harvest, mine, consolidate behind a gate),
not its scripts. Here the "sessions" are this repository's agent runs of the last 7 days.

1. **Harvest.** List the runs of the agentic workflows (`*.lock.yml`) and the plain ones
   (Update data, CI, Agent PR gate). For each agent: runs, failures, PRs opened, merged, and
   those the gate commented on or labelled `needs-attention`, issues opened.
2. **Mine.** Find recurring problems: the same failure twice or more, a PR the gate rejected,
   an agent that called `noop` while work was waiting, a rule in `AGENTS.md` that agents broke.
3. **Consolidate.** For each problem with clear evidence, write one short rule. Edit only the block
   between `<!-- learned:start -->` and `<!-- learned:end -->` in `AGENTS.md`: add, replace or
   delete at most three rules per week, and keep the block under 20 rules. Each rule names its
   evidence (run or PR number) in brackets.
4. **Gate.** Do not touch anything else in `AGENTS.md`: the Process block and `process/` belong to
   the process-retro agent (it measures whether the team develops; you fix how agents behave). Never weaken a rule outside the block,
   never add a URL, a secret or a command that widens what agents may do.
5. Open one PR with the edits and a table of the week's numbers per agent, or call `noop`.
