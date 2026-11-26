#!/usr/bin/env python3
"""Local fixes to the compiled gh-aw lock files that gh-aw itself does not offer yet.

Run it after every `gh aw compile` (scripts/workflow_change.py does). `--check` exits 1
when a lock file lacks a fix; tests/test_lock_patches.py runs that check in CI.

1. «Parse agent logs for step summary» may not fail the agent job.
   gh-aw v1.2.2 to v1.4.0 render the step summary with `lines.push("", ...traceLines)`
   (actions/setup/js/unified_session_render.cjs). A GLM session on Claude Code writes
   tens of thousands of `system/thinking_tokens` events, the spread overflows the stack
   (`ERR_API: Maximum call stack size exceeded`) and the whole run is marked failed,
   although the agent finished and its safe outputs went out (daily-status 45563067551,
   process-retro 45572407916, security-auditor 45702571324; 25.11.2026). Only the
   summary is lost, so the step gets `continue-on-error: true`.
"""
import argparse
import re
import sys
from pathlib import Path

WF = Path(".github/workflows")
STEP = "      - name: Parse agent logs for step summary\n"
FLAG = "        continue-on-error: true\n"
NEXT_STEP = re.compile(r"^      - |^  [A-Za-z0-9_-]+:\s*$")


def patch(text):
    """Return (new_text, changed)."""
    lines = text.splitlines(keepends=True)
    out, changed, i = [], False, 0
    while i < len(lines):
        out.append(lines[i])
        if lines[i] == STEP:
            j = i + 1
            while j < len(lines) and not NEXT_STEP.match(lines[j]):
                j += 1
            body = lines[i + 1:j]
            if FLAG not in body:
                out.append(FLAG)
                changed = True
            out.extend(body)
            i = j
            continue
        i += 1
    return "".join(out), changed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only report lock files that lack a fix")
    ap.add_argument("files", nargs="*", help="lock files (default: all .github/workflows/*.lock.yml)")
    a = ap.parse_args(argv)
    files = [Path(f) for f in a.files] or sorted(WF.glob("*.lock.yml"))
    missing = []
    for f in files:
        new, changed = patch(f.read_text())
        if changed:
            missing.append(str(f))
            if not a.check:
                f.write_text(new)
    if a.check and missing:
        print("lock files without the local fixes (run python3 scripts/lock_patches.py):", *missing, sep="\n  ")
        return 1
    for f in missing:
        print("patched", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
