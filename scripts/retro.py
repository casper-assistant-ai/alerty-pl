#!/usr/bin/env python3
"""Process retro for the alerty-pl agent team: is the team building, or only keeping books?

    retro.py metrics [--days 7] [--repo OWNER/NAME] [--out FILE.json] [--md FILE.md]
    retro.py dispatch [--schedule process/schedule.json] [--dry-run]
    retro.py queue [--repo OWNER/NAME] [--out FILE.json] [--md FILE.md]
    retro.py gave-up [--days N] [--log process/retro-log.md] [--repo OWNER/NAME] [--out FILE.json] [--md FILE.md]

`metrics` reads the last N days from the GitHub REST API (GH_TOKEN or GITHUB_TOKEN) and the
workflow sources in .github/workflows, and counts for every agent: runs, failures, PRs opened,
merged and rejected, report issues, and runs that produced nothing. The headline number is
`dev_share`: merged agent PRs that change the product (feat, fix, perf, refactor, test, revert,
style, build) divided by all agent output (those PRs + docs/chore PRs + report issues).
Data commits of the Update data workflow are counted apart and never count as either.

`dispatch` reads process/schedule.json (kept by the process-retro agent through the Agent PR
gate) and starts the extra agent runs planned for today. It only starts agentic workflows that
exist in this repository, at most `max_extra_runs_per_week` (capped at 3) per agent.

`queue` lists the work waiting for the issue-worker agent: every open issue with its kind and the
open PRs that already name it, the agent PRs the gate refused, and whether today's improvement PR
(tests, reliability, simplicity) is still due because the queue is empty. gh-aw's detection
tracker (`[aw] Detection Runs`, a comment per run whose threat detection failed) is left out: it
is a log that gh-aw keeps, not work.

`gave-up` lists the issues the issue-worker gave up on: closed with the label `agent-gave-up` in the last
N days, minus those the process-retro already handled (its log row names them after `Gave up:`).
The process-retro turns each into smaller issues or a lesson; the daily status lists them as the only
items that need a human look.
Python 3 stdlib only.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
DEV = {"feat", "fix", "perf", "refactor", "test", "revert", "style", "build"}
BOOK = {"docs", "chore", "ci"}
CC = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9-]+)\))?(?P<bang>!)?: ")
PREFIX = re.compile(r"^\[(?P<agent>[a-z0-9-]+)\] ")
# the type the Agent PR gate gives a PR whose title is not a Conventional Commit
GATE_TYPE = {"site-fixer": "fix", "site-designer": "feat", "parser-doctor": "fix",
             "region-keeper": "fix", "security-auditor": "fix", "test-improver": "test",
             "docs-keeper": "docs", "agent-coach": "chore", "process-retro": "chore", "process-doctor": "chore",
             "issue-worker": "fix", "security-fixer": "fix"}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HARD_CAP = 3
# agents that change the process itself; their PRs count as process, not as output
PROCESS_AGENTS = {"agent-coach", "process-retro", "process-doctor"}


def agent_of(title):
    m = PREFIX.match(title or "")
    return m.group("agent") if m else None


def kind(subject, agent=None):
    """dev, book, process, data or other for a commit subject or an agent PR title."""
    s = PREFIX.sub("", subject or "")
    if s.startswith("data:") or s.startswith("update:"):
        return "data"
    m = CC.match(s)
    t, scope = (m.group("type"), m.group("scope")) if m else (GATE_TYPE.get(agent), None)
    if scope == "data":
        return "data"
    if scope in ("process", "agents"):
        return "process"
    if t in DEV:
        return "dev"
    if t in BOOK:
        return "book"
    return "other"


def roles():
    """Agent name -> builder (opens PRs), reporter (opens issues), process or helper, from the sources."""
    out = {}
    for f in sorted(WF.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        front = text.split("---", 2)[1]
        if f.stem in PROCESS_AGENTS:
            out[f.stem] = "process"
        elif "create-pull-request:" in front:
            out[f.stem] = "builder"
        elif "create-issue:" in front:
            out[f.stem] = "reporter"
        else:
            out[f.stem] = "helper"
    return out


def summarize(commits, prs, issues, runs, role, since):
    """Pure: the week's numbers from lists of plain dicts (see fetch for the fields)."""
    agents = {a: {"role": r, "runs": 0, "failed": 0, "prs": 0, "merged": 0, "rejected": 0,
                  "open_prs": 0, "dev_merged": 0, "reports": 0, "idle": 0} for a, r in role.items()}
    for r in runs:
        a = Path(r.get("path") or "").name.removesuffix(".lock.yml")
        if a in agents and r.get("conclusion") not in ("skipped", "cancelled"):
            agents[a]["runs"] += 1
            if r.get("conclusion") in ("failure", "timed_out", "startup_failure"):
                agents[a]["failed"] += 1
    linked = set()
    dev_days = set()
    out = {"dev": 0, "book": 0, "process": 0, "other": 0}
    for p in prs:
        for n in re.findall(r"#(\d+)", (p.get("title") or "") + " " + (p.get("body") or "")):
            linked.add(int(n))
        a = agent_of(p.get("title"))
        if a not in agents or p.get("created_at", "") < since:
            continue
        g = agents[a]
        g["prs"] += 1
        if p.get("merged_at"):
            g["merged"] += 1
            k = kind(p["title"], a)
            out[k if k in out else "other"] += 1
            if k == "dev":
                g["dev_merged"] += 1
                dev_days.add(p["merged_at"][:10])
        elif p.get("state") == "closed":
            g["rejected"] += 1
        else:
            g["open_prs"] += 1
    tooling = 0
    reports_list = []
    unlinked = []
    for i in issues:
        labels = set(i.get("labels") or [])
        a = agent_of(i.get("title"))
        if "agentic-workflows" in labels:
            tooling += 1  # gh-aw's own notices (no-op tracker, rate limits)
            continue
        if i.get("created_at", "") >= since and a in agents:
            agents[a]["reports"] += 1
            reports_list.append(i["number"])
        if i.get("state") == "open" and i["number"] not in linked and "report" not in labels:
            unlinked.append(i["number"])
    for a, g in agents.items():
        g["idle"] = max(0, g["runs"] - g["failed"] - g["prs"] - g["reports"])
    out["book"] += len(reports_list)
    total = out["dev"] + out["book"]
    kinds = {"dev": 0, "book": 0, "process": 0, "data": 0, "other": 0}
    for c in commits:
        kinds[kind(c.get("subject"))] += 1
    builders = [a for a, g in agents.items() if g["role"] == "builder"]
    return {
        "since": since,
        "dev_share": round(out["dev"] / total, 2) if total else None,
        "agent_output": out,
        "dev_days": sorted(dev_days),
        "main_commits": kinds,
        "issues_without_pr": sorted(unlinked),
        "tooling_notices": tooling,
        "builders_without_merge": sorted(a for a in builders if agents[a]["merged"] == 0),
        "reporters_only": sorted(a for a, g in agents.items() if g["reports"] and not g["prs"]),
        "agents": agents,
    }


