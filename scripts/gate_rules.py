#!/usr/bin/env python3
"""Rules of the Agent PR gate that must not depend on text an agent can write.

    gate_rules.py workflow --body-file F
    gate_rules.py bad-files --body-file F --allowed RE [--security RE] < files
    gate_rules.py verdict --reviews-file F --sha SHA

Every agent posts as the same login, github-actions[bot], so neither a PR title nor the text of a
comment says which agent wrote it (security audit #146, «Hardening» 3 and 4):

- `workflow`: the gh-aw workflow that opened a PR, read from the footer gh-aw appends to the PR body
  after the agent's own text (`<!-- gh-aw-workflow-id: X -->` and `workflow_id: X` in
  `<!-- gh-aw-agentic-workflow: ... -->`). The last of each marker counts, because the footer comes
  last; both must name the same workflow, else the PR has none. A title prefix such as
  `[security-fixer] ` is the agent's own text and counts for nothing (#164).
- `bad-files`: the changed files (one per line on stdin) outside the paths an agent PR may change:
  `--allowed`, plus `--security` (the vendored `dashboard/`) only for a PR whose footer names
  `security-fixer`.
- `verdict`: the PR reviewer's verdict on one head, read from the PR's reviews (`GET
  pulls/{n}/reviews`), never from comments (#165). Only the `pr-reviewer` workflow has the
  `submit-pull-request-review` safe output (tests/test_gate_rules.py checks every workflow), so a
  review by github-actions[bot] comes from it, while any agent can comment. (GitHub strips HTML
  comments from review bodies, so gh-aw's `workflow_id` marker cannot bind it.) The review must be
  submitted on that commit (`commit_id`) and say so (`Head:`); the newest such review wins. Prints
  `verdict<TAB>reason`, or nothing.

scripts/workflow_change.py keeps its own copy of the verdict rule (it runs pinned by hash with the
deploy key and imports nothing from here); the tests run both on the same reviews. Agents may not
change this file: the gate refuses an agent PR that does. Python 3 stdlib only.
"""
import argparse
import json
import re
import sys

BOT = "github-actions[bot]"
SECURITY_FIXER = "security-fixer"
# a review GitHub shows on the PR; PENDING is a draft only its author sees, DISMISSED was taken back
SUBMITTED = {"COMMENTED", "APPROVED", "CHANGES_REQUESTED"}


def workflow_of(body):
    """The gh-aw workflow id in the PR body's footer, or None."""
    body = body or ""
    ids = re.findall(r"<!-- gh-aw-workflow-id: *([a-z0-9-]+) *-->", body)
    runs = re.findall(r"<!-- gh-aw-agentic-workflow:[^>]*?\bworkflow_id: *([a-z0-9-]+)", body)
    if not ids or not runs or ids[-1] != runs[-1]:
        return None
    # the footer is the end of the body: nothing but more gh-aw markers may follow the last id
    tail = body[body.rfind("<!-- gh-aw-workflow-id:"):]
    if re.sub(r"<!--.*?-->", "", tail, flags=re.S).strip():
        return None
    return ids[-1]


def bad_files(files, body, allowed, security=""):
    """The files outside the paths an agent PR with this body may change."""
    pattern = allowed
    if security and workflow_of(body) == SECURITY_FIXER:
        pattern = f"{allowed}|{security}"
    rx = re.compile(pattern)
    return [f for f in files if f and not rx.search(f)]


def verdict(reviews, sha):
    """(verdict, reason) of the PR reviewer's review of commit sha, or (None, '')."""
    for r in reversed(reviews or []):
        body = (r.get("body") or "").replace("\r", "")
        if (r.get("user") or {}).get("login") != BOT or r.get("state") not in SUBMITTED:
            continue
        if r.get("commit_id") != sha:
            continue
        if not re.search(rf"(?m)^Head: *{re.escape(sha)}\s*$", body):
            continue
        v = re.search(r"(?m)^Verdict: *(approve|changes|reject)\b", body)
        if not v:
            continue
        m = re.search(r"(?m)^Reason: *(.*)$", body)
        return v.group(1), (m.group(1).strip() if m else "")
    return None, ""


def load_pages(text):
    """The items of `gh api --paginate` output: one JSON array per page, back to back."""
    items, dec, i = [], json.JSONDecoder(), 0
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return items
        page, i = dec.raw_decode(text, i)
        items.extend(page if isinstance(page, list) else [page])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("workflow")
    w.add_argument("--body-file", required=True)
    b = sub.add_parser("bad-files")
    b.add_argument("--body-file", required=True)
    b.add_argument("--allowed", required=True)
    b.add_argument("--security", default="")
    v = sub.add_parser("verdict")
    v.add_argument("--reviews-file", required=True)
    v.add_argument("--sha", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "workflow":
        print(workflow_of(open(a.body_file, encoding="utf-8").read()) or "")
    elif a.cmd == "bad-files":
        body = open(a.body_file, encoding="utf-8").read()
        for f in bad_files(sys.stdin.read().split("\n"), body, a.allowed, a.security):
            print(f)
    else:
        found, reason = verdict(load_pages(open(a.reviews_file, encoding="utf-8").read()), a.sha)
        if found:
            print(f"{found}\t{reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
