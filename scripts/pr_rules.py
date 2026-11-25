#!/usr/bin/env python3
"""Repository rules that code can check, so they need no line in AGENTS.md.

    pr_rules.py check --base REF --head REF [--body-file F] [--workflow W] [--closes-file F]
    pr_rules.py commits RANGE
    pr_rules.py squash-body < messages

`check` looks at one PR: the diff from the merge base of REF..REF, its body and the issues it
closes. CI runs it on every pull request and the Agent PR gate on every PR it takes, with the copy
on main (agents may not change this file). It prints one line per broken rule and exits 1:

- suppression: an added `noqa`, `eslint-disable` (or another inline ESLint comment), `nosec`,
  `type: ignore` or CodeQL `codeql[...]`/`lgtm[...]` comment in code. A finding is fixed, never
  silenced (owner's rule, 2026-11-25). The linters ignore such comments too (`ruff --ignore-noqa`,
  ESLint `noInlineConfig`); this names them in the PR.
- lint-config: a looser `ruff.toml` (a rule taken out of `select`, a new `ignore`, `exclude` or
  per-file ignore) or `eslint.config.mjs` (a removed line, a new `ignores`, `off`, `warn` or 0), or a
  deleted CodeQL query or query test. Ask Casper in an issue when a rule is wrong.
- generated-data: a change under `docs/data/`, which only the Update data and Update shelters
  workflows write.
- parser-test: `scripts/rcb.py` changed with no change under `tests/` (a test on a saved page).
- ai-coauthor: a `Co-Authored-By:` line naming Claude or Anthropic, or «Generated with Claude
  Code», in the PR body (owner's rule, 2026-11-23).
- process-issue: the PR closes an issue labelled `agent-health` or `workflow-change`, which belong
  to the process-doctor and the Workflow maintainer.
- one-issue: an `issue-worker` PR closes more than one issue (one issue per run).

`commits RANGE` checks the commit messages of a push for AI co-author lines; `squash-body` drops
those lines from the text the gate merges with. Python 3 stdlib only.
"""
import argparse
import json
import re
import subprocess
import sys
import tomllib

CODE = re.compile(r"\.(py|js|mjs|cjs|ts)$")
# vendored code, and the cases a CodeQL query must find (bad on purpose)
VENDORED = re.compile(r"^(dashboard/|docs/vendor/|\.github/skills/|codeql/[^/]+/test/)")
SUPPRESS = re.compile(
    r"#\s*noqa\b|\bruff:\s*noqa\b|eslint-disable|/[*/]\s*eslint\b|/\*\s*global\s|#\s*nosec\b"
    r"|#\s*type:\s*ignore\b|@ts-(ignore|nocheck|expect-error)\b|\b(codeql|lgtm)\[",
    re.I,
)
# the whole line, so a report quotes it
AI_LINE = re.compile(
    r"^(\s*co-authored-by:.*\b(claude|anthropic)\b|.*generated with .*claude).*$", re.I | re.M
)
# this script and its test spell the patterns out
SELF = {"scripts/pr_rules.py", "tests/test_pr_rules.py"}
PROCESS_LABELS = {"agent-health", "workflow-change"}
RUFF_LOOSER = ("ignore", "extend-ignore", "exclude", "extend-exclude", "per-file-ignores",
               "extend-per-file-ignores", "unfixable")


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def parse_diff(text):
    """{path: (status, added lines, removed lines)} from `git diff --no-renames -U0` output."""
    files, path = {}, None
    for line in text.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1]
            files[path] = ["M", [], []]
        elif path is None:
            continue
        elif line.startswith("new file mode"):
            files[path][0] = "A"
        elif line.startswith("deleted file mode"):
            files[path][0] = "D"
        elif line.startswith("+") and not line.startswith("+++ "):
            files[path][1].append(line[1:])
        elif line.startswith("-") and not line.startswith("--- "):
            files[path][2].append(line[1:])
    return {p: tuple(v) for p, v in files.items()}


def suppressions(files):
    out = []
    for path, (_status, added, _removed) in files.items():
        if not CODE.search(path) or VENDORED.match(path) or path in SELF:
            continue
        for line in added:
            if SUPPRESS.search(line):
                out.append(f"suppression: {path} adds «{line.strip()[:120]}»; fix the finding instead "
                           "(the linters ignore such comments)")
    return out


def _ruff_sets(text):
    """The ruff settings that only grow looser, flattened to comparable items."""
    try:
        cfg = tomllib.loads(text or "")
    except tomllib.TOMLDecodeError:
        return None, None
    lint = cfg.get("lint", {})
    select = set(lint.get("select", [])) | set(lint.get("extend-select", []))
    looser = set()
    for scope in (cfg, lint):
        for key in RUFF_LOOSER:
            val = scope.get(key)
            if isinstance(val, dict):
                looser |= {f"{key}:{p}:{r}" for p, rs in val.items() for r in rs}
            elif isinstance(val, list):
                looser |= {f"{key}:{v}" for v in val}
    return select, looser


