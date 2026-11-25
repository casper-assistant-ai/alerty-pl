#!/usr/bin/env python3
"""Land the agents' workflow-change issues on .github/workflows/, inside a fixed security envelope.

The agents' GITHUB_TOKEN cannot change .github/workflows/, so the process-doctor (and the
issue-worker) file each change to a workflow as an issue labelled `workflow-change`, with the exact
patch in ```diff blocks. The Workflow maintainer (.github/workflows/workflow-maintainer.yml) lands
them with no human in the loop, through this script:

  prepare --out DIR   apply each open issue's patch on top of main, compile the gh-aw sources, check
                      the change (the guard) and run the tests; write DIR/plan.json and
                      DIR/changes.bundle (one commit per issue). Reads GitHub, writes nothing there.
  land --dir DIR      push the planned commits with the deploy key (main, or a review branch with a
                      PR), land the review PRs the PR reviewer approved, comment on and close the
                      issues, and start once each failing agent whose workflow changed.
  guard BASE [HEAD]   check the changes under .github/workflows/ from BASE to HEAD (default: the
                      working tree) and print the class.

The guard sorts a change into one of three classes:
  direct   gh-aw sources (.md): the schedule, timeout-minutes, the engine's model, fallback models,
           max-turns and retries, safe-output limits (max) and the description; plain workflows
           (.yml): cron schedules and job time limits. Lands on main at once.
  review   the prompt text of a gh-aw source (agents read it as standing instructions, and the
           process-doctor's own input quotes agent output that quotes public issues), and every
           change the issue-worker asks for (it reads issues from the public). Lands after the PR
           reviewer agent approves it.
  refuse   everything else, left with the label needs-casper for Casper or the owner: `run:`
           scripts (they run with the workflow's token and secrets, and no denylist can tell a
           harmless line from one that sends a key away; security audit #146), permissions,
           network, tools, steps, imports, secrets, triggers other than the schedule, other
           safe-output settings, engine endpoints, new, deleted or shared files, the maintainer's
           own workflow, `${{ }}` expressions or imports in new prompt lines.

workflow-maintainer.yml pins this file by its SHA-256 before it hands the deploy key to it: the
agents may change scripts/**, so a change here needs the pin changed too, which only Casper or
the owner can push.
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC
from pathlib import Path

try:
    import yaml
except ImportError:  # the guard refuses everything without a YAML parser
    yaml = None

WF = ".github/workflows/"
TARGET = re.compile(r"^\.github/workflows/[a-z0-9][a-z0-9-]*\.(md|yml)$")
PATH_RX = re.compile(r"\.github/workflows/[A-Za-z0-9_./-]+?\.(?:md|yml)\b")
SOURCE_RX = re.compile(r"<!-- gh-aw-workflow-id: ([a-z0-9-]+) -->")
# the agents whose workflow-change issues land here, and the least review each one gets
SOURCES = {"process-doctor": "direct", "issue-worker": "review"}
BOT = "github-actions[bot]"
MARK = "<!-- workflow-maintainer:"
DIFF_LANGS = {"diff", "patch", "udiff"}
HEADER = re.compile(r"^(diff --git |index [0-9a-f]|--- (a/|/dev/null|\.github/)|\+\+\+ (b/|/dev/null|\.github/))")
MODEL = re.compile(r"^glm-[0-9][a-z0-9.-]*$")
# at most two runs an hour: the minute field is one or two numbers
CRON = re.compile(r"^\d{1,2}(,\d{1,2})? [0-9*/,-]+ [0-9*/,-]+ [0-9A-Za-z*/,-]+ [0-9A-Za-z*/,-]+$")
FUZZY = re.compile(r"^[a-z0-9 :,-]{3,60}$")
BAD_PROMPT = re.compile(r"\$\{\{|^\s*(@include|@import|\{\{#import|\{\{#runtime-import)", re.I)
SELF = ".github/workflows/workflow-maintainer.yml"
NEEDS = "needs-casper"
MISSING = object()
TRAILER = "Workflow-Change-Issue"


class PatchError(Exception):
    pass


class Refused(PatchError):
    """The guard refused the change: it is for Casper or the owner, not for a corrected patch."""


# ---------------------------------------------------------------- reading the patch of an issue

def blocks(body):
    """([(text before, language, lines)] of the fenced blocks of an issue body, the text after the last)."""
    lines = (body or "").replace("\r\n", "\n").split("\n")
    out, i, start = [], 0, 0
    while i < len(lines):
        m = re.match(r"^([ \t]*)(`{3,}|~{3,})[ \t]*([\w+-]*)", lines[i])
        if not m:
            i += 1
            continue
        indent, fence, lang = m.group(1), m.group(2), m.group(3).lower()
        close = re.compile(r"^[ \t]*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$")
        j, content = i + 1, []
        while j < len(lines) and not close.match(lines[j]):
            s = lines[j]
            content.append(s[len(indent):] if indent and s.startswith(indent) else s)
            j += 1
        out.append(("\n".join(lines[start:i]), lang, content))
        i = start = j + 1
    return out, "\n".join(lines[start:])


def target(before, lines):
    """The file a diff block changes: its `+++ b/` header, else the last workflow path named before it."""
    for s in lines[:4]:
        m = re.match(r"^\+\+\+ (?:b/)?(\S+)", s)
        if m:
            return m.group(1)
    named = [m.group(0) for m in PATH_RX.finditer(before)]
    return named[-1] if named else None


def hunks(lines):
    """[(hunk, line hint)] of a diff block; a hunk is a list of (tag, text), tag ' ', '-' or '+'."""
    out, cur, hint, started = [], [], None, False
    for s in lines:
        if not started and HEADER.match(s):
            continue
        if s.startswith("@@"):
            if cur:
                out.append((cur, hint))
            cur = []
            m = re.match(r"^@@ -(\d+)", s)
            hint = int(m.group(1)) if m else None
            started = True
            continue
        started = True
        if s == "":
            cur.append((" ", ""))
        elif s[0] in " -+":
            cur.append((s[0], s[1:]))
        elif s[0] == "\\":
            continue  # "\ No newline at end of file"
        else:
            raise PatchError(f"not a diff line: {s[:60]!r}")
    if cur:
        out.append((cur, hint))
    return out


def _find(lines, seq, norm):
    want = [norm(x) for x in seq]
    n = len(want)
    return [i for i in range(len(lines) - n + 1)
            if norm(lines[i]) == want[0] and [norm(x) for x in lines[i:i + n]] == want]


def _trim(hunk):
    """The hunk without blank context lines at its ends (markdown adds them; the file may not have them)."""
    a, b = 0, len(hunk)
    while a < b and hunk[a] == (" ", ""):
        a += 1
    while b > a and hunk[b - 1] == (" ", ""):
        b -= 1
    return hunk[a:b]


def apply_hunk(lines, hunk, hint=None):
    """(new lines, 'applied' | 'already' | 'same'); raises PatchError when the hunk has no single place."""
    for h in (hunk, _trim(hunk)):
        old = [t for tag, t in h if tag in " -"]
        new = [t for tag, t in h if tag in " +"]
        if old == new:
            return lines, "same"
        if not old:
            raise PatchError("a hunk with no context lines: its place in the file is unknown")
        for norm in (lambda s: s, lambda s: s.rstrip()):
            at = _find(lines, old, norm)
            if len(at) > 1 and hint:
                at = [min(at, key=lambda i: abs(i + 1 - hint))]
            if len(at) == 1:
                i = at[0]
                return lines[:i] + new + lines[i + len(old):], "applied"
            if len(at) > 1:
                raise PatchError(f"its lines match {len(at)} places in the file")
            if _find(lines, new, norm):
                return lines, "already"
    first = next((t for tag, t in hunk if tag in " -" and t.strip()), "")
    raise PatchError(f"its old lines are not in the file on main (first one: {first.strip()[:70]!r})")


def apply_issue(body, root="."):
    """Apply every ```diff block of an issue body to the files under root.

    Returns {'files': {path: 'applied' | 'already'}, 'errors': [...], 'named_only': [...]}; the
    caller undoes the working tree when there are errors. named_only: workflow files the text after
    the last block names but no block changes (a change asked in prose, which is not applied)."""
    found, tail = blocks(body)
    files, errors, touched = {}, [], set()
    for before, lang, lines in found:
        if lang not in DIFF_LANGS:
            continue
        path = target(before, lines)
        if not path:
            errors.append("a ```diff block names no file: give it `--- a/.github/workflows/<file>` and `+++ b/…` lines")
            continue
        touched.add(path)
        if path.endswith(".lock.yml") or not TARGET.match(path):
            errors.append(f"`{path}`: only the sources .github/workflows/<name>.md and plain <name>.yml change here "
                          "(lock files are compiled, shared imports stay as they are)")
            continue
        file = Path(root, path)
        if not file.is_file():
            errors.append(f"`{path}`: no such file on main")
            continue
        text = file.read_text()
        cur = text.split("\n")
        try:
            hs = hunks(lines)
        except PatchError as e:
            errors.append(f"`{path}`: {e}")
            continue
        if not hs:
            errors.append(f"`{path}`: the diff block is empty")
            continue
        states = []
        for k, (h, hint) in enumerate(hs, 1):
            try:
                cur, state = apply_hunk(cur, h, hint)
            except PatchError as e:
                errors.append(f"`{path}`, hunk {k} of {len(hs)}: {e}")
                break
            states.append(state)
        else:
            new = "\n".join(cur)
            if new != text:
                file.write_text(new)
            prev = files.get(path)
            state = "already" if all(s != "applied" for s in states) else "applied"
            files[path] = "applied" if "applied" in (prev, state) else state
    if not files and not errors:
        errors.append("the issue has no ```diff block")
    named = {m.group(0) for m in PATH_RX.finditer(tail)}
    named_only = sorted(p for p in named if TARGET.match(p) and p not in touched)
    return {"files": files, "errors": errors, "named_only": named_only}


