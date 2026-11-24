#!/usr/bin/env python3
"""Failures of the alerty-pl agent workflows, gathered for the process-doctor agent.

    agent_failures.py [--days 7] [--repo OWNER/NAME] [--patterns process/failure-patterns.md]
                      [--out FILE.json] [--md FILE.md]

Reads, through the `gh` CLI (GH_TOKEN): every gh-aw agent workflow (a .lock.yml with its .md
source), its completed runs of the last N days, the failed steps of each failed run (gh-aw's
step-summary parser crash after the agent's work is left out, as in scripts/agent_health.cjs),
and the error lines of the failed job's log. Each failed run gets one signature (provider
overload, timeout, turn limit, network, permission, safe outputs, auth, engine crash, unknown).
A signature that failed at least RECUR_RUNS runs on RECUR_DAYS days is recurring: the doctor
turns it into a rule. It also lists the open agent-tooling issues (label `agentic-workflows`)
and whether the doctor already commented on them, and each workflow's timeout against its
longest agent job.

The pure functions (classify, signal_lines, summarize, markdown, ...) are tested in
tests/test_agent_failures.py; only fetch() talks to GitHub. Python 3 stdlib only.
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WORKFLOWS = Path(".github/workflows")
# gh-aw v1.2.2's step-summary parser throws on long sessions after the agent finished (agent_health.cjs)
IGNORED_STEPS = {"Parse agent logs for step summary"}
NEUTRAL = {"cancelled", "skipped", "action_required", "neutral", "stale"}
BAD = {"failure", "timed_out", "cancelled"}
RECUR_RUNS, RECUR_DAYS = 3, 2
LOG_RUNS = 6        # failed runs per workflow whose log is read; older ones are `unread`
LOG_LINES = 20      # error lines kept per run
DOCTOR = re.compile(r"process[ -]doctor", re.I)

# Order matters: the first match names the run. They are matched against signal_lines() only:
# a whole gh-aw job log names every error type in its own config ("rate_limit_error" and so on).
SIGNATURES = [
    ("timeout", r"timed out after|has exceeded the maximum execution time|\(timed_out\)|\(cancelled\)"),
    ("provider-overload", r"API Error: (529|429|5\d\d)|overloaded|\[1305\]|rate limit reached|too many requests"),
    ("turn-limit", r"error_max_turns|max(imum)?[ _-]turns"),
    ("network", r"firewall|blocked (by|domain)|ENOTFOUND|ECONNREFUSED|ECONNRESET|ETIMEDOUT|EAI_AGAIN|socket hang up"),
    ("auth", r"API Error: 401|invalid[ _]api[ _]key|authentication_error|bad credentials"),
    ("permission", r"resource not accessible by integration|refusing to allow|permission denied|API Error: 403"),
    ("safe-outputs", r"safe[ _-]?outputs?\b"),
    ("engine-crash", r"exited with code|process completed with exit code|engine driver crashed|segmentation fault"),
]
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
API_ERROR = re.compile(r"API Error: [^\"\\]{0,160}")
REQUEST_ID = re.compile(r"\[\d{14}[0-9a-f]{8,}\]")
PARSER_CRASH = re.compile(r"Maximum call stack size exceeded")


def classify(steps, signals=()):
    """One signature for a failed run from its failed steps and its signal lines."""
    text = "\n".join(list(steps) + list(signals))
    for name, rx in SIGNATURES:
        if re.search(rx, text, re.I):
            return name
    return "unknown"


def signal_lines(log_text, limit=LOG_LINES):
    """What a failed job log says about the failure: the runner's ##[error] lines (the parser crash
    left out), the model API errors (request ids folded, so repeats count once) and Claude's final
    result record. Everything else in a gh-aw log is configuration and tool chatter."""
    out = []
    def add(line):
        line = line.strip()[:300]
        if line and line not in out:
            out.append(line)
    for raw in (log_text or "").splitlines():
        line = ANSI.sub("", STAMP.sub("", raw))
        if "##[error]" in line:
            if not PARSER_CRASH.search(line):
                add(line.split("##[error]", 1)[1])
            continue
        for m in API_ERROR.findall(line):
            add(REQUEST_ID.sub("[…]", m))
        if line.lstrip().startswith("{") and '"type":"result"' in line:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("is_error") or r.get("subtype") not in (None, "success"):
                add(f"result: subtype={r.get('subtype')} is_error={r.get('is_error')} turns={r.get('num_turns')} "
                    f"terminal_reason={r.get('terminal_reason')} {str(r.get('result') or '')[:160]}")
    return out[-limit:]


def failed_steps(jobs):
    """Failed steps that count, as "job / step" strings; a failed job with no failed step counts as itself."""
    out = []
    for job in jobs or []:
        if job.get("conclusion") not in BAD:
            continue
        bad = [s for s in job.get("steps") or [] if s.get("conclusion") in BAD]
        if not bad:
            out.append(f"{job['name']} ({job['conclusion']})")
        for s in bad:
            if s["name"] in IGNORED_STEPS:
                continue
            tail = "" if s["conclusion"] == "failure" else f" ({s['conclusion']})"
            out.append(f"{job['name']} / {s['name']}{tail}")
    return out


def minutes(a, b):
    if not a or not b:
        return None
    f = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return round((f(b) - f(a)).total_seconds() / 60)


def timeout_of(md_text):
    """timeout-minutes of a gh-aw workflow source (gh-aw's default is 20)."""
    m = re.search(r"^timeout-minutes:\s*(\d+)", md_text or "", re.M)
    return int(m.group(1)) if m else 20


def known_patterns(text):
    """Signatures named in the first column of the table in process/failure-patterns.md."""
    out = set()
    for line in (text or "").splitlines():
        cells = [c.strip(" `") for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells and re.fullmatch(r"[a-z][a-z-]+", cells[0] or ""):
            out.add(cells[0])
    return out


def summarize(workflows, issues, patterns, now, days):
    """Pure: the report from workflows [{name, file, timeout, runs:[{..., jobs, steps, log}]}] and issues."""
    agents, failures, sigs = [], [], {}
    for wf in workflows:
        ok = bad = 0
        mins = []
        for r in wf["runs"]:
            if r.get("status") != "completed" or r.get("conclusion") in NEUTRAL:
                continue
            agent = next((j for j in r.get("jobs") or [] if j.get("name") == "agent"), None)
            m = minutes(agent.get("started_at"), agent.get("completed_at")) if agent else None
            if m is not None:
                mins.append(m)
            steps = failed_steps(r.get("jobs")) if r.get("conclusion") != "success" else []
            if not steps:
                ok += 1
                continue
            bad += 1
            signals = r.get("signals")
            sig = classify(steps, signals or [])
            if sig == "unknown" and signals is None:
                sig = "unread"
            day = (r.get("created_at") or "")[:10]
            failures.append({"workflow": wf["name"], "file": wf["file"], "run": r["id"], "url": r.get("html_url"),
                             "created_at": r.get("created_at"), "event": r.get("event"), "agent_minutes": m,
                             "steps": steps, "signature": sig, "errors": signals or []})
            s = sigs.setdefault(sig, {"signature": sig, "runs": 0, "days": set(), "workflows": set()})
            s["runs"] += 1
            s["days"].add(day)
            s["workflows"].add(wf["name"])
        longest = max(mins) if mins else None
        agents.append({"workflow": wf["name"], "file": wf["file"], "ok": ok, "failed": bad,
                       "fail_rate": round(bad / (ok + bad), 2) if ok + bad else 0.0,
                       "median_minutes": statistics.median(mins) if mins else None,
                       "longest_minutes": longest, "timeout_minutes": wf["timeout"],
                       "near_timeout": longest is not None and longest >= 0.85 * wf["timeout"]})
    signatures = []
    for s in sorted(sigs.values(), key=lambda x: -x["runs"]):
        signatures.append({"signature": s["signature"], "runs": s["runs"], "days": len(s["days"]),
                           "workflows": sorted(s["workflows"]), "known": s["signature"] in patterns,
                           "recurring": s["signature"] != "unread" and s["runs"] >= RECUR_RUNS and len(s["days"]) >= RECUR_DAYS})
    failures.sort(key=lambda f: f["created_at"] or "", reverse=True)
    open_issues = [{"number": i["number"], "title": i["title"], "labels": i.get("labels") or [],
                    "updated_at": i.get("updated_at"), "doctor_commented": bool(i.get("doctor_commented"))}
                   for i in issues]
    return {"generated_at": now, "days": days, "agents": agents, "signatures": signatures,
            "failures": failures, "open_issues": open_issues}


def markdown(rep):
    L = [f"# Agent failures, last {rep['days']} days (to {rep['generated_at'][:16].replace('T', ' ')} UTC)", "",
         "## Agents", "",
         "| Agent | OK | Failed | Fail rate | Median agent min | Longest | Timeout | Near timeout |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for a in sorted(rep["agents"], key=lambda a: (-a["failed"], a["workflow"])):
        L.append(f"| {a['workflow']} | {a['ok']} | {a['failed']} | {int(a['fail_rate'] * 100)}% | "
                 f"{a['median_minutes'] if a['median_minutes'] is not None else '-'} | "
                 f"{a['longest_minutes'] if a['longest_minutes'] is not None else '-'} | {a['timeout_minutes']} | "
                 f"{'**yes**' if a['near_timeout'] else 'no'} |")
    L += ["", "## Signatures", ""]
    if not rep["signatures"]:
        L.append("No failed runs.")
    else:
        L += ["| Signature | Failed runs | Days | Agents | In failure-patterns.md | Recurring |",
              "| --- | --- | --- | --- | --- | --- |"]
        for s in rep["signatures"]:
            L.append(f"| {s['signature']} | {s['runs']} | {s['days']} | {', '.join(s['workflows'])} | "
                     f"{'yes' if s['known'] else 'no'} | {'**yes: needs a rule**' if s['recurring'] else 'no'} |")
    L += ["", "## Open agent-tooling issues", ""]
    L += [f"- #{i['number']} {i['title']} (labels: {', '.join(i['labels'])}; "
          f"process-doctor commented: {'yes' if i['doctor_commented'] else 'no'})" for i in rep["open_issues"]] or ["None."]
    L += ["", "## Failed runs, newest first", ""]
    for f in rep["failures"][:40]:
        L.append(f"### {f['workflow']}: run {f['run']}, {(f['created_at'] or '')[:16].replace('T', ' ')} UTC, "
                 f"{f['event']}, agent {f['agent_minutes'] if f['agent_minutes'] is not None else '?'} min, `{f['signature']}`")
        L.append(f"{f['url']}  ")
        L.append("Failed steps: " + "; ".join(f["steps"]))
        if f["errors"]:
            L += ["", "```text", *f["errors"], "```"]
        L.append("")
    return "\n".join(L) + "\n"


# ---- GitHub through the gh CLI ----

# Job logs hold terminal escape sequences, and newer gh (the runners') refuses to print them without
# this flag; older gh (2.45) has no such flag and prints them anyway.
ESCAPES = "--allow-escape-sequences"


def gh(path, raw=False, run=subprocess.run):
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    out = run(cmd + ([ESCAPES] if raw else []), capture_output=True, text=True, timeout=120)
    if raw and out.returncode != 0 and "unknown flag" in out.stderr:
        out = run(cmd, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path}: {out.stderr.strip()[:200]}")
    return out.stdout if raw else json.loads(out.stdout)


def fetch(repo, days, now):
    since = (dt.datetime.fromisoformat(now.replace("Z", "+00:00")) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    workflows = []
    for w in gh(f"repos/{repo}/actions/workflows?per_page=100")["workflows"]:
        src = Path(w["path"].replace(".lock.yml", ".md"))
        if w["path"].endswith(".lock.yml") and src.exists():
            workflows.append({"id": w["id"], "name": w["name"], "file": src.name, "timeout": timeout_of(src.read_text())})
    pool = ThreadPoolExecutor(8)
    runs_of = pool.map(lambda w: gh(f"repos/{repo}/actions/workflows/{w['id']}/runs?status=completed&per_page=100"
                                    f"&created=%3E%3D{since}")["workflow_runs"], workflows)
    for w, runs in zip(workflows, runs_of):
        w["runs"] = [r for r in runs if r.get("conclusion") not in NEUTRAL]
    every = [r for w in workflows for r in w["runs"]]
    jobs = pool.map(lambda r: gh(f"repos/{repo}/actions/runs/{r['id']}/attempts/{r.get('run_attempt') or 1}/jobs?per_page=100")["jobs"], every)
    for r, j in zip(every, jobs):
        r["jobs"] = j
    to_read = []
    for w in workflows:
        failed = [r for r in w["runs"] if r.get("conclusion") != "success" and failed_steps(r["jobs"])]
        for r in failed[:LOG_RUNS]:
            job = next((j for j in r["jobs"] if j.get("conclusion") in BAD and j["name"] == "agent"), None) \
                or next((j for j in r["jobs"] if j.get("conclusion") in BAD), None)
            if job:
                to_read.append((r, job["id"]))

    def read(item):
        r, job_id = item
        try:
            return signal_lines(gh(f"repos/{repo}/actions/jobs/{job_id}/logs", raw=True))
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            return [f"(log not read: {e})"]
    for (r, _), sig in zip(to_read, pool.map(read, to_read)):
        r["signals"] = sig

    issues = [i for i in gh(f"repos/{repo}/issues?state=open&labels=agentic-workflows&per_page=100") if not i.get("pull_request")]
    comments = pool.map(lambda i: gh(f"repos/{repo}/issues/{i['number']}/comments?per_page=100") if i.get("comments") else [], issues)
    out = [{"number": i["number"], "title": i["title"], "updated_at": i.get("updated_at"),
            "labels": [l["name"] for l in i.get("labels") or []],
            "doctor_commented": any(DOCTOR.search(c.get("body") or "") for c in cs)} for i, cs in zip(issues, comments)]
    pool.shutdown()
    return workflows, out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "casper-assistant-ai/alerty-pl"))
    p.add_argument("--patterns", default="process/failure-patterns.md")
    p.add_argument("--out")
    p.add_argument("--md")
    a = p.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pat = Path(a.patterns)
    workflows, issues = fetch(a.repo, a.days, now)
    rep = summarize(workflows, issues, known_patterns(pat.read_text() if pat.exists() else ""), now, a.days)
    if a.out:
        Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    md = markdown(rep)
    if a.md:
        Path(a.md).write_text(md)
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