def ruff_looser(old, new):
    """Why the new ruff.toml is looser than the old one, or []."""
    s_old, l_old = _ruff_sets(old)
    s_new, l_new = _ruff_sets(new)
    if s_new is None:
        return ["ruff.toml does not parse"]
    if s_old is None:
        return []
    out = [f"takes {r} out of select" for r in sorted(s_old - s_new)]
    out += [f"adds {x}" for x in sorted(l_new - l_old)]
    return out


ESLINT_LOOSER = re.compile(r"\bignores\b|[\"']off[\"']|[\"']warn[\"']|:\s*\[?\s*[01]\b|noInlineConfig\s*:\s*false", re.I)


def lint_configs(files, base, head):
    out = []
    base = git("merge-base", base, head).strip()  # what the PR started from, not a newer main
    for path, (status, added, removed) in files.items():
        if path == "ruff.toml":
            old = git("show", f"{base}:ruff.toml") if status != "A" else ""
            new = git("show", f"{head}:ruff.toml") if status != "D" else ""
            for why in ruff_looser(old, new) if new else ["deletes ruff.toml"]:
                out.append(f"lint-config: ruff.toml {why}")
        elif path == "eslint.config.mjs":
            if removed:
                out.append(f"lint-config: eslint.config.mjs removes «{removed[0].strip()[:80]}»; "
                           "the config may only grow stricter")
            for line in added:
                if ESLINT_LOOSER.search(line.split("//", 1)[0]):
                    out.append(f"lint-config: eslint.config.mjs adds «{line.strip()[:80]}»")
        elif re.match(r"^codeql/[^/]+/(queries|test)/", path) and status == "D":
            out.append(f"lint-config: deletes {path}; a CodeQL query and its test stay")
    return out


def check(files, base, head, body="", workflow="", closes=()):
    out = suppressions(files)
    out += lint_configs(files, base, head) if base and head else []
    data = sorted(p for p in files if p.startswith("docs/data/"))
    if data:
        out.append(f"generated-data: changes {', '.join(data[:5])}; only the Update data and Update "
                   "shelters workflows write docs/data/")
    if "scripts/rcb.py" in files and not any(p.startswith("tests/") for p in files):
        out.append("parser-test: scripts/rcb.py changes with no test; add a case on a saved page "
                   "(tests/fixtures/, tests/test_rcb*.py)")
    for m in AI_LINE.finditer(body or ""):
        out.append(f"ai-coauthor: the PR body has «{m.group(0).strip()[:80]}»; no AI tool is a co-author")
    for issue in closes:
        hit = PROCESS_LABELS & set(issue.get("labels", []))
        if hit:
            out.append(f"process-issue: closes #{issue['number']} ({', '.join(sorted(hit))}), which "
                       "belongs to the process-doctor; drop «Closes #" f"{issue['number']}»")
    if workflow == "issue-worker" and len(closes) > 1:
        nums = ", ".join(f"#{i['number']}" for i in closes)
        out.append(f"one-issue: an issue-worker PR closes one issue; this one closes {nums}")
    return out


def commit_problems(log):
    """Commits (records `sha\\x1fmessage\\x1e`) whose message names an AI co-author."""
    out = []
    for rec in log.split("\x1e"):
        if "\x1f" not in rec:
            continue
        sha, msg = rec.strip().split("\x1f", 1)
        m = AI_LINE.search(msg)
        if m:
            out.append(f"ai-coauthor: commit {sha[:9]} has «{m.group(0).strip()[:80]}»")
    return out


def squash_body(text):
    return "\n".join(l for l in text.split("\n") if not AI_LINE.search(l))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--base", required=True)
    c.add_argument("--head", required=True)
    c.add_argument("--body-file")
    c.add_argument("--workflow", default="")
    c.add_argument("--closes-file", help='JSON: [{"number": N, "labels": ["..."]}]')
    m = sub.add_parser("commits")
    m.add_argument("range")
    sub.add_parser("squash-body")
    a = ap.parse_args(argv)
    if a.cmd == "squash-body":
        sys.stdout.write(squash_body(sys.stdin.read()))
        return 0
    if a.cmd == "commits":
        out = commit_problems(git("log", "--format=%H%x1f%B%x1e", a.range))
    else:
        files = parse_diff(git("diff", "--no-renames", "-U0", f"{a.base}...{a.head}"))
        body = open(a.body_file, encoding="utf-8").read() if a.body_file else ""
        closes = json.load(open(a.closes_file, encoding="utf-8")) if a.closes_file else []
        out = check(files, a.base, a.head, body, a.workflow, closes)
    for line in out:
        print(line)
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
