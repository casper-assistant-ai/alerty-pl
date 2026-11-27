---
description: |
  Daily health report of the alerty-pl service and its agent team: data freshness,
  alerts parsed, regions unmatched, agent PRs merged or stuck, failures. One issue,
  replacing yesterday's.
on:
  schedule:
    - cron: "5 10 * * *"
  workflow_dispatch:
  # zai-gate:begin
  # z.ai quota gate (scripts/zai_gate.py writes it): skip the run when the account's 5-hour quota
  # is used up to this agent's limit, instead of dying at turn 1 on 429 [1308]
  steps:
    - name: z.ai quota gate
      id: zai_quota
      # exit 1 = skip the run; the job itself stays green, the activation reads the outcome
      continue-on-error: true
      env:
        ZAI_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        LIMIT: "60"
      run: |
        set -u
        r=$(curl -sS -m 20 -H "Authorization: $ZAI_KEY" https://api.z.ai/api/monitor/usage/quota/limit) || { echo "z.ai quota not read, the run goes on"; exit 0; }
        read -r pct reset < <(printf '%s' "$r" | python3 -I -c '
        import json, sys
        try:
            ls = [l for l in json.load(sys.stdin)["data"]["limits"] if l.get("type") == "TOKENS_LIMIT"]
            print(max(int(l["percentage"]) for l in ls), max(int(l.get("nextResetTime") or 0) for l in ls))
        except Exception:
            print("- 0")
        ' 2>/dev/null || echo "- 0")
        case "${pct:--}" in -|*[!0-9]*) echo "no TOKENS_LIMIT in the answer of z.ai, the run goes on"; exit 0;; esac
        at=$(date -u -d "@$(( ${reset:-0} / 1000 ))" +%H:%M 2>/dev/null || echo "?")
        if [ "$pct" -ge "$LIMIT" ]; then
          echo "::notice title=z.ai quota::5-hour quota ${pct}% used, this agent's limit is ${LIMIT}%; resets at ${at} UTC; run skipped"
          exit 1
        fi
        echo "z.ai 5-hour quota ${pct}% used (limit ${LIMIT}%, resets at ${at} UTC), the run goes on"
  # zai-gate:end
# zai-gate:if-begin
if: ${{ needs.pre_activation.outputs.zai_quota_result == 'success' }}
# zai-gate:if-end
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
network: defaults
steps:
  - name: List the issues the agents gave up on
    env:
      GH_TOKEN: ${{ github.token }}
    run: |
      mkdir -p /tmp/gh-aw/agent
      python3 -I scripts/retro.py gave-up --days 1 --out /tmp/gh-aw/agent/gave-up.json --md /tmp/gh-aw/agent/gave-up.md
tools:
  bash: ["cat:*", "jq:*", "ls:*", "head:*", "tail:*", "grep:*", "wc:*", "date:*"]
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
  # One self-closing issue per workflow comes from agent-health.yml instead of an issue per failure.
  report-failure-as-issue: false
  # Detector failures stay in the run diagnostics; no ever-growing «[aw] Detection Runs» tracker.
  threat-detection:
    report-as-issue: false
timeout-minutes: 20
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
  `[ci-doctor]` and `[triage]`, and agent PRs the gate closed without merging (with the reason).
- **Needs a human look** (step 3 of the give-up ladder): the issues the issue-worker gave up on in the
  last 24 hours (label `agent-gave-up`), read from `/tmp/gh-aw/agent/gave-up.md`, each as `#N title`
  with a link and its «Needs:» line from the closing comment. These are the only items of this
  report that ask for a human; everything else here is information. Write «Nothing needs a human
  look» when the list is empty.
- **Next:** at most three things the agents should do next.

Plain Markdown, short bullet lists, no tables over 6 rows.
