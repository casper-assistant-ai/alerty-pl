#!/usr/bin/env python3
"""Open alerts of the Security and quality tab, for the security-fixer agent.

    security_alerts.py collect [--repo OWNER/NAME] [--out FILE.json] [--md FILE.md]
    security_alerts.py pending [--repo OWNER/NAME]
    security_alerts.py dismiss --kind KIND --number N --reason REASON --comment TEXT [--repo OWNER/NAME]

`collect` reads every open alert: code scanning (CodeQL, with the data flow of each result from the
latest SARIF on the default branch), code quality findings, Dependabot and secret scanning. Secret
values are never kept. It marks the alerts that an open security-fixer PR or an open security issue
already names in a line `Alert: <kind>#<number>`. A kind the token cannot read is listed under
`unreadable` with the reason (the workflow's GITHUB_TOKEN reads code scanning only; the repository
secret SECURITY_ALERTS_TOKEN, a fine-grained token for this repository with Code scanning, Dependabot
and Secret scanning alerts, read and write, reads all of them).

`pending` prints the number of open alerts that nothing covers yet and the newest one's creation
time (`0 -` when none); the Security watch workflow starts the agent from it.

`dismiss` closes one alert with a reason the agent gave through its `dismiss-alert` safe output.
Only reasons that say the code is fine are allowed (false positive, used in tests, not used,
inaccurate, tolerable risk), each only for the kinds whose API knows it.

Token: GH_TOKEN or GITHUB_TOKEN. Python 3 stdlib only.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
KINDS = ("code-scanning", "code-quality", "dependabot", "secret-scanning")
ALERT_LINE = re.compile(r"(?m)^\s*Alerts?:\s*(.+)$")
ALERT_REF = re.compile(r"\b(code-scanning|code-quality|dependabot|secret-scanning)#(\d+)\b")
# the agent's reason -> what each API calls it; a kind missing here does not take that reason
REASONS = {
    "false_positive": {"code-scanning": "false positive", "secret-scanning": "false_positive",
                       "dependabot": "inaccurate"},
    "used_in_tests": {"code-scanning": "used in tests", "secret-scanning": "used_in_tests"},
    "not_used": {"dependabot": "not_used"},
    "inaccurate": {"dependabot": "inaccurate", "code-scanning": "false positive"},
    "tolerable_risk": {"dependabot": "tolerable_risk", "code-scanning": "won't fix"},
}
COMMENT_MAX = 280


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def token():
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:
        sys.exit("security_alerts: set GH_TOKEN or GITHUB_TOKEN")
    return tok


def request(path, method="GET", body=None, accept="application/vnd.github+json"):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token()}", "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "alerty-pl-security-alerts"})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            link = r.headers.get("Link") or ""
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read() or b"{}").get("message") or e.reason
        except ValueError:
            msg = e.reason
        raise ApiError(e.code, msg) from None
    return (json.loads(raw) if raw else None), link


def paged(path):
    items, url = [], path + ("&" if "?" in path else "?") + "per_page=100"
    while url:
        page, link = request(url)
        items += page
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return items


# ---- pure: shape each API's alert into one record -------------------------------------------

def from_code_scanning(a):
    inst = a.get("most_recent_instance") or {}
    loc = inst.get("location") or {}
    rule = a.get("rule") or {}
    return {"kind": "code-scanning", "number": a["number"], "url": a.get("html_url"),
            "tool": (a.get("tool") or {}).get("name"), "rule": rule.get("id"),
            "title": rule.get("description"), "severity": rule.get("security_severity_level") or rule.get("severity"),
            "tags": rule.get("tags") or [], "path": loc.get("path"), "line": loc.get("start_line"),
            "message": (inst.get("message") or {}).get("text"), "category": inst.get("category"),
            "created_at": a.get("created_at")}


def from_code_quality(f):
    rule, loc = f.get("rule") or {}, f.get("location") or {}
    return {"kind": "code-quality", "number": f["number"], "url": f.get("url"), "tool": "Code quality",
            "rule": rule.get("id"), "title": rule.get("title"), "severity": rule.get("severity"),
            "tags": [rule.get("category")] if rule.get("category") else [], "path": loc.get("path"),
            "line": loc.get("start_line"), "message": (f.get("message") or {}).get("text"),
            "created_at": f.get("created_at")}


def from_dependabot(a):
    dep, adv, vuln = a.get("dependency") or {}, a.get("security_advisory") or {}, a.get("security_vulnerability") or {}
    pkg = dep.get("package") or {}
    patched = (vuln.get("first_patched_version") or {}).get("identifier")
    return {"kind": "dependabot", "number": a["number"], "url": a.get("html_url"), "tool": "Dependabot",
            "rule": adv.get("ghsa_id"), "title": adv.get("summary"), "severity": adv.get("severity"),
            "tags": [], "path": dep.get("manifest_path"), "line": None,
            "message": f"{pkg.get('ecosystem')} {pkg.get('name')} {vuln.get('vulnerable_version_range')}"
                       f" -> first patched {patched or 'none'}",
            "created_at": a.get("created_at")}


def from_secret_scanning(a):
    # never keep the secret itself
    return {"kind": "secret-scanning", "number": a["number"], "url": a.get("html_url"), "tool": "Secret scanning",
            "rule": a.get("secret_type"), "title": a.get("secret_type_display_name"), "severity": "high",
            "tags": [a.get("validity")] if a.get("validity") else [], "path": None, "line": None,
            "message": "push protection bypassed" if a.get("push_protection_bypassed") else "",
            "created_at": a.get("created_at")}


def covered_refs(items):
    """Pure: {"kind#n": "PR #12" | "issue #13"} from open PRs and issues that name alerts."""
    refs = {}
    for it in items:
        what = f"{'PR' if it.get('pull_request') or it.get('is_pr') else 'issue'} #{it['number']}"
        for line in ALERT_LINE.findall(it.get("body") or ""):
            for kind, num in ALERT_REF.findall(line):
                refs.setdefault(f"{kind}#{num}", what)
    return refs


def mark_pending(alerts, refs):
    for a in alerts:
        a["covered_by"] = refs.get(f"{a['kind']}#{a['number']}")
    return [a for a in alerts if not a["covered_by"]]


def flows_by_location(sarif):
    """Pure: {(rule, path, line): [step texts]} from a SARIF log, the data flow of each result."""
    out = {}
    for run in sarif.get("runs") or []:
        for res in run.get("results") or []:
            loc = ((res.get("locations") or [{}])[0].get("physicalLocation") or {})
            key = (res.get("ruleId"), (loc.get("artifactLocation") or {}).get("uri"), (loc.get("region") or {}).get("startLine"))
            steps = []
            for cf in res.get("codeFlows") or []:
                for tf in cf.get("threadFlows") or []:
                    path = []
                    for step in tf.get("locations") or []:
                        pl = (step.get("location") or {}).get("physicalLocation") or {}
                        text = ((step.get("location") or {}).get("message") or {}).get("text") or ""
                        path.append(f"{(pl.get('artifactLocation') or {}).get('uri')}:{(pl.get('region') or {}).get('startLine')} {text}".strip())
                    if path:
                        steps.append(path)
            if steps:
                out.setdefault(key, []).extend(steps[:3])
    return out


def to_markdown(report):
    lines = [f"# Open alerts of {report['repo']}", ""]
    for kind, why in report["unreadable"].items():
        lines.append(f"- {kind}: not readable with this token ({why})")
    if report["unreadable"]:
        lines.append("")
    pending = [a for a in report["alerts"] if not a.get("covered_by")]
    lines.append(f"{len(report['alerts'])} open, {len(pending)} not covered by an open PR or issue.")
    for a in report["alerts"]:
        where = f"{a['path']}:{a['line']}" if a.get("line") else (a.get("path") or "-")
        lines += ["", f"## {a['kind']}#{a['number']} {a.get('rule')} ({a.get('severity')})",
                  f"- {a.get('title')}", f"- where: {where}", f"- tool: {a.get('tool')}; tags: {', '.join(t for t in a.get('tags') or [] if t)}",
                  f"- message: {a.get('message')}", f"- url: {a.get('url')}"]
        if a.get("covered_by"):
            lines.append(f"- covered by {a['covered_by']}: skip")
        for i, flow in enumerate(a.get("flows") or [], 1):
            lines.append(f"- data flow {i}:")
            lines += [f"    {s}" for s in flow]
    return "\n".join(lines) + "\n"


# ---- network --------------------------------------------------------------------------------

def collect(repo):
    base = f"/repos/{repo}"
    report = {"repo": repo, "alerts": [], "unreadable": {}}
    sources = [("code-scanning", f"{base}/code-scanning/alerts?state=open", from_code_scanning),
               ("code-quality", f"{base}/code-quality/findings?state=open", from_code_quality),
               ("dependabot", f"{base}/dependabot/alerts?state=open", from_dependabot),
               ("secret-scanning", f"{base}/secret-scanning/alerts?state=open", from_secret_scanning)]
    for kind, path, shape in sources:
        try:
            report["alerts"] += [shape(a) for a in paged(path)]
        except ApiError as e:
            report["unreadable"][kind] = str(e)
    cs = [a for a in report["alerts"] if a["kind"] == "code-scanning"]
    if cs:
        try:
            analyses = paged(f"{base}/code-scanning/analyses?ref=refs/heads/main")
            latest = {}
            for an in analyses:  # newest first
                latest.setdefault(an.get("category"), an["id"])
            flows = {}
            for aid in latest.values():
                sarif, _ = request(f"{base}/code-scanning/analyses/{aid}", accept="application/sarif+json")
                flows.update(flows_by_location(sarif or {}))
            for a in cs:
                a["flows"] = flows.get((a["rule"], a["path"], a["line"]), [])
        except ApiError as e:
            report["unreadable"]["code-scanning data flows"] = str(e)
    refs = {}
    try:
        prs = [p for p in paged(f"{base}/pulls?state=open") if (p.get("title") or "").startswith("[security-fixer] ")]
        for p in prs:
            p["is_pr"] = True
        issues = paged(f"{base}/issues?state=open&labels=security")
        refs = covered_refs(prs + [i for i in issues if not i.get("pull_request")])
    except ApiError as e:
        report["unreadable"]["open PRs and issues"] = str(e)
    mark_pending(report["alerts"], refs)
    return report


def check_dismissal(kind, reason, comment):
    """Pure: (api_reason, comment) or raise ValueError."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    if kind == "code-quality":
        raise ValueError("code quality findings have no dismiss API; fix them with a PR")
    api = (REASONS.get(reason) or {}).get(kind)
    if not api:
        raise ValueError(f"reason {reason!r} is not allowed for {kind}")
    comment = " ".join((comment or "").split())
    if len(comment) < 20:
        raise ValueError("the comment must say why (at least 20 characters)")
    if len(comment) > COMMENT_MAX:
        comment = comment[:COMMENT_MAX - 1] + "…"
    return api, comment