# ---------------------------------------------------------------- the guard

def _without(d, *keys):
    return {k: v for k, v in d.items() if k not in keys}


def _key(k):
    return "on" if k is True else str(k)


def _int(name, v, lo, hi):
    ok = isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi
    return [] if ok else [f"{name} must be a whole number from {lo} to {hi}, not {v!r}"]


def added_lines(a, b):
    return [s[1:] for s in difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), lineterm="", n=0)
            if s.startswith("+") and not s.startswith("+++")]


def split_md(text):
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text or "", re.S)
    if not m:
        raise ValueError("no frontmatter between --- lines")
    return m.group(1), text[m.end():]


def check_on(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return ["the triggers changed form"]
    if _without(a, "schedule") != _without(b, "schedule"):
        return ["a trigger other than the schedule changed"]
    s = b.get("schedule", MISSING)
    if s is MISSING:
        return ["the schedule was removed"]
    if isinstance(s, str):
        return [] if FUZZY.match(s) else [f"schedule {s!r} is not a plain schedule like `daily`"]
    if (isinstance(s, list) and 0 < len(s) <= 3
            and all(isinstance(e, dict) and set(e) == {"cron"} and isinstance(e["cron"], str) and CRON.match(e["cron"])
                    for e in s)):
        return []
    return [f"schedule {s!r}: up to three `cron:` entries whose minute field is one or two numbers"]


def check_engine(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return ["the engine changed"]
    p = []
    keep = ("model", "fallback-models", "max-turns", "env")
    if _without(a, *keep) != _without(b, *keep):
        p.append("the engine changed beyond model, fallback-models, max-turns and CLAUDE_CODE_MAX_RETRIES")
    ae, be = a.get("env") or {}, b.get("env") or {}
    if not isinstance(ae, dict) or not isinstance(be, dict) \
            or _without(ae, "CLAUDE_CODE_MAX_RETRIES") != _without(be, "CLAUDE_CODE_MAX_RETRIES"):
        p.append("the engine's env changed beyond CLAUDE_CODE_MAX_RETRIES")
    elif "CLAUDE_CODE_MAX_RETRIES" in be and not re.fullmatch(r"\d{1,2}", str(be["CLAUDE_CODE_MAX_RETRIES"])):
        p.append("CLAUDE_CODE_MAX_RETRIES must be a number up to 99")
    if "model" in b and not MODEL.match(str(b["model"])):
        p.append(f"model {b['model']!r} is not a z.ai GLM model")
    fm = b.get("fallback-models", [])
    if not isinstance(fm, list) or len(fm) > 4 or not all(MODEL.match(str(x)) for x in fm):
        p.append("fallback-models: up to four z.ai GLM models")
    if a.get("max-turns") != b.get("max-turns") and "max-turns" in b:
        p += _int("engine.max-turns", b["max-turns"], 5, 500)
    return p


def check_safe_outputs(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict) or set(a) != set(b):
        return ["safe outputs were added or removed"]
    p = []
    for k in a:
        x, y = a[k], b[k]
        if x == y:
            continue
        if isinstance(x, dict) and isinstance(y, dict) and _without(x, "max") == _without(y, "max"):
            p += _int(f"safe-outputs.{k}.max", y.get("max"), 1, 20)
        else:
            p.append(f"safe-outputs.{k} changed beyond its max")
    return p


def check_md(old, new):
    """(problems, needs review) for a gh-aw source: frontmatter keys in the allowed set, prompt text."""
    try:
        ofm, obody = split_md(old)
        nfm, nbody = split_md(new)
        o, n = yaml.safe_load(ofm) or {}, yaml.safe_load(nfm) or {}
    except (ValueError, yaml.YAMLError) as e:
        return [f"cannot read the frontmatter ({str(e).splitlines()[0]})"], False
    if not isinstance(o, dict) or not isinstance(n, dict):
        return ["the frontmatter is not a mapping"], False
    p = []
    for k in sorted(set(o) | set(n), key=_key):
        a, b = o.get(k, MISSING), n.get(k, MISSING)
        if a == b:
            continue
        if MISSING in (a, b):
            p.append(f"`{_key(k)}` was added or removed")
        elif k == "timeout-minutes":
            p += _int("timeout-minutes", b, 5, 90)
        elif k in ("on", True):
            p += check_on(a, b)
        elif k == "engine":
            p += check_engine(a, b)
        elif k == "safe-outputs":
            p += check_safe_outputs(a, b)
        elif k != "description":
            p.append(f"`{_key(k)}` changed; only the schedule, timeout-minutes, the engine's model, fallback "
                     "models, max-turns and retries, safe-output max, the description and the prompt may")
    for line in added_lines(obody, nbody):
        if BAD_PROMPT.search(line):
            p.append(f"a new prompt line holds an expression or an import: {line.strip()[:80]!r}")
    # the prompt is standing instructions for an agent with write tools: the PR reviewer reads it first
    return p, obody != nbody


def check_jobs(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict) or set(a) != set(b):
        return ["jobs were added or removed"], False
    p, review = [], False
    for j in a:
        x, y = a[j], b[j]
        if x == y:
            continue
        if not isinstance(x, dict) or not isinstance(y, dict) \
                or _without(x, "timeout-minutes", "steps") != _without(y, "timeout-minutes", "steps"):
            p.append(f"job `{j}` changed beyond timeout-minutes and its run scripts")
            continue
        if x.get("timeout-minutes") != y.get("timeout-minutes"):
            p += _int(f"jobs.{j}.timeout-minutes", y.get("timeout-minutes"), 1, 120)
        xs, ys = x.get("steps") or [], y.get("steps") or []
        if len(xs) != len(ys):
            p.append(f"job `{j}`: steps were added or removed")
            continue
        for i, (s, t) in enumerate(zip(xs, ys, strict=True), 1):
            if s == t:
                continue
            if not isinstance(s, dict) or not isinstance(t, dict) or _without(s, "run") != _without(t, "run"):
                p.append(f"job `{j}`, step {i}: changed beyond its run script")
            elif s.get("run") != t.get("run"):
                p.append(f"job `{j}`, step {i}: its `run:` script changed; scripts run with the workflow's token and "
                         "secrets, so Casper or the owner applies such a change by hand")
    return p, review


def check_yml(old, new):
    """(problems, needs review) for a plain workflow: schedules, job time limits, run scripts."""
    try:
        o, n = yaml.safe_load(old), yaml.safe_load(new)
    except yaml.YAMLError as e:
        return [f"not valid YAML ({str(e).splitlines()[0]})"], False
    if not isinstance(o, dict) or not isinstance(n, dict):
        return ["not a workflow"], False
    p, review = [], False
    for k in sorted(set(o) | set(n), key=_key):
        a, b = o.get(k, MISSING), n.get(k, MISSING)
        if a == b:
            continue
        if MISSING in (a, b):
            p.append(f"`{_key(k)}` was added or removed")
        elif k in ("on", True):
            p += check_on(a, b)
        elif k == "jobs":
            q, r = check_jobs(a, b)
            p += q
            review = review or r
        else:
            p.append(f"`{_key(k)}` changed; only schedules, job time limits and run scripts may")
    return p, review


def lock_version(text):
    m = re.search(r'"compiler_version":"([^"]+)"', text or "")
    return m.group(1) if m else None


def _read(ref, path):
    if ref is None:
        f = Path(path)
        return f.read_text() if f.is_file() else None
    r = subprocess.run(["git", "show", f"{ref}:{path}"], text=True, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def changed_paths(base, head=None):
    if head is None:
        diff = git("diff", "--name-status", base)
        # new files count only under .github/: only those are committed (git add -- .github/workflows/)
        new = git("ls-files", "--others", "--exclude-standard", "--", ".github/")
    else:
        diff, new = git("diff", "--name-status", base, head), ""
    out = []
    for line in diff.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out.append((parts[0][:1], parts[-1]))
    return out + [("A", p) for p in new.splitlines() if p]


def guard(base, head=None):
    """('direct' | 'review' | 'refuse', problems) for the changes from base to head (None: the working tree)."""
    if yaml is None:
        return "refuse", ["no YAML parser (python3-yaml) on this runner"]
    paths = changed_paths(base, head)
    if not paths:
        return "refuse", ["nothing changed"]
    names = {p for _, p in paths}
    problems, review = [], False
    for status, path in paths:
        if status != "M":
            what = {"A": "added", "D": "deleted"}.get(status, "renamed or copied")
            problems.append(f"`{path}` was {what}: only existing workflows change here")
            continue
        if not path.startswith(WF):
            problems.append(f"`{path}` is outside .github/workflows/")
            continue
        old, new = _read(base, path), _read(head, path)
        if path.endswith(".lock.yml"):
            if path[:-len(".lock.yml")] + ".md" not in names:
                problems.append(f"`{path}`: a compiled lock file changed without its source")
            elif lock_version(old) != lock_version(new):
                problems.append(f"`{path}`: compiled by gh-aw {lock_version(new)}, the repository uses {lock_version(old)}")
            continue
        if not TARGET.match(path):
            problems.append(f"`{path}`: only .github/workflows/<name>.md and .yml change here")
            continue
        if path == SELF:
            problems.append(f"`{path}`: the maintainer does not change its own workflow")
            continue
        if path.endswith(".md"):
            q, r = check_md(old, new)
            lock = path[:-3] + ".lock.yml"
            if lock not in names and _read(base, lock) is not None:
                q.append(f"changed, but `{lock}` was not compiled again")
        else:
            q, r = check_yml(old, new)
        problems += [f"`{path}`: {x}" for x in q]
        review = review or r
    if problems:
        return "refuse", problems
    return ("review" if review else "direct"), []


# ---------------------------------------------------------------- git and GitHub

def sh(*cmd, check=True, env=None, tries=1):
    """Run a command; a gh write is tried up to `tries` times (GitHub answers 500 and 502 at times)."""
    import time
    for k in range(tries):
        r = subprocess.run(list(cmd), text=True, capture_output=True, env=env)
        if r.returncode == 0:
            break
        if k + 1 < tries:
            time.sleep(15 * (k + 1))
    if r.returncode != 0:
        why = f"`{' '.join(cmd[:3])}` exited {r.returncode}: {(r.stderr or r.stdout).strip()[-600:]}"
        if check:
            raise RuntimeError(why)
        print(f"::warning::{why}")
    return r.stdout


def git(*args, check=True):
    return sh("git", *args, check=check)


def gh_api(path, *extra):
    out = sh("gh", "api", path, *extra)
    return json.loads(out) if out.strip() else None


def gh_items(path):
    out = sh("gh", "api", "--paginate", path, "--jq", ".[] | tojson")
    return [json.loads(s) for s in out.splitlines() if s.strip()]


def repo():
    return os.environ["GITHUB_REPOSITORY"]


def source_of(issue):
    """The agent that filed an issue, when the maintainer takes its workflow changes, else None.

    gh-aw ends the body with its own footer; the last workflow-id marker is gh-aw's, and the title
    prefix that gh-aw puts on that agent's issues must match it."""
    if (issue.get("user") or {}).get("login") != BOT or issue.get("pull_request"):
        return None
    found = SOURCE_RX.findall(issue.get("body") or "")
    src = found[-1] if found else None
    if src in SOURCES and (issue.get("title") or "").startswith(f"[{src}] "):
        return src
    return None


def digest(body):
    return hashlib.sha256((body or "").encode()).hexdigest()[:12]


def marker(n, h, result):
    return f"{MARK} issue={n} body={h} result={result} -->"


def handled(comments, h):
    """True when the maintainer already ended this exact patch. «In review» ends nothing: while its PR is
    open the caller skips the issue, and when the PR is gone without a result the patch is tried again."""
    return any((c.get("user") or {}).get("login") == BOT and MARK in (c.get("body") or "")
               and f" body={h} " in c.get("body") and " result=review " not in c.get("body") for c in comments)


def identity():
    git("config", "user.name", "alerty-pl bot")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")


def reset_tree():
    git("reset", "-q", "--hard")
    git("clean", "-q", "-fd", "--", ".github/")


def compile_sources(paths):
    for p in paths:
        if p.endswith(".md"):
            sh("gh", "aw", "compile", Path(p).stem)


def run_tests():
    """(ok, log): the unit and node tests, as CI runs them."""
    log = []
    nodes = sorted(str(p) for p in Path("tests").glob("*.test.mjs"))
    for cmd in (["python3", "-I", "-m", "unittest", "discover", "-s", "tests"], ["node", "--test", *nodes]):
        if cmd[0] == "node" and not nodes:
            continue
        r = subprocess.run(cmd, text=True, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        log.append(f"$ {' '.join(cmd[:6])}\n{(r.stdout + r.stderr)[-2500:]}")
        if r.returncode:
            return False, "\n".join(log)
    return True, "\n".join(log)


def subject(issue):
    t = re.sub(r"^\[[a-z0-9-]+\]\s*", "", issue["title"])
    t = re.sub(r"^workflow change:\s*", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()[:90]


def commit(issue, cls, files):
    msg = (f"ci(workflows): {subject(issue)} (#{issue['number']})\n\n"
           f"Applied by the Workflow maintainer from #{issue['number']} ({cls}: {', '.join(Path(f).name for f in files)}).\n\n"
           f"{TRAILER}: {issue['number']}\n")
    git("add", "-A", "--", WF)
    git("commit", "-q", "-m", msg)
    return git("rev-parse", "HEAD").strip()


def attempt(issue, src):
    """Apply one issue in the working tree on top of HEAD: (class, files, named_only) or raises PatchError."""
    res = apply_issue(issue["body"])
    if res["errors"]:
        raise PatchError("; ".join(res["errors"]))
    changed = sorted(p for p, s in res["files"].items() if s == "applied")
    if not changed:
        return "already", [], res["named_only"]
    try:
        compile_sources(changed)
    except RuntimeError as e:
        raise PatchError(f"gh aw compile failed: {e}") from e
    cls, problems = guard("HEAD")
    if cls == "refuse":
        raise Refused("; ".join(problems))
    ok, log = run_tests()
    if not ok:
        raise PatchError("the tests fail with the patch:\n\n```text\n" + log[-2000:] + "\n```")
    if SOURCES[src] == "review":
        cls = "review"
    files = sorted(p for _, p in changed_paths("HEAD"))
    return cls, files, res["named_only"]


def prepare(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    identity()
    git("fetch", "-q", "origin", "main")
    git("checkout", "-q", "-B", "wm/main", "origin/main")
    issues = gh_api(f"repos/{repo()}/issues?labels=workflow-change&state=open&per_page=100&sort=created&direction=asc") or []
    in_review = {p["head"]["ref"] for p in gh_items(f"repos/{repo()}/pulls?state=open&per_page=100")}
    plan, branches = [], []
    for issue in issues:
        src = source_of(issue)
        if not src:
            continue
        n, h = issue["number"], digest(issue["body"])
        if f"workflow-change/{n}" in in_review or handled(gh_items(f"repos/{repo()}/issues/{n}/comments?per_page=100"), h):
            continue
        item = {"issue": n, "title": issue["title"], "digest": h, "source": src}
        try:
            cls, files, named_only = attempt(issue, src)
        except PatchError as e:
            reset_tree()
            item.update(result="refused" if isinstance(e, Refused) else "failed", reason=str(e))
            plan.append(item)
            print(f"#{n}: not applied: {str(e)[:300]}")
            continue
        item.update(named_only=named_only, files=files)
        if cls == "already":
            reset_tree()
            item.update(result="already")
        elif cls == "direct":
            item.update(result="partial" if named_only else "applied", cls=cls, commit=commit(issue, cls, files))
        else:
            # a review change goes alone into its own branch from main, so its PR shows only it
            reset_tree()
            branch = f"workflow-change/{n}"
            git("checkout", "-q", "-B", branch, "origin/main")
            try:
                cls2, files, named_only = attempt(issue, src)
                if cls2 == "already":
                    raise PatchError("its change is already on main")
                item.update(result="review", cls="review", branch=branch, commit=commit(issue, "review", files),
                            files=files, named_only=named_only)
                branches.append(branch)
            except PatchError as e:
                reset_tree()
                item.update(result="refused" if isinstance(e, Refused) else "failed",
                            reason=f"in its own branch from main: {e}")
            git("checkout", "-q", "wm/main")
        plan.append(item)
        print(f"#{n}: {item['result']}")
    (out / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    refs = (["wm/main"] if git("rev-list", "--count", "origin/main..wm/main").strip() != "0" else []) + branches
    if refs:
        git("bundle", "create", str(out / "changes.bundle"), *refs, "^origin/main")
    return plan


# ---------------------------------------------------------------- landing

def comment(n, text):
    sh("gh", "issue", "comment", str(n), "-R", repo(), "--body", text, tries=4)


def close(n, text):
    sh("gh", "issue", "close", str(n), "-R", repo(), "--reason", "completed", "--comment", text, tries=4)


def close_pr(num, ref, text):
    """Comment on a review PR, close it and delete its branch (the job's GITHUB_TOKEN may not delete branches)."""
    sh("gh", "api", f"repos/{repo()}/issues/{num}/comments", "-f", f"body={text}", check=False, tries=4)
    sh("gh", "api", "-X", "PATCH", f"repos/{repo()}/pulls/{num}", "-f", "state=closed", check=False, tries=4)
    git("push", "-q", "deploy", "--delete", ref, check=False)


def commit_url(sha):
    return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo()}/commit/{sha}"


def run_url():
    return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo()}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"


def push(ref, branch, force=False):
    args = ["push", "-q"] + (["--force"] if force else []) + ["deploy", f"{ref}:refs/heads/{branch}"]
    r = subprocess.run(["git", *args], text=True, capture_output=True)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def land_on_main(ref, expect):
    """Rebase ref's commits onto the newest main, check each again, push: {issue: sha}."""
    last = ""
    for _ in range(3):
        git("fetch", "-q", "origin", "main")
        git("checkout", "-q", "-B", "land", ref)
        if subprocess.run(["git", "rebase", "-q", "origin/main"], capture_output=True).returncode:
            git("rebase", "--abort", check=False)
            raise RuntimeError("main changed the same lines meanwhile; the next run applies the patch again")
        landed = {}
        for c in git("rev-list", "--reverse", "origin/main..HEAD").split():
            cls, problems = guard(f"{c}^", c)
            if cls not in expect:
                raise RuntimeError(f"the guard says {cls} for {c[:7]} after the rebase: {'; '.join(problems)}")
            m = re.search(rf"^{TRAILER}: (\d+)$", git("log", "-1", "--format=%B", c), re.M)
            if m:
                landed[int(m.group(1))] = c
        ok, last = push("HEAD", "main")
        if ok:
            return landed
    raise RuntimeError(f"the push to main failed: {last[-300:]}")


def health_issues():
    """{workflow lock file: health issue number} of the open agent-health issues."""
    out = {}
    for i in gh_api(f"repos/{repo()}/issues?labels=agent-health&state=open&per_page=100") or []:
        m = re.search(r"<!-- agent-health: \.github/workflows/([a-z0-9-]+\.lock\.yml) -->", i.get("body") or "")
        if m:
            out[m.group(1)] = i["number"]
    return out


def start_checks(files, health):
    """Start once each agent whose workflow changed and whose runs fail: its next good run closes the health issue."""
    started = []
    for f in files:
        if f.endswith(".md"):
            lock = Path(f).stem + ".lock.yml"
            if lock in health and subprocess.run(["gh", "workflow", "run", lock, "-R", repo()],
                                                 capture_output=True).returncode == 0:
                started.append(f"started `{Path(f).stem}` once to check the change (health issue #{health[lock]})")
    return started


def started_within(workflow, minutes):
    out = sh("gh", "run", "list", "-R", repo(), "--workflow", workflow, "--limit", "1", "--json", "createdAt",
             "--jq", ".[0].createdAt // \"\"", check=False).strip()
    if not out:
        return False
    from datetime import datetime
    age = datetime.now(UTC) - datetime.fromisoformat(out.replace("Z", "+00:00"))
    return age.total_seconds() < minutes * 60


def busy(workflow):
    out = sh("gh", "run", "list", "-R", repo(), "--workflow", workflow, "--limit", "10", "--json", "status",
             "--jq", '[.[] | select(.status != "completed")] | length', check=False)
    return (out.strip() or "0") != "0"


def approve_ci(sha):
    """CI on a PR that github-actions[bot] opened waits for an approval (as for the agents' PRs): give it."""
    runs = (gh_api(f"repos/{repo()}/actions/runs?head_sha={sha}&status=action_required") or {}).get("workflow_runs", [])
    for r in runs:
        sh("gh", "api", "-X", "POST", f"repos/{repo()}/actions/runs/{r['id']}/approve", check=False)
        print(f"approved CI run {r['id']} for {sha[:7]}")


REVIEWED = {"COMMENTED", "APPROVED", "CHANGES_REQUESTED"}


def verdict_in(reviews, sha):
    """(verdict, reason) of the PR reviewer's review of commit sha, or (None, '').

    Read from the PR's reviews, never from comments: every agent comments as github-actions[bot],
    but only the pr-reviewer workflow has the submit-pull-request-review safe output (#165). The
    same rule as scripts/gate_rules.py verdict; tests/test_gate_rules.py runs both on one set."""
    for r in reversed(reviews or []):
        body = (r.get("body") or "").replace("\r", "")
        if (r.get("user") or {}).get("login") != BOT or r.get("state") not in REVIEWED or r.get("commit_id") != sha:
            continue
        if not re.search(rf"(?m)^Head: *{re.escape(sha)}\s*$", body):
            continue
        v = re.search(r"(?m)^Verdict: *(approve|changes|reject)\b", body)
        if v:
            m = re.search(r"(?m)^Reason: *(.*)$", body)
            return v.group(1), (m.group(1).strip() if m else "")
    return None, ""


def verdict_of(pr, sha):
    """(verdict, reason) of the PR reviewer's review of this exact head, or (None, '')."""
    return verdict_in(gh_items(f"repos/{repo()}/pulls/{pr}/reviews?per_page=100"), sha)


def refuse_note():
    return ("This change is outside what lands with no human. Casper or the owner reads the patch and applies it by "
            "hand (label `needs-casper`); the process-doctor does not file it again.\n\n")


def report(item, extra=""):
    n, h, res = item["issue"], item["digest"], item["result"]
    head = {"failed": "Workflow maintainer: not applied.",
            "refused": "Workflow maintainer: not applied, the guard refused it.",
            "already": "Workflow maintainer: the patch is already on main; nothing to apply."}[res]
    body = head + "\n\n" + (f"Reason: {item.get('reason', '')}\n\n" if item.get("reason") else "")
    if res == "refused":
        body += refuse_note()
        sh("gh", "issue", "edit", str(n), "-R", repo(), "--add-label", NEEDS, check=False, tries=4)
    if res == "failed":
        body += ("The issue stays open. The process-doctor closes it and opens a corrected one: each change as a "
                 "```diff block with `--- a/<path>` and `+++ b/<path>` lines and unchanged context lines copied "
                 "from main.\n\n")
    body += f"Run: {run_url()}\n\n{marker(n, h, res)}" + extra
    if res == "already":
        close(n, body)
    else:
        comment(n, body)


def land(d):
    d = Path(d)
    plan = json.loads((d / "plan.json").read_text()) if (d / "plan.json").is_file() else []
    identity()
    git("remote", "add", "deploy", f"git@github.com:{repo()}.git", check=False)
    git("fetch", "-q", "origin", "main")
    if (d / "changes.bundle").is_file():
        git("fetch", "-q", str(d / "changes.bundle"), "+refs/heads/*:refs/remotes/wc/*")
    health = health_issues()
    started = set()
    doctor = False  # a doctor's patch was refused, failed or applied in part: it should answer soon
    # 1. direct changes: onto main at once
    direct = [i for i in plan if i.get("cls") == "direct"]
    if direct:
        try:
            landed = land_on_main("refs/remotes/wc/wm/main", {"direct"})
        except RuntimeError as e:
            print(f"::warning::direct changes not landed: {e}")
            landed = {}
        for item in direct:
            sha = landed.get(item["issue"])
            if not sha:
                continue
            files = ", ".join(f"`{f}`" for f in item["files"])
            checks = [s for s in start_checks(item["files"], health) if s not in started]
            started.update(checks)
            body = (f"Workflow maintainer: applied in {commit_url(sha)}.\n\nFiles: {files}. The guard allowed it as a "
                    "direct change (schedules, time limits, models, retries and safe-output limits only); the gh-aw "
                    "sources were compiled again and the unit and node tests pass.\n\n")
            if checks:
                body += "".join(f"- {c}\n" for c in checks) + "\n"
            if item["result"] == "partial":
                body += ("Not applied: " + ", ".join(f"`{p}`" for p in item["named_only"]) + " is named after the last "
                         "diff block but has no ```diff block of its own. The process-doctor opens a new issue with its "
                         "diff if the change is still needed, then closes this one.\n\n")
            body += f"Run: {run_url()}\n\n{marker(item['issue'], item['digest'], item['result'])}"
            if item["result"] == "partial":
                comment(item["issue"], body)
                doctor = doctor or item.get("source") == "process-doctor"
            else:
                close(item["issue"], body)
            print(f"#{item['issue']}: landed {sha[:7]}")
    # 2. new review changes: a branch and a PR for the PR reviewer
    review_started = False
    for item in [i for i in plan if i.get("result") == "review"]:
        n, branch = item["issue"], item["branch"]
        ok, err = push(f"refs/remotes/wc/{branch}", branch, force=True)
        if not ok:
            print(f"::warning::#{n}: push of {branch} failed: {err[-300:]}")
            continue
        files = ", ".join(f"`{f}`" for f in item["files"])
        body = (f"Closes #{n}\n\nThe Workflow maintainer applied the patch of #{n} to {files}. It changes an agent's "
                "prompt (or comes from an agent that reads public issues), so it lands only after the PR reviewer "
                "approves this head; the maintainer then puts it on main itself (the gate's GITHUB_TOKEN cannot merge "
                f"workflow files).\n\nThe guard checked that permissions, triggers, steps, scripts, actions and "
                f"secrets stay as they are; the unit and node tests pass.\n\nRun: {run_url()}")
        title = f"[workflow-maintainer] ci(workflows): {subject({'title': item['title']})}"
        r = subprocess.run(["gh", "pr", "create", "-R", repo(), "--head", branch, "--base", "main", "--title", title,
                            "--body", body, "--label", "pipeline", "--label", "workflow-change"],
                           text=True, capture_output=True)
        if r.returncode:
            print(f"::warning::#{n}: PR not opened: {(r.stderr or r.stdout).strip()[-300:]}")
            continue
        pr = r.stdout.strip().rsplit("/", 1)[-1]
        comment(n, f"Workflow maintainer: the patch is in review as #{pr}: it lands when the PR reviewer approves it.\n\n"
                   f"Run: {run_url()}\n\n{marker(n, item['digest'], 'review')}")
        review_started = True
        print(f"#{n}: in review as #{pr}")
    # 3. review PRs from earlier runs (a refused one gets the label needs-casper, made here)
    sh("gh", "label", "create", NEEDS, "-R", repo(), "--force", "--color", "b60205",
       "--description", "Casper or the owner applies this by hand", check=False)
    for pr in gh_items(f"repos/{repo()}/pulls?state=open&per_page=100"):
        ref = pr["head"]["ref"]
        m = re.fullmatch(r"workflow-change/(\d+)", ref)
        if not m or (pr.get("user") or {}).get("login") != BOT or pr["head"]["repo"]["full_name"] != repo():
            continue
        n, num, sha = int(m.group(1)), pr["number"], pr["head"]["sha"]
        git("fetch", "-q", "origin", f"+refs/heads/{ref}:refs/remotes/origin/{ref}")
        base = git("merge-base", "origin/main", sha).strip()
        cls, problems = guard(base, sha)
        if cls == "refuse":
            text = "Workflow maintainer: closed without landing, the guard refuses it: " + "; ".join(problems)
            close_pr(num, ref, text)
            issue = gh_api(f"repos/{repo()}/issues/{n}") or {}
            sh("gh", "issue", "edit", str(n), "-R", repo(), "--add-label", NEEDS, check=False, tries=4)
            comment(n, f"{text}\n\nPR: #{num}\n\n{refuse_note()}{marker(n, digest(issue.get('body')), 'refused')}")
            print(f"#{n}: PR #{num} closed, refused by the guard")
            continue
        approve_ci(sha)
        verdict, reason = verdict_of(num, sha)
        if verdict is None:
            review_started = True
            continue
        if verdict in ("changes", "reject"):
            text = (f"Workflow maintainer: closed without landing. The PR reviewer said «{verdict}»: {reason or 'see its comment'}\n\n"
                    "The process-doctor opens a corrected workflow-change issue if the change is still needed.")
            close_pr(num, ref, text)
            issue = gh_api(f"repos/{repo()}/issues/{n}") or {}
            comment(n, f"{text}\n\nPR: #{num}\n\n{marker(n, digest(issue.get('body')), 'refused')}")
            doctor = doctor or source_of(issue) == "process-doctor"
            print(f"#{n}: PR #{num} closed, the reviewer said {verdict}")
            continue
        try:
            landed = land_on_main(f"refs/remotes/origin/{ref}", {"direct", "review"})
            sha2 = landed.get(n) or git("rev-parse", "HEAD").strip()
        except RuntimeError as e:
            print(f"::warning::#{n}: PR #{num} approved but not landed: {e}")
            continue
        if sha2 != sha:  # rebased: the PR closes by hand, its head is no longer the landed commit
            close_pr(num, ref, f"Workflow maintainer: approved by the PR reviewer and landed on main as {commit_url(sha2)}.")
        else:  # main now holds the PR's head: GitHub marks the PR merged; the branch goes
            git("push", "-q", "deploy", "--delete", ref, check=False)
        issue = gh_api(f"repos/{repo()}/issues/{n}") or {}
        if issue.get("state") == "open":
            checks = start_checks([f for f in git("diff", "--name-only", f"{sha2}^", sha2).split()], health)
            close(n, f"Workflow maintainer: landed in {commit_url(sha2)} after the PR reviewer approved #{num}: {reason}\n\n"
                     + "".join(f"- {c}\n" for c in checks)
                     + f"\nRun: {run_url()}\n\n{marker(n, digest(issue.get('body')), 'applied')}")
        print(f"#{n}: PR #{num} landed {sha2[:7]}")
    # the PR reviewer also runs every 3 hours by itself; start it at most once an hour
    if review_started and not busy("pr-reviewer.lock.yml") and not started_within("pr-reviewer.lock.yml", 60):
        sh("gh", "workflow", "run", "pr-reviewer.lock.yml", "-R", repo(), check=False)
        print("started the PR reviewer")
    # 4. what did not apply: one comment each (the marker keeps it to one per patch)
    for item in [i for i in plan if i.get("result") in ("failed", "refused", "already")]:
        report(item)
        doctor = doctor or (item["result"] == "failed" and item.get("source") == "process-doctor")
        print(f"#{item['issue']}: {item['result']}")
    # 5. the process-doctor answers a refused or partial patch with a corrected issue; start it rather
    # than wait up to 4 hours for agent-health, at most once in 2 hours
    if doctor and not busy("process-doctor.lock.yml") and not started_within("process-doctor.lock.yml", 120):
        sh("gh", "workflow", "run", "process-doctor.lock.yml", "-R", repo(), check=False)
        print("started the process-doctor for the corrected patches")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--out", required=True)
    p = sub.add_parser("land")
    p.add_argument("--dir", required=True)
    p = sub.add_parser("guard")
    p.add_argument("base")
    p.add_argument("head", nargs="?")
    p = sub.add_parser("apply", help="apply the ```diff blocks of an issue body (a file) to the working tree")
    p.add_argument("body")
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        prepare(a.out)
    elif a.cmd == "land":
        land(a.dir)
    elif a.cmd == "guard":
        cls, problems = guard(a.base, a.head)
        print(cls)
        for x in problems:
            print("  " + x)
        return 0 if cls != "refuse" else 1
    elif a.cmd == "apply":
        res = apply_issue(Path(a.body).read_text())
        print(json.dumps(res, indent=1))
        return 1 if res["errors"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
