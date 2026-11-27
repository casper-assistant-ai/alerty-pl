---
description: |
  Weekly: makes the site look designed rather than generated, and keeps its front end
  modern. Uses the unslop skill (heydamir/unslop) for visual design and the
  modern-web-guidance skill (GoogleChrome) for web platform best practices. Opens one
  small PR on docs/*.html|js|css for the Agent PR gate.
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
skills:
  - heydamir/unslop/skills/unslop@main
  - googlechrome/modern-web-guidance/skills/modern-web-guidance@main
network: defaults
tools:
  bash: ["cat:*", "ls:*", "grep:*", "head:*", "tail:*", "wc:*", "node:*", "python3:*", "find:*"]
  edit:
safe-outputs:
  create-pull-request:
    title-prefix: "[site-designer] "
    labels: [agent, site]
    draft: false
    allowed-files: ["docs/*.html", "docs/*.js", "docs/*.css"]
    protected-files: blocked
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

# Site designer

You own the look and the front-end quality of the alerty-pl site in `docs/` (plain HTML, CSS and
JavaScript, no build step, no npm, no external fonts or CDNs). Read `AGENTS.md` first.

1. Read the `unslop` skill and the `modern-web-guidance` skill. They are your checklist.
2. Skim `docs/*.html`, `docs/*.css` and `docs/*.js` (`wc -l`, `head` and `grep` first; read a
   file whole only when you mean to change it) and list what still looks generic or "AI-made" (by
   the unslop checklist) and what is out of date or weak (by modern-web-guidance: accessibility,
   semantics, performance, responsive layout, dark/light, reduced motion).
3. Pick at most three changes that give the most value. Keep them small and safe:
   - the map, the lists and the data flow must keep working; never change `docs/data/` or `docs/geo/`;
   - the UI language is Polish; keep every RCB link and the footer disclaimer;
   - alert colours keep their meaning (air = red); keep text contrast at WCAG AA or better.
   The node tests pin the front end: `tests/style.test.mjs` the `.month h2` and `.top .src` rules of
   `docs/style.css` (fixes of the mobile audit), `tests/i18n.test.mjs` the `data-i18n` marks and the
   switcher of every page, `tests/common.test.mjs` the helpers of `docs/common.js`. Never edit a test
   to make a change pass: drop or reshape the change and name it in the PR body as a follow-up.
4. Check every changed script with `node --check docs/<file>.js`, then run
   `node --test tests/*.test.mjs` and quote its output in the PR body.
5. Open one PR. Its body lists each change, the skill rule behind it, and how to see it.
   The run has 25 minutes and no clock: stop reading and write by your 40th turn, and never read
   `process/*.md` or `scripts/` (the process-doctor's files, not a design checklist).
   The PR may change `docs/*.html`, `docs/*.js` and `docs/*.css` only: the safe output refuses the
   whole patch for any other file, and the run's work is lost.
   Call `noop` when nothing is worth changing this week.
