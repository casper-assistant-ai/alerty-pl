---
description: |
  Weekly: adds tests for parser cases that are not covered yet, using real RCB pages
  saved as fixtures. Opens one PR for the Agent PR gate.
on:
  schedule:
    - cron: "22 10 * * 0"
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
