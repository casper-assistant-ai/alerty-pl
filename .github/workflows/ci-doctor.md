---
description: |
  Investigates failed runs of CI, Update data and Agent PR gate, on main and on pull requests,
  files one issue per distinct cause with the evidence and the fix it suggests, and dispatches
  the issue-worker, which brings it to a fix PR or closes it with the reason.
on:
  # started by other workflows (CI, Site check, Update data, the CI doctor) with GITHUB_TOKEN
  bots: ["github-actions[bot]"]
  workflow_run:
    workflows: ["CI", "Update data", "Agent PR gate"]
    types: [completed]
    branches: [main]
  # CI on a pull request of this repository starts this run itself when it fails (ci.yml);
  # fork PRs cannot, so outsiders cannot spend the agent budget
  workflow_dispatch:
    inputs:
      run_id:
        description: "Id of the failed run"
        required: true
if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'failure' }}
permissions:
  actions: read
  contents: read
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
network: defaults
tools:
  bash: false
  cli-proxy: false
  github:
    toolsets: [default, actions]
    # job logs of pull request runs are low-integrity content; the doctor only reads them
    lockdown: false
    min-integrity: none
safe-outputs:
  create-issue:
    title-prefix: "[ci-doctor] "
    labels: [agent, ci]
    max: 1
    deduplicate-by-title: true
    expires: 7d
  add-comment:
    max: 2
    target: "*"
  dispatch-workflow:
    workflows: [issue-worker]
    max: 1
  noop:
    report-as-issue: false
timeout-minutes: 20
---

# CI doctor

Read the Process block in `AGENTS.md` first: it says what the team needs from you this week.

Run: ${{ github.event.workflow_run.html_url }} (run id ${{ github.event.workflow_run.id }}${{ github.event.inputs.run_id }},
head ${{ github.event.workflow_run.head_sha }}). Read the run (GitHub tools) for its event and
head branch: a `pull_request` run belongs to the PR with that head branch.

0. A run with no jobs (it waited for an approval that expired, or the pull request was merged
   or closed first) is not a failure of the code: call `noop`.
1. Read the failed jobs' logs and find the first real error. For a pull request run, find the PR
   by its head branch and add one comment there with the cause and the fix.
2. Classify it: parser broke on new gov.pl HTML, gov.pl unreachable (transient), test failure,
   workflow or permission problem, or Pages deployment problem.
3. Search open issues titled "[ci-doctor]". If one has the same cause, add one comment with this
   run's link and stop.
4. A single transient network error with the next run green: call `noop`.
5. Otherwise create one issue: the error line, the cause with a confidence level, the fix, and
   the PR number for a pull request run. When the parser broke, say that the parser doctor was
   dispatched and should fix it. Then dispatch the `issue-worker`: it brings the issue to a fix PR
   (an agent PR that fails is replaced by a fixed one) or closes it with the reason.
