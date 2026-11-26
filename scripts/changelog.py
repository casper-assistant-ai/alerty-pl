#!/usr/bin/env python3
"""Releases and the changelog of alerty-pl, built from Conventional Commits and git tags.

Every commit on main follows Conventional Commits (https://www.conventionalcommits.org):
    <type>(<optional scope>)!: <description>
Types: feat, fix, perf, revert (they make a release), docs, style, refactor, test, build,
ci, chore (they do not). A "!" after the type or a "BREAKING CHANGE:" footer is a breaking change.

Versions follow semver (https://semver.org) and live in git tags vMAJOR.MINOR.PATCH:
breaking -> major, feat -> minor, fix/perf/revert -> patch. Each run of the Update data
workflow calls `release`: when main has releasable commits since the last tag, it tags HEAD.

    python3 -I scripts/changelog.py release            # tag HEAD with the next version, if any
    python3 -I scripts/changelog.py build              # write CHANGELOG.md and docs/data/changelog.json
    python3 -I scripts/changelog.py lint A..B          # check commit subjects in a range
    python3 -I scripts/changelog.py lint --title "…"   # check one subject (a PR title)
    python3 -I scripts/changelog.py next               # print the version the next release gets
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = {
    "feat": "Nowe funkcje", "fix": "Poprawki", "perf": "Wydajność", "revert": "Wycofane zmiany",
    "docs": "Dokumentacja", "style": "Wygląd kodu", "refactor": "Porządki w kodzie", "test": "Testy",
    "build": "Budowanie", "ci": "Automatyzacja", "chore": "Inne",
}
RELEASING = {"feat": "minor", "fix": "patch", "perf": "patch", "revert": "patch"}
CC = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9._/-]+)\))?(?P<bang>!)?: (?P<desc>\S.*)$")
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

# Commits that are not Conventional (made before the convention of 21.11.2026, or in the web
# editor), written the way they would be today.
LEGACY = {
    "0b213ac": "feat: alert map of Poland from gov.pl RCB, run by an agent team",
    "c2871d9": "fix(update): autostash meta.json before the rebase",
    "ef40b0f": "feat(monitoring): agent monitoring with gh-cao, alert times in the history fixed",
    "1d7350e": "fix(deploy): retry the Pages deploy when the artifact is not listed yet",
    "eb8df96": "feat(agents): developer agents on z.ai (GLM-5.3) with the site-designer, security-auditor and agent-coach skills",
    "6313095": "feat(regions): map Warsaw-area towns to powiaty (#4)",
    "1fdd28c": "feat(site): honest status signals, reduced-motion opt-in, live-region alarm announcements (#5)",
    "040db28": "feat: alert history since 2021, analytics page and a redesign",
    "e9f75cb": "fix(regions): re-parse cached alerts after the Warsaw-area town rules (#7)",
    # made later in GitHub's web editor, outside the lint
    "8253358": "ci: weekly Dependabot checks",
}
# Robot commits that are not changes of the product.
SKIP = re.compile(r"^(data: |chore\(data\)|chore\(release\))")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def parse(subject, body=""):
    """A commit subject -> dict(type, scope, breaking, desc), or None when it is not conventional."""
    m = CC.match(subject.strip())
    if not m or m["type"] not in TYPES:
        return None
    breaking = bool(m["bang"]) or bool(re.search(r"^BREAKING[ -]CHANGE: ", body, re.M))
    return {"type": m["type"], "scope": m["scope"], "breaking": breaking, "desc": m["desc"]}


def commits(rev_range=None):
    """Commits of main, oldest first: dicts with sha, date, subject, body and the parsed parts."""
    fmt = "%H%x1f%aI%x1f%s%x1f%b%x1e"
    out = git("log", "--reverse", "--no-merges", f"--format={fmt}", *([rev_range] if rev_range else []))
    items = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, date, subject, body = rec.split("\x1f")
        if SKIP.match(subject):
            continue
        subject = LEGACY.get(sha[:7], subject)
        items.append({"sha": sha, "date": date, "subject": subject, "body": body, "cc": parse(subject, body)})
    return items


def tags():
    """Version tags reachable from HEAD: {sha: (major, minor, patch)}."""
    out = git("tag", "--merged", "HEAD", "--format=%(refname:short)\t%(*objectname)\t%(objectname)")
    res = {}
    for line in out.splitlines():
        name, peeled, obj = line.split("\t")
        m = TAG.match(name)
        if m:
            res[peeled or obj] = tuple(map(int, m.groups()))
    return res


def bump(version, kind):
    major, minor, patch = version
    if kind == "major":
        return (major + 1, 0, 0) if major else (1, 0, 0)
    if kind == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def level(items):
    """The biggest bump the commits ask for: major, minor, patch or None."""
    kinds = set()
    for c in items:
        cc = c["cc"]
        if cc and cc["breaking"]:
            kinds.add("major")
        elif cc and cc["type"] in RELEASING:
            kinds.add(RELEASING[cc["type"]])
    for k in ("major", "minor", "patch"):
        if k in kinds:
            return k
    return None


def vstr(v):
    return "{}.{}.{}".format(*v)


def releases():
    """Walk main and cut it at the version tags: [{version, date, sha, commits}], newest first.
    Commits after the last tag form the "unreleased" entry (version None)."""
    tagged = tags()
    out, cur = [], []
    for c in commits():
        cur.append(c)
        if c["sha"] in tagged:
            out.append({"version": vstr(tagged[c["sha"]]), "date": c["date"][:10], "time": c["date"],
                        "sha": c["sha"], "commits": cur})
            cur = []
    if cur:
        out.append({"version": None, "date": cur[-1]["date"][:10], "time": cur[-1]["date"],
                    "sha": cur[-1]["sha"], "commits": cur})
    return list(reversed(out))


def next_version():
    rels = releases()
    last = next((r for r in rels if r["version"]), None)
    pending = rels[0]["commits"] if rels and rels[0]["version"] is None else []
    kind = level(pending)
    if not kind:
        return None
    base = tuple(map(int, last["version"].split("."))) if last else (0, 0, 0)
    return vstr(bump(base, kind))


def entry(c):
    cc = c["cc"] or {"type": "chore", "scope": None, "breaking": False, "desc": c["subject"]}
    return {"type": cc["type"], "scope": cc["scope"], "breaking": cc["breaking"], "text": cc["desc"],
            "sha": c["sha"][:7], "date": c["date"][:10], "time": c["date"]}


def build(repo_url):
    rels = releases()
    data = {"repo": repo_url, "types": TYPES, "releases": [
        {"version": r["version"], "date": r["date"], "time": r["time"], "sha": r["sha"][:7],
         "changes": [entry(c) for c in reversed(r["commits"])]} for r in rels]}
    out = ROOT / "docs" / "data" / "changelog.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    md = ["# Changelog", "",
          "Built by `scripts/changelog.py` from [Conventional Commits](https://www.conventionalcommits.org) "
          "and the version tags; versions follow [semver](https://semver.org). Do not edit by hand.", ""]
    order = ["feat", "fix", "perf", "revert", "docs", "refactor", "style", "test", "build", "ci", "chore"]
    for r in rels:
        head = f"## {r['version']} ({r['date']})" if r["version"] else "## Unreleased"
        md.append(head)
        changes = [entry(c) for c in r["commits"]]
        breaking = [e for e in changes if e["breaking"]]
        if breaking:
            md += ["", "### BREAKING CHANGES", ""] + [f"- {fmt_md(e, repo_url)}" for e in breaking]
        for t in order:
            group = [e for e in changes if e["type"] == t and not e["breaking"]]
            if group:
                md += ["", f"### {t}", ""] + [f"- {fmt_md(e, repo_url)}" for e in reversed(group)]
        md.append("")
    (ROOT / "CHANGELOG.md").write_text("\n".join(md), encoding="utf-8")
    return len(rels)


def fmt_md(e, repo_url):
    scope = f"**{e['scope']}:** " if e["scope"] else ""
    link = f" ([{e['sha']}]({repo_url}/commit/{e['sha']}))" if repo_url else f" ({e['sha']})"
    return scope + e["text"] + link


# A PR title that the agent tooling cut (#189, PR #180): the first 128 characters, a line break, then a
# marker that is cut too. CC cannot match across the line break, and the type and the scope are right,
# so the hint of the format would mislead.
CUT_MARKER = "[Content truncat"


def cut(subject):
    """Where the tooling cut a subject: the characters before its line break or truncation marker,
    else None for a whole subject."""
    m = re.search(r"[\r\n]", subject)
    if m:
        return m.start()
    i = subject.find(CUT_MARKER)
    return i if i >= 0 else None


def lint_subjects(subjects):
    bad = [(s, cut(s)) for s in subjects if not SKIP.match(s) and (parse(s) is None or cut(s) is not None)]
    whole = [s for s, n in bad if n is None]
    for s, n in bad:
        if n is None:
            print(f"not a Conventional Commit: {s!r}", file=sys.stderr)
        else:
            print(f"not a Conventional Commit, the title was cut: {len(s)} characters, the cut after {n}: "
                  f"{s!r}", file=sys.stderr)
    if len(whole) < len(bad):
        print("A cut title stays rejected: shorten the PR title, so that the whole title with its agent "
              "prefix stays under 128 characters.", file=sys.stderr)
    if whole:
        print("Use <type>(<scope>)!: <description>, type one of: " + ", ".join(TYPES), file=sys.stderr)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("release")
    sub.add_parser("next")
    b = sub.add_parser("build")
    b.add_argument("--repo", default="https://github.com/casper-assistant-ai/alerty-pl")
    lt = sub.add_parser("lint")
    lt.add_argument("range", nargs="?")
    lt.add_argument("--title")
    a = ap.parse_args()
    if a.cmd == "build":
        print(build(a.repo), "releases")
    elif a.cmd == "next":
        print(next_version() or "no release pending")
    elif a.cmd == "release":
        v = next_version()
        if not v:
            print("no releasable commits since the last tag")
            return 0
        git("tag", "-a", "v" + v, "-m", "alerty-pl v" + v, "HEAD")
        print("v" + v)
    elif a.cmd == "lint":
        if a.title is not None:
            return lint_subjects([a.title])
        subjects = [s for s in git("log", "--no-merges", "--format=%s", a.range or "HEAD~1..HEAD").splitlines()]
        return lint_subjects(subjects)
    return 0


if __name__ == "__main__":
    sys.exit(main())
