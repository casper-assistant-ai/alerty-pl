#!/usr/bin/env python3
"""Start again the agent runs that z.ai stopped, so their work does not wait for the next schedule.

    agent_retry.py [--repo OWNER/NAME] [--hours 12] [--watch MINUTES] [--dry-run] [--now ISO]

A gh-aw agent run that ends on a model API error (429 or 5xx from z.ai: 1305 overloaded, 1302 rate
limit, 1308 the 5-hour quota) lost its whole session; the next scheduled run of a queue agent such as
the issue-worker comes up to two hours later, and an agent started by an event never runs again for
that event (#146 waited from 19:21 to 21:25 UTC on 2026-11-25). This script re-runs such a run
(`POST /actions/runs/{id}/rerun`: same event, same inputs, a new attempt), when:

- the run's last attempt failed in the agent job, and Claude's final record says `api_error` with
  status 429 or 5xx, or the last assistant message is such an API error;
- the agent sent no output that a second attempt would repeat (a PR, an issue, a closing, a push,
  a dispatch; a comment or a label is harmless);
- it is the run's attempt 1 or 2 (at most three attempts), it finished within `--hours`, and no newer
  run of that workflow for the same event and title is running or succeeded;
- its time has come: 10 minutes after the failure, or for 1308 one minute after the quota's reset
  time (z.ai gives it in Beijing time, UTC+8), never later than 30 minutes after the failure for
  the other codes.

At most one run is re-run per pass; the next due one waits STAGGER (5 minutes), so a quota reset
does not start every waiting session at once.

With `--watch N` it keeps looking for N minutes while a retry is due later, sleeping until the next
one (at most 10 minutes at a time), so a quota that resets 40 minutes later is still met by one job.
The pure functions are tested in tests/test_agent_retry.py; only fetch-like helpers talk to GitHub.
Python 3 stdlib only.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_failures import ANSI, STAMP, agent_failed, gh

WORKFLOWS = Path(".github/workflows")
MAX_ATTEMPTS = 3            # the first run and two retries
DELAY = dt.timedelta(minutes=10)
AFTER_RESET = dt.timedelta(minutes=1)
UNKNOWN_RESET = dt.timedelta(minutes=30)
# one re-run at a time: after a quota reset every waiting run fell due in the same minute, and the
# burst of sessions met 429 [1302] «Rate limit reached for requests» (11-27 07:21 and 07:35 UTC)
STAGGER = dt.timedelta(minutes=5)
BEIJING = dt.timezone(dt.timedelta(hours=8))
BUSY = {"queued", "in_progress", "waiting", "requested", "pending"}
# Safe outputs a second attempt may repeat without harm; any other one means the work went out.
HARMLESS = {"noop", "missing_tool", "missing_data", "report_incomplete", "add_comment", "add_labels"}
SAFE_TOOL = re.compile(r'"name"\s*:\s*"mcp__safeoutputs__(\w+)"')
RESET = re.compile(r"reset at (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
CODE = re.compile(r"\[(1\d{3})\]")
TEXT_STATUS = re.compile(r"API Error: (?:Request rejected \()?(\d{3})")


def _time(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _iso(t):
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def api_error(log_text):
    """The model API error that ended the agent's session, or None.

    Returns {"status": 429, "code": "1308", "text": ..., "reset": datetime|None}. Only Claude Code's own
    records count (the final `result` with terminal_reason api_error, or an assistant message marked
    is_api_error_message): the session also quotes issues and logs that name these errors."""
    last = None
    for raw in (log_text or "").splitlines():
        line = ANSI.sub("", STAMP.sub("", raw.split("\t")[-1])).strip()
        if not line.startswith("{") or not ('"type":"result"' in line or "is_api_error_message" in line):
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        status, text = None, ""
        if rec.get("type") == "result":
            text = str(rec.get("result") or "")
            m = TEXT_STATUS.match(text)
            if rec.get("terminal_reason") == "api_error":
                status = rec.get("api_error_status") or (int(m.group(1)) if m else None)
            elif rec.get("is_error") and m:  # older Claude Code: no terminal_reason, the status is in the text
                status = int(m.group(1))
            else:
                last = None  # the session went on after an earlier API error
                continue
        elif rec.get("type") == "assistant" and rec.get("is_api_error_message"):
            status = rec.get("api_error_status")
            content = (rec.get("message") or {}).get("content") or []
            text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        else:
            continue
        if not isinstance(status, int) or not (status == 429 or status >= 500):
            last = None  # a later, different API error (401, 400...) is not a provider limit
            continue
        code = CODE.search(text)
        reset = RESET.search(text)
        last = {"status": status, "code": code.group(1) if code else None, "text": text[:200],
                "reset": dt.datetime.fromisoformat(reset.group(1)).replace(tzinfo=BEIJING) if reset else None}
    return last


def sent_outputs(log_text):
    """Safe-output tools the agent called that a second attempt would repeat."""
    return sorted({m for m in SAFE_TOOL.findall(log_text or "") if m not in HARMLESS})


def due_at(run, err):
    """When the failed run may be re-run: after the quota reset for 1308, else DELAY after it ended."""
    ended = _time(run.get("updated_at") or run["created_at"])
    if err.get("code") == "1308":
        return (err["reset"] + AFTER_RESET) if err.get("reset") else ended + UNKNOWN_RESET
    return ended + DELAY


def superseded(run, runs):
    """A newer run of the same workflow for the same event (schedule and dispatch count as one) and title
    makes the retry pointless: it is running, it succeeded, or it failed too and is the one to re-run
    (two re-runs of one queue agent would take the same issue)."""
    group = lambda r: "queue" if r.get("event") in ("schedule", "workflow_dispatch") else r.get("event")
    start = _time(run["created_at"])
    for r in runs:
        if r["id"] == run["id"] or _time(r["created_at"]) <= start:
            continue
        if group(r) != group(run) or r.get("display_title") != run.get("display_title"):
            continue
        if r.get("status") in BUSY or r.get("conclusion") in ("success", "failure", "timed_out"):
            return r
    return None


def candidates(runs, now, hours):
    """Failed runs worth a look, newest first: last attempt failed, attempts left, recent."""
    out = []
    for r in runs:
        if r.get("status") != "completed" or r.get("conclusion") != "failure":
            continue
        if (r.get("run_attempt") or 1) >= MAX_ATTEMPTS:
            continue
        if now - _time(r.get("updated_at") or r["created_at"]) > dt.timedelta(hours=hours):
            continue
        out.append(r)
    return out


def decide(run, runs, jobs, log_text, now):
    """("retry"|"wait"|"skip", reason, due) for one failed run."""
    if not agent_failed(jobs):
        return "skip", "the agent job did not fail", None
    newer = superseded(run, runs)
    if newer:
        return "skip", f"run {newer['id']} came after it", None
    err = api_error(log_text)
    if not err:
        return "skip", "not a model API limit", None
    sent = sent_outputs(log_text)
    if sent:
        return "skip", f"outputs already sent: {', '.join(sent)}", None
    due = due_at(run, err)
    what = f"API {err['status']}" + (f" [{err['code']}]" if err.get("code") else "")
    if due > now:
        return "wait", f"{what}, retry at {_iso(due)}", due
    return "retry", what, due


def agents(repo):
    """The gh-aw agent workflows: a .lock.yml whose .md source is in the checkout."""
    out = []
    for w in gh(f"repos/{repo}/actions/workflows?per_page=100")["workflows"]:
        if w["path"].endswith(".lock.yml") and Path(w["path"].replace(".lock.yml", ".md")).exists():
            out.append(w)
    return out


def agent_log(repo, jobs):
    job = next((j for j in jobs if j.get("name") == "agent"), None)
    if not job:
        return ""
    try:
        return gh(f"repos/{repo}/actions/jobs/{job['id']}/logs", raw=True)
    except RuntimeError as e:
        print(f"  log of job {job['id']} not read: {e}", file=sys.stderr)
        return ""


def rerun(repo, run_id, post=None):
    import subprocess
    post = post or subprocess.run
    out = post(["gh", "api", "-X", "POST", f"repos/{repo}/actions/runs/{run_id}/rerun"],
               capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])


def scan(repo, now, hours, dry_run, seen, logs=None):
    """One pass over every agent; returns (lines, next due time or None). `logs` keeps the agent logs of
    runs that wait, so a watch does not download them again."""
    logs = {} if logs is None else logs
    lines, nxt, started = [], None, False
    for w in agents(repo):
        runs = gh(f"repos/{repo}/actions/workflows/{w['id']}/runs?per_page=30")["workflow_runs"]
        for r in candidates(runs, now, hours):
            key = (r["id"], r.get("run_attempt") or 1)
            if key in seen:
                continue
            jobs = gh(f"repos/{repo}/actions/runs/{r['id']}/attempts/{key[1]}/jobs?per_page=100")["jobs"]
            if key not in logs:
                logs[key] = agent_log(repo, jobs) if agent_failed(jobs) else ""
            verdict, reason, due = decide(r, runs, jobs, logs[key], now)
            label = f"{w['name']} run {r['id']} attempt {key[1]} ({r.get('event')})"
            if verdict == "skip":
                seen.add(key)
                logs.pop(key, None)
                continue
            if verdict == "wait":
                lines.append(f"{label}: {reason}")
                nxt = due if nxt is None or due < nxt else nxt
                continue
            if started:  # STAGGER: the next one waits for the next pass
                due = now + STAGGER
                lines.append(f"{label}: {reason}, waits {int(STAGGER.total_seconds() // 60)} minutes after the last re-run")
                nxt = due if nxt is None or due < nxt else nxt
                continue
            started = True
            seen.add(key)
            logs.pop(key, None)
            if dry_run:
                lines.append(f"{label}: {reason}, would re-run")
                continue
            try:
                rerun(repo, r["id"])
                lines.append(f"{label}: {reason}, re-run started ({r['html_url']})")
            except RuntimeError as e:
                lines.append(f"{label}: {reason}, re-run refused: {e}")
    return lines, nxt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "casper-assistant-ai/alerty-pl"))
    ap.add_argument("--hours", type=float, default=12)
    ap.add_argument("--watch", type=float, default=0, help="minutes to keep waiting for retries due later")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", help="ISO time instead of the clock (tests, dry runs)")
    a = ap.parse_args(argv)
    clock = (lambda: _time(a.now)) if a.now else (lambda: dt.datetime.now(dt.UTC))
    stop = clock() + dt.timedelta(minutes=a.watch)
    seen, logs, report = set(), {}, []
    while True:
        now = clock()
        lines, nxt = scan(a.repo, now, a.hours, a.dry_run, seen, logs)
        report += [f"{_iso(now)} {l}" for l in lines]
        for l in lines:
            print(l)
        if nxt is None or nxt > stop or a.now:
            break
        time.sleep(max(30, min(600, (nxt - clock()).total_seconds() + 5)))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Agent retry\n\n" + ("\n".join(f"- {l}" for l in report) or "- nothing to retry") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
