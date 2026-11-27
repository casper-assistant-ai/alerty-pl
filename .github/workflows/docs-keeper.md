---
description: |
  Weekly: keeps README.md and AGENTS.md true to the code and the agent roster in
  .github/workflows. Opens one PR for the Agent PR gate.
on:
  schedule: weekly
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