def markdown(m):
    share = "n/a (no agent output)" if m["dev_share"] is None else f"{round(m['dev_share'] * 100)}%"
    o, c = m["agent_output"], m["main_commits"]
    lines = [
        f"Process retro since {m['since'][:10]}: development share **{share}** "
        f"({o['dev']} product PRs merged, {o['book']} docs/chore PRs and reports).",
        "",
        f"- Commits on main: {c['dev']} product, {c['book']} docs/chore, {c['process']} process, "
        f"{c['data']} data, {c['other']} other.",
        f"- Days with product work merged: {len(m.get('dev_days', []))} "
        f"({', '.join(m.get('dev_days', [])) or 'none'}); a day without it is a failed day.",
        f"- Builders with nothing merged: {', '.join(m['builders_without_merge']) or 'none'}.",
        f"- Agents that only report: {', '.join(m['reporters_only']) or 'none'}.",
        f"- Open issues with no PR: {', '.join('#' + str(n) for n in m['issues_without_pr']) or 'none'}.",
        f"- gh-aw tooling notices: {m['tooling_notices']}.",
        "",
        "| agent | role | runs | failed | PRs | merged | product | rejected | reports | idle |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for a, g in sorted(m["agents"].items()):
        lines.append(f"| {a} | {g['role']} | {g['runs']} | {g['failed']} | {g['prs']} | {g['merged']} | "
                     f"{g['dev_merged']} | {g['rejected']} | {g['reports']} | {g['idle']} |")
    return "\n".join(lines) + "\n"


# A rate limit answers 403 or 429 with the wait to come: Retry-After (seconds), or X-RateLimit-Reset
# (the epoch second it ends). Such an answer gets one more try after that wait. A step that runs on
# schedule does not wait out a longer one: the run fails with the wait in its last line.
RATE_LIMIT = {403, 429}
MAX_WAIT = 60
DEFAULT_WAIT = 2  # a 403 or 429 that names no wait (no rate limit: a missing permission) gets its second try after this


class ApiError(Exception):
    """GitHub refused a request: its status, its message and when to ask again, in one line."""


def rate_wait(headers, now=None):
    """(seconds to wait before one more try at a 403 or 429, the seconds GitHub asks for).
    The seconds asked for are in Retry-After, else X-RateLimit-Reset minus now; None when the answer
    names neither. The wait is that number, not under 0; over MAX_WAIT it is None: do not try again."""
    asked = None
    for name in ("Retry-After", "X-RateLimit-Reset"):
        try:
            asked = float(headers.get(name))
        except (AttributeError, TypeError, ValueError):
            continue
        if name == "X-RateLimit-Reset":
            asked -= time.time() if now is None else now
        break
    if asked is None:
        return DEFAULT_WAIT, None
    return (None if asked > MAX_WAIT else max(asked, 0)), asked


def api(path, token, method="GET", body=None):
    """One request: (the JSON, or None for an empty body; the URL of the next page, or None).
    A 403 or 429 gets one more try after the wait it names (rate_wait); what is still refused, and
    any other error status, ends in an ApiError of one line, which main() prints before it exits."""
    url = path if path.startswith("http") else "https://api.github.com" + path
    slept = 0
    for tries in (1, 2):
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Accept": "application/vnd.github+json",
                                              "Authorization": f"Bearer {token}",
                                              "X-GitHub-Api-Version": "2022-11-28",
                                              "User-Agent": "alerty-pl-retro"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                nxt = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link") or "")
                return (json.loads(data) if data else None), (nxt.group(1) if nxt else None)
        except urllib.error.HTTPError as e:
            try:  # what GitHub says: the message of the JSON body, else the reason phrase
                said = json.loads(e.read() or b"{}").get("message") or e.reason
            except (AttributeError, ValueError):
                said = e.reason
            e.close()
            wait, asked = rate_wait(e.headers) if e.code in RATE_LIMIT else (None, None)
            if tries == 1 and wait is not None:
                print(f"::warning::GitHub API {e.code} on {method} {url}: trying once more in {wait:g} s", file=sys.stderr)
                slept = wait
                time.sleep(wait)
                continue
            err = f"GitHub API {e.code} ({str(said)[:120]}) on {method} {url}"
            if tries == 2:
                err += f"; the second try, after {slept:g} s, was refused as well"
            if asked is not None:
                err += f"; GitHub asks to wait {asked:g} s more"
            raise ApiError(err) from None


def pages(path, token, key=None, stop=None, limit=10):
    out, url = [], path
    for _ in range(limit):
        data, url = api(url, token)
        items = data[key] if key else data
        out.extend(items)
        if not url or (stop and items and stop(items[-1])):
            break
    return out


def fetch(repo, token, since, with_runs=True):
    r = f"/repos/{repo}"
    q = urllib.parse.quote
    commits = [{"subject": c["commit"]["message"].split("\n")[0]}
               for c in pages(f"{r}/commits?sha=main&per_page=100&since={q(since)}", token)]
    prs = [{"number": p["number"], "title": p["title"], "body": p.get("body") or "",
            "created_at": p["created_at"], "merged_at": p.get("merged_at"), "state": p["state"],
            "labels": [x["name"] for x in p.get("labels", [])]}
           for p in pages(f"{r}/pulls?state=all&sort=created&direction=desc&per_page=100", token,
                          stop=lambda p: p["created_at"] < since)]
    issues = [{"number": i["number"], "title": i["title"], "state": i["state"],
               "created_at": i["created_at"], "labels": [x["name"] for x in i.get("labels", [])]}
              for i in pages(f"{r}/issues?state=all&per_page=100&since={q(since)}", token)
              if "pull_request" not in i]
    # open issues older than the window still count when nothing links them
    seen = {i["number"] for i in issues}
    issues += [{"number": i["number"], "title": i["title"], "state": i["state"],
                "created_at": i["created_at"], "labels": [x["name"] for x in i.get("labels", [])]}
               for i in pages(f"{r}/issues?state=open&per_page=100", token)
               if "pull_request" not in i and i["number"] not in seen]
    if not with_runs:
        return commits, prs, issues, []
    runs = [{"path": w.get("path"), "conclusion": w.get("conclusion"), "event": w.get("event")}
            for w in pages(f"{r}/actions/runs?per_page=100&created=%3E%3D{since[:10]}", token, key="workflow_runs")]
    return commits, prs, issues, runs


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not t:
        sys.exit("retro: set GH_TOKEN")
    return t


def repo_name(arg):
    return arg or os.environ.get("GITHUB_REPOSITORY") or "casper-assistant-ai/alerty-pl"


# gh-aw keeps these issues itself (no-op tracker); they are closed by fixing the cause
MANAGED = re.compile(r"^\[aw\] No-Op Runs")
# gh-aw's log of detection problems: one comment per run whose threat detection failed. Never
# work for the issue-worker: closing it only makes gh-aw file a new one and start another run.
# The whole title: a failure notice ("[aw] <workflow>: <reason>") must still be listed.
TRACKER = re.compile(r"^\[aw\] Detection Runs$")
WORKER = "issue-worker"
# The process-doctor owns these: agent-health's self-closing failure issues, and its own
# workflow-change issues (frontmatter patches that GITHUB_TOKEN cannot push, applied by a maintainer).
DOCTOR_LABELS = {"agent-health", "workflow-change"}
# the issue-worker starts an improvement PR body with "Improvement: ..." (gh-aw strips HTML comments)
IMPROVEMENT = re.compile(r"^\s*Improvement\b", re.I)


def issue_kind(title, labels):
    """What an open issue asks for: managed, report, dev-task, ci, site-error, aw-notice or request."""
    labels = set(labels or [])
    a = agent_of(title)
    if MANAGED.match(title or "") or labels & DOCTOR_LABELS:
        return "managed"
    # the issue-worker's dev-tasks for a report's points, also when the model left the label off
    if "dev-task" in labels or (title or "").startswith("[issue-worker] dev-task:"):
        return "dev-task"
    if "site-error" in labels:
        return "site-error"
    if a == "ci-doctor" or "ci" in labels:
        return "ci"
    if "agentic-workflows" in labels:
        return "aw-notice"
    if "report" in labels or a in ("daily-status", "security-audit"):
        return "report"
    return "request"


ORDER = ["ci", "site-error", "aw-notice", "request", "dev-task", "report", "managed"]


GIVE_UP = 2  # closed, unmerged PRs for one issue before the worker closes the issue instead
GAVE_UP_LABEL = "agent-gave-up"  # the worker puts it on the issue it closes after GIVE_UP rejected PRs


def queue(issues, prs, today):
    """Pure: the issue-worker's queue from open issues and all recent PRs (plain dicts).

    An open PR that names an issue means it is in work. A closed, unmerged PR that names it was
    rejected (by the reviewer, the tests or the path check); after GIVE_UP of them the worker
    closes the issue with the reasons instead of trying again."""
    refs, rejected = {}, {}
    for p in prs:
        nums = set(re.findall(r"#(\d+)", (p.get("title") or "") + " " + (p.get("body") or "")))
        if p.get("state") == "open":
            target = refs
        elif p.get("state") == "closed" and not p.get("merged_at"):
            target = rejected
        else:
            continue
        for n in nums:
            target.setdefault(int(n), []).append(p["number"])
    items = []
    for i in issues:
        if i.get("state") != "open" or TRACKER.match(i.get("title") or ""):
            continue
        k = issue_kind(i.get("title"), i.get("labels"))
        items.append({"number": i["number"], "title": i["title"], "kind": k,
                      "labels": i.get("labels") or [], "created_at": i.get("created_at"),
                      "open_prs": sorted(refs.get(i["number"], [])),
                      "rejected_prs": sorted(rejected.get(i["number"], []))})
    items.sort(key=lambda x: (ORDER.index(x["kind"]), x["created_at"] or ""))
    actionable = [x for x in items if not x["open_prs"] and x["kind"] != "managed"]
    give_up = [x["number"] for x in actionable if len(x["rejected_prs"]) >= GIVE_UP]
    improved_today = any(agent_of(p.get("title")) == WORKER and IMPROVEMENT.match(p.get("body") or "")
                         and (p.get("created_at") or "").startswith(today) for p in prs)
    return {"today": today, "issues": items, "actionable": [x["number"] for x in actionable],
            "give_up": give_up,
            "improvement_due": not actionable and not improved_today}


WORKER_BUSY = {"queued", "in_progress", "waiting", "requested", "pending"}


def should_kick(q, prs, runs):
    """Pure: why the issue-worker should start now, or None.

    Issues made by agents (GITHUB_TOKEN) start no workflow, so the worker's dev-tasks and the agents'
    reports used to wait for its two-hourly schedule (#146: six hours for five points). Start it when
    no worker run is waiting or running and work is left that its last run did not see or was moving
    through: an actionable issue opened after that run started, or a PR that run opened while the
    queue still holds issues. An issue the worker leaves open on purpose starts nothing by itself."""
    if not q["actionable"]:
        return None
    if any(r.get("status") in WORKER_BUSY for r in runs):
        return None
    if not runs:
        return f"no issue-worker run yet; {len(q['actionable'])} issue(s) wait"
    last = max(r["created_at"] for r in runs)
    new = [x["number"] for x in q["issues"] if x["number"] in q["actionable"] and (x["created_at"] or "") > last]
    if new:
        return "new since the last run: " + ", ".join(f"#{n}" for n in new)
    made = [p["number"] for p in prs if agent_of(p.get("title")) == WORKER and (p.get("created_at") or "") > last]
    if made:
        return (f"the last run opened PR #{made[0]} and {len(q['actionable'])} issue(s) still wait: "
                + ", ".join(f"#{n}" for n in q["actionable"][:5]))
    return None


def queue_md(q):
    lines = [f"Issue-worker queue on {q['today']}: {len(q['actionable'])} issue(s) to handle, "
             f"{len(q['give_up'])} to close after {GIVE_UP} rejected PRs; improvement due: "
             f"{'yes' if q['improvement_due'] else 'no'}.", "",
             "| issue | kind | open PRs | rejected PRs | title |", "|---|---|---|---|---|"]
    for x in q["issues"]:
        prs = ", ".join(f"#{n}" for n in x["open_prs"]) or "none"
        rej = ", ".join(f"#{n}" for n in x["rejected_prs"]) or "none"
        if x["number"] in q["give_up"]:
            rej += f" (give up: close the issue with the label {GAVE_UP_LABEL})"
        lines.append(f"| #{x['number']} | {x['kind']} | {prs} | {rej} | {x['title']} |")
    return "\n".join(lines) + "\n"


# the process-retro writes «Gave up: #12 split into #20 #21; #13 lesson» in its log row once it handled them
HANDLED = re.compile(r"Gave up:(.*)")


def handled_numbers(log_text):
    """Issue numbers the retro log names after «Gave up:» (the issues and the ones made from them)."""
    out = set()
    for line in (log_text or "").splitlines():
        for m in HANDLED.finditer(line):
            out |= {int(n) for n in re.findall(r"#(\d+)", m.group(1))}
    return out


def gave_up(issues, since, handled=()):
    """Pure: the issues closed with GAVE_UP_LABEL at or after `since` (ISO, UTC), newest first, that the
    retro has not handled yet. Pull requests, open issues and other labels never count."""
    out = []
    for i in issues:
        if "pull_request" in i or i.get("state") != "closed" or GAVE_UP_LABEL not in (i.get("labels") or []):
            continue
        if (i.get("closed_at") or "") < since or i["number"] in set(handled):
            continue
        out.append({"number": i["number"], "title": i["title"], "closed_at": i["closed_at"],
                    "url": i.get("html_url") or ""})
    return sorted(out, key=lambda x: x["closed_at"], reverse=True)


def gave_up_md(items, since):
    if not items:
        return f"No issue closed with the label {GAVE_UP_LABEL} since {since}.\n"
    lines = [f"{len(items)} issue(s) the issue-worker gave up on since {since} (label {GAVE_UP_LABEL}):", ""]
    lines += [f"- #{x['number']} {x['title']} (closed {x['closed_at']}) {x['url']}".rstrip() for x in items]
    return "\n".join(lines) + "\n"


def load_schedule(path, known):
    """Validated plan: agent -> list of weekdays. Unknown agents and extra days are dropped."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cap = min(int(data.get("max_extra_runs_per_week", HARD_CAP)), HARD_CAP)
    plan = {}
    for agent, days in (data.get("extra_runs") or {}).items():
        if agent not in known or agent == "process-retro":
            continue
        plan[agent] = [d for d in dict.fromkeys(days) if d in DAYS][:cap]
    return plan


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("metrics")
    m.add_argument("--days", type=int, default=7)
    m.add_argument("--repo")
    m.add_argument("--out")
    m.add_argument("--md")
    d = sub.add_parser("dispatch")
    d.add_argument("--schedule", default=str(ROOT / "process" / "schedule.json"))
    d.add_argument("--repo")
    d.add_argument("--day", help="mon..sun (default: today, UTC)")
    d.add_argument("--dry-run", action="store_true")
    q = sub.add_parser("queue")
    q.add_argument("--repo")
    q.add_argument("--out")
    q.add_argument("--md")
    k = sub.add_parser("kick", help="start the issue-worker when new work waits (should_kick)")
    k.add_argument("--repo")
    k.add_argument("--dry-run", action="store_true")
    g = sub.add_parser("gave-up")
    g.add_argument("--days", type=int, default=1)
    g.add_argument("--log", help="the retro log; issues it names after «Gave up:» are skipped")
    g.add_argument("--repo")
    g.add_argument("--out")
    g.add_argument("--md")
    a = ap.parse_args(argv)
    try:
        run(a)
    except ApiError as e:  # one line in the step's log, not a traceback
        sys.exit(f"retro: {e}")


def run(a):
    if a.cmd == "gave-up":
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = pages(f"/repos/{repo_name(a.repo)}/issues?state=closed&labels={GAVE_UP_LABEL}&per_page=100"
                    f"&since={urllib.parse.quote(since)}", token())
        issues = [{"number": i["number"], "title": i["title"], "state": i["state"], "closed_at": i.get("closed_at"),
                   "html_url": i.get("html_url"), "labels": [x["name"] for x in i.get("labels", [])],
                   **({"pull_request": True} if "pull_request" in i else {})} for i in raw]
        log = Path(a.log).read_text(encoding="utf-8") if a.log and Path(a.log).exists() else ""
        items = gave_up(issues, since, handled_numbers(log))
        if a.out:
            Path(a.out).write_text(json.dumps(items, indent=1), encoding="utf-8")
        md = gave_up_md(items, since)
        if a.md:
            Path(a.md).write_text(md, encoding="utf-8")
        print(md)
    elif a.cmd == "queue":
        now = dt.datetime.now(dt.timezone.utc)
        since = (now - dt.timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _, prs, issues, _ = fetch(repo_name(a.repo), token(), since)
        res = queue(issues, prs, now.strftime("%Y-%m-%d"))
        if a.out:
            Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        md = queue_md(res)
        if a.md:
            Path(a.md).write_text(md, encoding="utf-8")
        print(md)
    elif a.cmd == "kick":
        now = dt.datetime.now(dt.timezone.utc)
        since = (now - dt.timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
        repo, tok = repo_name(a.repo), token()
        _, prs, issues, _ = fetch(repo, tok, since, with_runs=False)
        q = queue(issues, prs, now.strftime("%Y-%m-%d"))
        data, _ = api(f"/repos/{repo}/actions/workflows/{WORKER}.lock.yml/runs?per_page=10", tok)
        runs = [{"status": r["status"], "created_at": r["created_at"]} for r in data["workflow_runs"]]
        why = should_kick(q, prs, runs)
        if not why:
            print(f"issue-worker: not started ({len(q['actionable'])} actionable; busy, or nothing new since its last run)")
            return
        print(f"issue-worker: start ({why})" + (" [dry run]" if a.dry_run else ""))
        if not a.dry_run:
            api(f"/repos/{repo}/actions/workflows/{WORKER}.lock.yml/dispatches", tok, method="POST", body={"ref": "main"})
    elif a.cmd == "metrics":
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        res = summarize(*fetch(repo_name(a.repo), token(), since), roles(), since)
        if a.out:
            Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        md = markdown(res)
        if a.md:
            Path(a.md).write_text(md, encoding="utf-8")
        print(md)
    else:
        known = {f.name.removesuffix(".lock.yml") for f in WF.glob("*.lock.yml")}
        day = a.day or DAYS[dt.datetime.now(dt.timezone.utc).weekday()]
        todo = [ag for ag, days in load_schedule(a.schedule, known).items() if day in days]
        for ag in todo:
            print(f"dispatch {ag} ({day})" + (" [dry run]" if a.dry_run else ""))
            if not a.dry_run:
                api(f"/repos/{repo_name(a.repo)}/actions/workflows/{ag}.lock.yml/dispatches", token(),
                    method="POST", body={"ref": "main"})
        if not todo:
            print(f"no extra agent runs planned for {day}")


if __name__ == "__main__":
    main()
