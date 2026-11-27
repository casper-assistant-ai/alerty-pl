#!/usr/bin/env python3
"""Keep the z.ai quota gate in every agent workflow that runs on z.ai.

    zai_gate.py [--check] [files...]

The z.ai coding plan has a 5-hour token quota for the whole account. On 2026-11-26/27 it ran out
again and again (83% was gone 43 minutes after the 07:08 UTC reset of 11-27), and every agent that
started in the hole died at its first turn on 429 [1308] «Usage limit reached for 5 hour», 12 red
runs in one night and an e-mail for each (issue-worker 45946260556, pr-fixer 45953392187).

The gate is a pre-activation step (`on.steps`) that asks z.ai how much of the 5-hour quota is used
(`GET https://api.z.ai/api/monitor/usage/quota/limit`, free, it spends no tokens) and skips the run
(the run is skipped, not failed) when the share is at the agent's limit:

- pipeline agents, which keep the queue moving (issue-worker, pr-fixer, pr-reviewer, ci-doctor,
  issue-triage, site-fixer, security-fixer, parser-doctor): 90%;
- the others (reports, retros, audits, design, docs, tests): 60%, so they leave the rest of the
  window to the pipeline.

When z.ai does not answer, or answers without a TOKENS_LIMIT, the run goes on. A skipped run is
caught by the agent's next schedule or dispatch; agent-retry.yml still re-runs a run that died.

The step and the `if:` are written between the markers `# zai-gate:begin` and `# zai-gate:end`, so
this script rewrites them in place. Run it after editing the gate, then `gh aw compile` and
`scripts/lock_patches.py`. `--check` exits 1 when a workflow lacks the current gate
(tests/test_zai_gate.py).
"""
import argparse
import re
import sys
from pathlib import Path

WF = Path(".github/workflows")
PIPELINE = {"issue-worker", "pr-fixer", "pr-reviewer", "ci-doctor", "issue-triage", "site-fixer",
            "security-fixer", "parser-doctor"}
PIPELINE_LIMIT, OTHER_LIMIT = 90, 60
BEGIN, END = "  # zai-gate:begin\n", "  # zai-gate:end\n"
IF_BEGIN, IF_END = "# zai-gate:if-begin\n", "# zai-gate:if-end\n"
GATE_IF = "needs.pre_activation.outputs.zai_quota_result == 'success'"

STEP = """\
  # z.ai quota gate (scripts/zai_gate.py writes it): skip the run when the account's 5-hour quota
  # is used up to this agent's limit, instead of dying at turn 1 on 429 [1308]
  steps:
    - name: z.ai quota gate
      id: zai_quota
      # exit 1 = skip the run; the job itself stays green, the activation reads the outcome
      continue-on-error: true
      env:
        ZAI_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        LIMIT: "{limit}"
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
"""


def zai_agents():
    out = []
    for md in sorted(WF.glob("*.md")):
        if not md.with_suffix("").with_suffix(".lock.yml").exists() and not (WF / (md.stem + ".lock.yml")).exists():
            continue
        if "api.z.ai" in md.read_text():
            out.append(md)
    return out


def frontmatter_bounds(lines):
    assert lines[0] == "---\n", "no frontmatter"
    return 1, lines.index("---\n", 1)


def patch(text, name):
    """Return the workflow text with the current gate."""
    limit = PIPELINE_LIMIT if name in PIPELINE else OTHER_LIMIT
    lines = text.splitlines(keepends=True)
    _, end = frontmatter_bounds(lines)
    fm = lines[1:end]
    # drop an older gate
    def strip(block, b, e):
        if b in block:
            i, j = block.index(b), block.index(e)
            del block[i:j + 1]
    strip(fm, BEGIN, END)
    strip(fm, IF_BEGIN, IF_END)
    # the step goes at the end of the `on:` block
    on = next(i for i, l in enumerate(fm) if l.startswith("on:"))
    k = on + 1
    while k < len(fm) and (fm[k].startswith(" ") or fm[k].strip() == ""):
        k += 1
    if re.match(r"on:\s*\S", fm[on]):  # `on: daily` style is not used here
        raise SystemExit(f"{name}: inline `on:` value, write the gate by hand")
    if any(re.match(r"  steps:", l) for l in fm[on + 1:k]):
        raise SystemExit(f"{name}: has its own on.steps, merge the gate by hand")
    fm[k:k] = [BEGIN, STEP.replace("{limit}", str(limit)), END]
    # the condition: AND with an existing `if:`
    ifs = [i for i, l in enumerate(fm) if l.startswith("if:")]
    if ifs:
        i = ifs[0]
        old = fm[i][3:].strip()
        if old.startswith("${{") and old.endswith("}}"):
            old = old[3:-2].strip()
        fm[i:i + 1] = [IF_BEGIN, f"if: ${{{{ ({old}) && {GATE_IF} }}}}\n", f"# was: if: {old}\n", IF_END]
    else:
        fm.insert(k + 3, IF_BEGIN)
        fm.insert(k + 4, f"if: ${{{{ {GATE_IF} }}}}\n")
        fm.insert(k + 5, IF_END)
    return "".join([lines[0]] + fm + lines[end:])


def unwrap_if(fm_text):
    """The original `if:` kept in the `# was:` line, for a rewrite."""
    m = re.search(r"^# was: if: (.*)$", fm_text, re.M)
    return m.group(1) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    files = [Path(f) for f in a.files] or zai_agents()
    missing = []
    for f in files:
        text = f.read_text()
        was = unwrap_if(text)
        base = text
        if was is not None:  # restore the original `if:` before the rewrite
            lines = text.splitlines(keepends=True)
            i, j = lines.index(IF_BEGIN), lines.index(IF_END)
            lines[i:j + 1] = [f"if: {was}\n"]
            base = "".join(lines)
        new = patch(base, f.stem)
        if new != text:
            missing.append(str(f))
            if not a.check:
                f.write_text(new)
    for m in missing:
        print(("lacks the current z.ai gate: " if a.check else "gate written: ") + m)
    return 1 if (a.check and missing) else 0


if __name__ == "__main__":
    sys.exit(main())
