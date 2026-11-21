#!/usr/bin/env python3
"""Process retro for the alerty-pl agent team: is the team building, or only keeping books?

    retro.py metrics [--days 7] [--repo OWNER/NAME] [--out FILE.json] [--md FILE.md]
    retro.py dispatch [--schedule process/schedule.json] [--dry-run]
    retro.py queue [--repo OWNER/NAME] [--out FILE.json] [--md FILE.md]

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
(tests, reliability, simplicity) is still due because the queue is empty.
Python 3 stdlib only.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
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
             "docs-keeper": "docs", "agent-coach": "chore", "process-retro": "chore",
             "issue-worker": "fix"}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HARD_CAP = 3
# agents that change the process itself; their PRs count as process, not as output
PROCESS_AGENTS = {"agent-coach", "process-retro"}


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
        labels = set(p.get("labels") or [])
        if p.get("merged_at"):
            g["merged"] += 1
            k = kind(p["title"], a)
            out[k if k in out else "other"] += 1
            if k == "dev":
                g["dev_merged"] += 1
                dev_days.add(p["merged_at"][:10])
        elif p.get("state") == "closed" or "needs-attention" in labels:
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


def api(path, token, method="GET", body=None):
    url = path if path.startswith("http") else "https://api.github.com" + path
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Accept": "application/vnd.github+json",
                                          "Authorization": f"Bearer {token}",
                                          "X-GitHub-Api-Version": "2022-11-28",
                                          "User-Agent": "alerty-pl-retro"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link") or "")
        return (json.loads(data) if data else None), (nxt.group(1) if nxt else None)


def pages(path, token, key=None, stop=None, limit=10):
    out, url = [], path
    for _ in range(limit):
        data, url = api(url, token)
        items = data[key] if key else data
        out.extend(items)
        if not url or (stop and items and stop(items[-1])):
            break
    return out


def fetch(repo, token, since):
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
WORKER = "issue-worker"
IMPROVEMENT = "<!-- improvement -->"  # the issue-worker puts this line in an improvement PR body


def issue_kind(title, labels):
    """What an open issue asks for: managed, report, dev-task, ci, site-error, aw-notice or request."""
    labels = set(labels or [])
    a = agent_of(title)
    if MANAGED.match(title or ""):
        return "managed"
    if "dev-task" in labels:
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


def queue(issues, prs, today):
    """Pure: the issue-worker's queue from open issues and all recent PRs (plain dicts)."""
    refs = {}
    for p in prs:
        if p.get("state") != "open":
            continue
        for n in set(re.findall(r"#(\d+)", (p.get("title") or "") + " " + (p.get("body") or ""))):
            refs.setdefault(int(n), []).append(p["number"])
    items = []
    for i in issues:
        if i.get("state") != "open":
            continue
        k = issue_kind(i.get("title"), i.get("labels"))
        items.append({"number": i["number"], "title": i["title"], "kind": k,
                      "labels": i.get("labels") or [], "created_at": i.get("created_at"),
                      "open_prs": sorted(refs.get(i["number"], []))})
    items.sort(key=lambda x: (ORDER.index(x["kind"]), x["created_at"] or ""))
    refused = [{"number": p["number"], "title": p["title"]} for p in prs
               if p.get("state") == "open" and "needs-attention" in (p.get("labels") or [])]
    actionable = [x for x in items if not x["open_prs"] and x["kind"] != "managed"]
    improved_today = any(agent_of(p.get("title")) == WORKER and IMPROVEMENT in (p.get("body") or "")
                         and (p.get("created_at") or "").startswith(today) for p in prs)
    return {"today": today, "issues": items, "actionable": [x["number"] for x in actionable],
            "refused_prs": refused,
            "improvement_due": not actionable and not refused and not improved_today}


def queue_md(q):
    lines = [f"Issue-worker queue on {q['today']}: {len(q['actionable'])} issue(s) to handle, "
             f"{len(q['refused_prs'])} refused agent PR(s); improvement due: "
             f"{'yes' if q['improvement_due'] else 'no'}.", "",
             "| issue | kind | open PRs | title |", "|---|---|---|---|"]
    for x in q["issues"]:
        prs = ", ".join(f"#{n}" for n in x["open_prs"]) or "none"
        lines.append(f"| #{x['number']} | {x['kind']} | {prs} | {x['title']} |")
    for p in q["refused_prs"]:
        lines.append(f"| PR #{p['number']} | refused by gate | | {p['title']} |")
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
    a = ap.parse_args(argv)
    if a.cmd == "queue":
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
