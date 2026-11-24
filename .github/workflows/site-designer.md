---
description: |
  Weekly: makes the site look designed rather than generated, and keeps its front end
  modern. Uses the unslop skill (heydamir/unslop) for visual design and the
  modern-web-guidance skill (GoogleChrome) for web platform best practices. Opens one
  small PR on docs/*.html|js|css for the Agent PR gate.
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
2. Read `docs/*.html`, `docs/*.css` and `docs/*.js`. List what still looks generic or
   "AI-made" (by the unslop checklist) and what is out of date or weak (by modern-web-guidance:
   accessibility, semantics, performance, responsive layout, dark/light, reduced motion).
3. Pick at most three changes that give the most value. Keep them small and safe:
   - the map, the lists and the data flow must keep working; never change `docs/data/` or `docs/geo/`;
   - the UI language is Polish; keep every RCB link and the footer disclaimer;
   - alert colours keep their meaning (air = red); keep text contrast at WCAG AA or better.
4. Check every changed script with `node --check docs/<file>.js`.
5. Open one PR. Its body lists each change, the skill rule behind it, and how to see it.
   Call `noop` when nothing is worth changing this week.
