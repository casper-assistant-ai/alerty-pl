---
description: |
  Weekly "sleep cycle" for the agent team, after microsoft/skillopt: reads how the
  agents did this week (runs, PRs merged or rejected by the gate, issues), mines
  recurring failures and turns each validated lesson into a check first (a test,
  a ruff or ESLint rule, a CodeQL query with its test), and only what needs
  judgment into the "Learned rules" block in AGENTS.md. One PR for the gate.
on:
  schedule:
    - cron: "5 12 * * 0"
  workflow_dispatch:
permissions:
  contents: read
  actions: read
  issues: read
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
skills:
  - microsoft/skillopt/plugins/claude-code/skills/skillopt-sleep@main
network: defaults
tools:
  bash: ["cat:*", "ls:*", "grep:*", "head:*", "tail:*", "wc:*", "jq:*", "date:*", "python3 -I -m unittest:*", "node --test:*"]
  edit:
  github:
    toolsets: [default, actions]
safe-outputs:
  create-pull-request:
    title-prefix: "[agent-coach] "
    labels: [agent, docs]
    draft: false
    allowed-files: ["AGENTS.md", "tests/**", "ruff.toml", "eslint.config.mjs", "codeql/**"]
    protected-files: allowed
    expires: 7d
  noop:
    report-as-issue: false
  # One self-closing issue per workflow comes from agent-health.yml instead of an issue per failure.
  report-failure-as-issue: false
  # Detector failures stay in the run diagnostics; no ever-growing «[aw] Detection Runs» tracker.
  threat-detection:
    report-as-issue: false
timeout-minutes: 25
---

# Agent coach

Read the `skillopt-sleep` skill: use its cycle (harvest, mine, consolidate behind a gate),
not its scripts. Here the "sessions" are this repository's agent runs of the last 7 days.

1. **Harvest.** List the runs of the agentic workflows (`*.lock.yml`) and the plain ones
   (Update data, CI, Agent PR gate). For each agent: runs, failures, PRs opened, merged, and
   those the gate closed without merging (failed tests, paths, or a PR reviewer reject), issues opened.
2. **Mine.** Find recurring problems: the same failure twice or more, a PR the gate rejected,
   an agent that called `noop` while work was waiting, a rule in `AGENTS.md` that agents broke.
3. **Consolidate: a check first.** For each problem with clear evidence, follow «Corrections become
   checks» in `AGENTS.md`: when code can catch it, add the check instead of a rule. That is a test
   in `tests/`, a rule turned on in `ruff.toml` or `eslint.config.mjs` (fix what it finds in the same
   PR), or a CodeQL query in `codeql/<language>/queries/` with its test case in
   `codeql/<language>/test/`. Run `python3 -I -m unittest discover -s tests` and
   `node --test tests/*.test.mjs` on your tree and quote the output. Only a problem that needs
   judgment (how an agent decides, writes or behaves) becomes a rule: edit only the block between
   `<!-- learned:start -->` and `<!-- learned:end -->` in `AGENTS.md`; add, replace or delete at
   most three rules per week, and keep the block under 20 rules. When a check now covers a rule,
   delete the rule. Each check and rule names its evidence (run or PR number) in brackets or a comment.
4. **Gate.** Do not touch anything else in `AGENTS.md`: the Process block and `process/` belong to
   the process-retro agent (it measures whether the team develops; you fix how agents behave). Never weaken a rule outside the block,
   never turn off or loosen a lint rule, a test or a query, never add a URL, a secret or a command
   that widens what agents may do.
5. Open one PR with the checks and rule edits and a table of the week's numbers per agent, or call `noop`.