def dismiss(repo, kind, number, reason, comment):
    api, comment = check_dismissal(kind, reason, comment)
    base = f"/repos/{repo}"
    current, _ = request(f"{base}/{kind}/alerts/{int(number)}")
    if (current or {}).get("state") != "open":
        return f"{kind}#{number} is already {(current or {}).get('state')}"
    if kind == "code-scanning":
        body = {"state": "dismissed", "dismissed_reason": api, "dismissed_comment": comment}
    elif kind == "dependabot":
        body = {"state": "dismissed", "dismissed_reason": api, "dismissed_comment": comment}
    else:
        body = {"state": "resolved", "resolution": api, "resolution_comment": comment}
    request(f"{base}/{kind}/alerts/{int(number)}", method="PATCH", body=body)
    return f"{kind}#{number} dismissed ({api}): {comment}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--out")
    c.add_argument("--md")
    sub.add_parser("pending")
    d = sub.add_parser("dismiss")
    d.add_argument("--kind", required=True)
    d.add_argument("--number", required=True, type=int)
    d.add_argument("--reason", required=True)
    d.add_argument("--comment", required=True)
    for p in (c, sub.choices["pending"], d):
        p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "casper-assistant-ai/alerty-pl"))
    args = ap.parse_args(argv)
    if args.cmd == "dismiss":
        try:
            print(dismiss(args.repo, args.kind, args.number, args.reason, args.comment))
        except (ValueError, ApiError) as e:
            print(f"refused {args.kind}#{args.number}: {e}", file=sys.stderr)
            return 1
        return 0
    report = collect(args.repo)
    if args.cmd == "pending":
        for kind, why in report["unreadable"].items():
            print(f"unreadable {kind}: {why}", file=sys.stderr)
        pending = [a for a in report["alerts"] if not a.get("covered_by")]
        print(len(pending), max((a.get("created_at") or "" for a in pending), default="-") or "-")
        return 0
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    md = to_markdown(report)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(md)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
