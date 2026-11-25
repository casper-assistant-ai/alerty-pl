import contextlib
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import retro  # noqa: E402

SINCE = "2026-11-14T00:00:00Z"


class Api(unittest.TestCase):
    """api() against a GitHub that refuses. A rate limit (403 or 429) gets one more try after the
    wait GitHub names; what is still refused ends in one clear line (ApiError), which main() prints.
    Before, the queue of the issue-worker, the retro's numbers and the daily status died on a
    traceback (`HTTPError: HTTP Error 403: rate limit exceeded`) in their first step."""

    PATH = "/repos/o/r/issues?per_page=100"
    URL = "https://api.github.com/repos/o/r/issues?per_page=100"
    LIMITED = {"Retry-After": "60"}
    BODY = b'{"message": "API rate limit exceeded for installation ID 1."}'

    def setUp(self):
        for p in (mock.patch.object(retro.time, "sleep"), mock.patch.object(retro.time, "time", return_value=1_700_000_000)):
            p.start()
            self.addCleanup(p.stop)
        log = io.StringIO()
        quiet = contextlib.redirect_stderr(log)  # the warning of the second try must not print in the test log
        self.addCleanup(quiet.__exit__, None, None, None)
        quiet.__enter__()
        self.log = log

    def refused(self, code, reason, headers=None, body=b""):
        """An HTTPError as urlopen raises it: body None is an error with nothing to read."""
        return urllib.error.HTTPError(self.URL, code, reason, headers or {}, None if body is None else io.BytesIO(body))

    class answered:
        def __init__(self, body=b"[]", link=None):
            self.body = body
            self.headers = {"Link": link} if link else {}

        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.body

    def test_a_rate_limit_gets_one_more_try_after_the_wait_github_names(self):
        answers = [self.refused(403, "rate limit exceeded", self.LIMITED, self.BODY),
                   self.answered(b'[{"number": 1}]', '<https://api.github.com/next>; rel="next"')]
        with mock.patch.object(retro.urllib.request, "urlopen", side_effect=answers) as opened:
            data, nxt = retro.api(self.PATH, "t")
        self.assertEqual(data, [{"number": 1}])
        self.assertEqual(nxt, "https://api.github.com/next")
        self.assertEqual(opened.call_count, 2)
        retro.time.sleep.assert_called_once_with(60)
        self.assertEqual(self.log.getvalue(),
                         f"::warning::GitHub API 403 on GET {self.URL}: trying once more in 60 s\n")

    def test_rate_wait_reads_retry_after_then_the_reset_time(self):
        now = 1_700_000_000
        wait = retro.rate_wait
        self.assertEqual(wait({"Retry-After": "60", "X-RateLimit-Reset": "1"}, now), (60, 60))
        self.assertEqual(wait({"X-RateLimit-Reset": str(now + 30)}, now), (30, 30))
        self.assertEqual(wait({"X-RateLimit-Reset": str(now - 5)}, now), (0, -5))  # it ended already: now
        # a wait over MAX_WAIT (the primary limit of an hour) is not waited out, and a wait not
        # named at all (a 403 that is no rate limit) is the short one before a second try
        self.assertEqual(wait({"X-RateLimit-Reset": str(now + 1500)}, now), (None, 1500))
        self.assertEqual(wait({"Retry-After": "1500"}, now), (None, 1500))
        for unnamed in ({}, None, {"Retry-After": "soon"}):
            self.assertEqual(wait(unnamed, now), (retro.DEFAULT_WAIT, None))

    def test_a_429_and_the_reset_time_read_the_same_way(self):
        answers = [self.refused(429, "Too Many Requests", {"X-RateLimit-Reset": str(1_700_000_000 + 45)}),
                   self.answered()]
        with mock.patch.object(retro.urllib.request, "urlopen", side_effect=answers):
            self.assertEqual(retro.api(self.PATH, "t"), ([], None))
        retro.time.sleep.assert_called_once_with(45)

    def test_still_refused_after_the_second_try_is_one_line(self):
        # two answers, each with its own body: the first is read and closed before the second try
        twice = mock.Mock(side_effect=[self.refused(403, "rate limit exceeded", self.LIMITED, self.BODY) for _ in (1, 2)])
        with mock.patch.object(retro.urllib.request, "urlopen", twice):
            with self.assertRaises(retro.ApiError) as c:
                retro.api(self.PATH, "t")
        self.assertEqual(twice.call_count, 2)
        self.assertEqual(str(c.exception),
                         "GitHub API 403 (API rate limit exceeded for installation ID 1.) "
                         f"on GET {self.URL}; the second try, after 60 s, was refused as well; GitHub asks to wait 60 s more")

    def test_a_long_message_is_cut_so_the_line_stays_readable(self):
        once = mock.Mock(side_effect=self.refused(500, "x", {}, b'{"message": "' + b"x" * 300 + b'"}'))
        with mock.patch.object(retro.urllib.request, "urlopen", once):
            with self.assertRaises(retro.ApiError) as c:
                retro.api(self.PATH, "t")
        self.assertEqual(str(c.exception), f"GitHub API 500 ({'x' * 120}) on GET {self.URL}")

    def test_a_wait_over_a_minute_is_not_waited_out(self):
        once = mock.Mock(side_effect=self.refused(429, "Too Many Requests", {"Retry-After": "1500"}, b'{"message": "slow down"}'))
        with mock.patch.object(retro.urllib.request, "urlopen", once):
            with self.assertRaises(retro.ApiError) as c:
                retro.api(self.PATH, "t")
        self.assertEqual(str(c.exception), f"GitHub API 429 (slow down) on GET {self.URL}; GitHub asks to wait 1500 s more")
        self.assertEqual(once.call_count, 1)
        retro.time.sleep.assert_not_called()

    def test_a_403_that_is_no_rate_limit_gets_a_second_try_as_well(self):
        forbidden = b'{"message": "Resource not accessible by integration"}'
        twice = mock.Mock(side_effect=[self.refused(403, "Forbidden", {}, forbidden) for _ in (1, 2)])
        with mock.patch.object(retro.urllib.request, "urlopen", twice):
            with self.assertRaises(retro.ApiError) as c:
                retro.api(self.PATH, "t")
        self.assertEqual(str(c.exception), f"GitHub API 403 (Resource not accessible by integration) on GET {self.URL}; "
                         f"the second try, after {retro.DEFAULT_WAIT} s, was refused as well")
        self.assertEqual(twice.call_count, 2)
        retro.time.sleep.assert_called_once_with(retro.DEFAULT_WAIT)

    def test_another_status_is_not_tried_again_and_reads_the_same(self):
        # the message of the JSON body, else the reason phrase: a body that is not JSON, or none to read
        for reason, body in [("Not Found", b'{"message": "Not Found"}'), ("Internal Server Error", b"<html>oops</html>"),
                             ("Service Unavailable", None)]:
            code = 404 if reason == "Not Found" else 503
            once = mock.Mock(side_effect=self.refused(code, reason, {}, body))
            with mock.patch.object(retro.urllib.request, "urlopen", once):
                with self.assertRaises(retro.ApiError) as c:
                    retro.api(self.PATH, "t")
            self.assertEqual(str(c.exception), f"GitHub API {code} ({reason}) on GET {self.URL}")
            self.assertEqual(once.call_count, 1, reason)
        retro.time.sleep.assert_not_called()

    def test_a_dispatch_refused_with_429_is_sent_once_more_body_and_all(self):
        answers = [self.refused(429, "Too Many Requests", {"Retry-After": "1"}), self.answered(b"")]
        path = "/repos/o/r/actions/workflows/x.lock.yml/dispatches"
        with mock.patch.object(retro.urllib.request, "urlopen", side_effect=answers) as opened:
            self.assertEqual(retro.api(path, "t", method="POST", body={"ref": "main"}), (None, None))
        self.assertEqual([json.loads(c.args[0].data) for c in opened.call_args_list], [{"ref": "main"}] * 2)
        self.assertEqual([c.args[0].get_method() for c in opened.call_args_list], ["POST", "POST"])

    def test_main_exits_with_that_line_not_a_traceback(self):
        line = f"GitHub API 403 (rate limit exceeded) on GET {self.URL}; GitHub asks to wait 1500 s more"
        with mock.patch.dict(os.environ, {"GH_TOKEN": "t"}), \
                mock.patch.object(retro, "fetch", side_effect=retro.ApiError(line)):
            with self.assertRaises(SystemExit) as c:
                retro.main(["metrics", "--days", "7"])
        self.assertEqual(c.exception.code, "retro: " + line)


class Kind(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(retro.kind("feat(map): slider"), "dev")
        self.assertEqual(retro.kind("[site-fixer] fix(site): null label"), "dev")
        self.assertEqual(retro.kind("docs: readme"), "book")
        self.assertEqual(retro.kind("chore(data): 2 active, 47 alerts"), "data")
        self.assertEqual(retro.kind("data: 2 active"), "data")
        self.assertEqual(retro.kind("chore(process): retro week 47"), "process")
        self.assertEqual(retro.kind("Add something"), "other")

    def test_gate_type_for_plain_titles(self):
        self.assertEqual(retro.kind("[site-designer] Honest status signals", "site-designer"), "dev")
        self.assertEqual(retro.kind("[docs-keeper] Refresh README", "docs-keeper"), "book")


class Summarize(unittest.TestCase):
    def test_week(self):
        role = {"site-designer": "builder", "test-improver": "builder", "daily-status": "reporter"}
        prs = [
            {"number": 5, "title": "[site-designer] feat(site): dark mode", "body": "Refs #3",
             "created_at": "2026-11-20T10:00:00Z", "merged_at": "2026-11-20T11:00:00Z", "state": "closed", "labels": ["agent"]},
            {"number": 6, "title": "[test-improver] test: more", "body": "",
             "created_at": "2026-11-20T10:00:00Z", "merged_at": None, "state": "closed", "labels": ["agent"]},
        ]
        issues = [
            {"number": 2, "title": "[daily-status] 2026-11-21", "state": "open", "created_at": "2026-11-21T00:00:00Z", "labels": ["report"]},
            {"number": 3, "title": "Map bug", "state": "open", "created_at": "2026-11-19T00:00:00Z", "labels": []},
            {"number": 4, "title": "Old bug", "state": "open", "created_at": "2026-10-01T00:00:00Z", "labels": []},
            {"number": 8, "title": "[aw] No-Op Runs", "state": "open", "created_at": "2026-11-21T00:00:00Z", "labels": ["agentic-workflows"]},
        ]
        runs = [{"path": ".github/workflows/site-designer.lock.yml", "conclusion": "success"},
                {"path": ".github/workflows/test-improver.lock.yml", "conclusion": "success"},
                {"path": ".github/workflows/test-improver.lock.yml", "conclusion": "success"},
                {"path": ".github/workflows/daily-status.lock.yml", "conclusion": "skipped"},
                {"path": ".github/workflows/daily-status.lock.yml", "conclusion": "success"}]
        commits = [{"subject": "feat(map): x"}, {"subject": "chore(data): y"}]
        m = retro.summarize(commits, prs, issues, runs, role, SINCE)
        self.assertEqual(m["agent_output"]["dev"], 1)
        self.assertEqual(m["agent_output"]["book"], 1)
        self.assertEqual(m["dev_share"], 0.5)
        self.assertEqual(m["issues_without_pr"], [4])
        self.assertEqual(m["tooling_notices"], 1)
        self.assertEqual(m["builders_without_merge"], ["test-improver"])
        self.assertEqual(m["reporters_only"], ["daily-status"])
        self.assertEqual(m["agents"]["test-improver"]["rejected"], 1)
        self.assertEqual(m["agents"]["test-improver"]["idle"], 1)
        self.assertEqual(m["agents"]["daily-status"]["runs"], 1)
        self.assertEqual(m["main_commits"]["data"], 1)
        self.assertIn("development share **50%**", retro.markdown(m))


class Roles(unittest.TestCase):
    def test_roles_from_sources(self):
        r = retro.roles()
        self.assertEqual(r["process-retro"], "process")
        self.assertEqual(r["agent-coach"], "process")
        self.assertEqual(r["site-designer"], "builder")
        self.assertEqual(r["daily-status"], "reporter")


class Schedule(unittest.TestCase):
    def test_caps_and_unknown(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"max_extra_runs_per_week": 9, "extra_runs": {
                "site-designer": ["mon", "tue", "wed", "thu", "mon"], "evil": ["mon"],
                "process-retro": ["mon"], "test-improver": ["xyz", "fri"]}}, f)
        plan = retro.load_schedule(f.name, {"site-designer", "test-improver", "process-retro"})
        self.assertEqual(plan, {"site-designer": ["mon", "tue", "wed"], "test-improver": ["fri"]})

    def test_repo_schedule_is_valid(self):
        plan = retro.load_schedule(retro.ROOT / "process" / "schedule.json", {"site-designer"})
        self.assertIsInstance(plan, dict)


class Queue(unittest.TestCase):
    def issues(self):
        return [
            {"number": 2, "title": "[daily-status] 2026-11-21", "state": "open",
             "created_at": "2026-11-21T14:00:00Z", "labels": ["agent", "report"]},
            {"number": 6, "title": "[aw] Security auditor: hit engine rate limit (HTTP 429)",
             "state": "open", "created_at": "2026-11-21T15:00:00Z", "labels": ["agentic-workflows"]},
            {"number": 8, "title": "[aw] No-Op Runs", "state": "open",
             "created_at": "2026-11-21T19:00:00Z", "labels": ["agentic-workflows"]},
            {"number": 9, "title": "[dev-task] Cover rcb.status()", "state": "open",
             "created_at": "2026-11-21T22:00:00Z", "labels": ["tests", "dev-task"]},
            {"number": 11, "title": "[ci-doctor] Update data failed", "state": "open",
             "created_at": "2026-11-22T01:00:00Z", "labels": ["agent", "ci"]},
            {"number": 1, "title": "old", "state": "closed", "created_at": "2026-11-20T00:00:00Z",
             "labels": []},
        ]

    def test_order_kinds_and_links(self):
        prs = [{"number": 20, "title": "[test-improver] test: status", "body": "Closes #9",
                "state": "open", "created_at": "2026-11-22T02:00:00Z", "labels": ["agent"]},
               {"number": 21, "title": "[site-designer] feat: x", "body": "Closes #2",
                "state": "closed", "created_at": "2026-11-22T02:00:00Z", "labels": ["agent"]}]
        q = retro.queue(self.issues(), prs, "2026-11-22")
        self.assertEqual([x["kind"] for x in q["issues"]],
                         ["ci", "aw-notice", "dev-task", "report", "managed"])
        self.assertEqual(q["actionable"], [11, 6, 2])
        self.assertFalse(q["improvement_due"])
        self.assertIn("| #9 | dev-task | #20 |", retro.queue_md(q))

    def test_detection_tracker_is_not_work(self):
        # gh-aw's "[aw] Detection Runs" is a log it keeps itself: not listed, not actionable
        tracker = {"number": 82, "title": "[aw] Detection Runs", "state": "open",
                   "created_at": "2026-11-24T01:46:45Z", "labels": ["agentic-workflows"]}
        q = retro.queue(self.issues() + [tracker], [], "2026-11-24")
        self.assertEqual([x["number"] for x in q["issues"]], [11, 6, 9, 2, 8])
        self.assertEqual(q["actionable"], [11, 6, 9, 2])
        # only that title: a failure notice that starts with the same words is still work
        self.assertEqual(retro.issue_kind(tracker["title"], tracker["labels"]), "aw-notice")
        notice = dict(tracker, number=83, title="[aw] Detection Runs: engine driver crashed")
        self.assertIn(83, retro.queue(self.issues() + [notice], [], "2026-11-24")["actionable"])

    def test_process_doctor_issues_are_not_work(self):
        # agent-health's failure issues and the doctor's workflow-change issues belong to the process-doctor
        health = {"number": 96, "title": "[aw] CI doctor: 4 failed runs in a row", "state": "open",
                  "created_at": "2026-11-24T11:24:21Z", "labels": ["agentic-workflows", "agent-health"]}
        patch = {"number": 98, "title": "[process-doctor] workflow change: issue-worker timeout", "state": "open",
                 "created_at": "2026-11-24T12:00:00Z", "labels": ["agentic-workflows", "workflow-change"]}
        self.assertEqual(retro.issue_kind(health["title"], health["labels"]), "managed")
        self.assertEqual(retro.issue_kind(patch["title"], patch["labels"]), "managed")
        q = retro.queue(self.issues() + [health, patch], [], "2026-11-24")
        self.assertNotIn(96, q["actionable"])
        self.assertNotIn(98, q["actionable"])

    def test_improvement_due_once_a_day(self):
        q = retro.queue([], [], "2026-11-22")
        self.assertTrue(q["improvement_due"])
        done = [{"number": 30, "title": "[issue-worker] test: more cases",
                 "body": "Improvement PR (queue empty): changelog tests", "state": "open",
                 "created_at": "2026-11-22T08:00:00Z", "labels": ["agent"]}]
        self.assertFalse(retro.queue([], done, "2026-11-22")["improvement_due"])
        self.assertTrue(retro.queue([], done, "2026-11-23")["improvement_due"])
        fix = [dict(done[0], body="Fixes the parser. An improvement too.")]
        self.assertTrue(retro.queue([], fix, "2026-11-22")["improvement_due"])

    def test_rejected_prs_and_give_up(self):
        issues = [{"number": 40, "title": "Map bug", "state": "open", "labels": [],
                   "created_at": "2026-11-21T00:00:00Z"},
                  {"number": 41, "title": "Tooltip bug", "state": "open", "labels": [],
                   "created_at": "2026-11-21T01:00:00Z"}]
        closed = lambda n, ref: {"number": n, "title": "[issue-worker] fix: y", "body": f"Closes #{ref}",
                                 "state": "closed", "merged_at": None, "labels": ["agent"],
                                 "created_at": "2026-11-21T08:00:00Z"}
        merged = dict(closed(52, 41), merged_at="2026-11-21T09:00:00Z")
        q = retro.queue(issues, [closed(50, 40), closed(51, 40), closed(53, 41), merged], "2026-11-22")
        by = {x["number"]: x for x in q["issues"]}
        self.assertEqual(by[40]["rejected_prs"], [50, 51])
        self.assertEqual(by[41]["rejected_prs"], [53])
        self.assertEqual(q["give_up"], [40])
        self.assertFalse(q["improvement_due"])
        self.assertIn("| #40 | request | none | #50, #51 (give up: close the issue with the label agent-gave-up) |", retro.queue_md(q))


class GaveUp(unittest.TestCase):
    """The give-up ladder: the worker labels, the retro reads the label, the daily status lists it."""
    SINCE = "2026-11-22T00:00:00Z"

    def closed(self, n, closed_at, labels=("agent-gave-up",), **extra):
        return dict({"number": n, "title": f"Issue {n}", "state": "closed", "closed_at": closed_at,
                     "html_url": f"https://github.com/o/r/issues/{n}", "labels": list(labels)}, **extra)

    def test_only_closed_labelled_issues_since_the_window_newest_first(self):
        issues = [
            self.closed(1, "2026-11-22T05:00:00Z"),
            self.closed(2, "2026-11-23T05:00:00Z"),
            self.closed(3, "2026-11-21T23:59:59Z"),                      # before the window
            self.closed(4, "2026-11-23T01:00:00Z", labels=("bug",)),     # closed with another reason
            self.closed(5, "2026-11-23T02:00:00Z", pull_request=True),   # a PR carrying the label
            dict(self.closed(6, None), state="open"),                    # reopened by a human
        ]
        got = retro.gave_up(issues, self.SINCE)
        self.assertEqual([x["number"] for x in got], [2, 1])
        self.assertEqual(got[0], {"number": 2, "title": "Issue 2", "closed_at": "2026-11-23T05:00:00Z",
                                  "url": "https://github.com/o/r/issues/2"})

    def test_issues_the_retro_log_names_are_handled_once(self):
        log = ("| 2026-11-22 | 70% | 7 | 3 | block refreshed; Gave up: #1 split into #20 #21, #7 lesson |\n"
               "| 2026-11-23 | 69% | 11 | 5 | no change; PR #2 merged |\n")  # #2 here is not a give-up
        self.assertEqual(retro.handled_numbers(log), {1, 20, 21, 7})
        issues = [self.closed(1, "2026-11-22T05:00:00Z"), self.closed(2, "2026-11-23T05:00:00Z")]
        got = retro.gave_up(issues, self.SINCE, retro.handled_numbers(log))
        self.assertEqual([x["number"] for x in got], [2])
        self.assertEqual(retro.handled_numbers(""), set())

    def test_markdown_lists_each_issue_or_says_none(self):
        items = retro.gave_up([self.closed(2, "2026-11-23T05:00:00Z")], self.SINCE)
        md = retro.gave_up_md(items, self.SINCE)
        self.assertIn("1 issue(s) the issue-worker gave up on", md)
        self.assertIn("- #2 Issue 2 (closed 2026-11-23T05:00:00Z) https://github.com/o/r/issues/2", md)
        self.assertIn("No issue closed with the label agent-gave-up", retro.gave_up_md([], self.SINCE))

    def test_the_queue_marker_names_the_label_the_worker_must_use(self):
        issues = [{"number": 40, "title": "Map bug", "state": "open", "labels": [], "created_at": "2026-11-21T00:00:00Z"}]
        closed = lambda n: {"number": n, "title": "[issue-worker] fix: y", "body": "Closes #40", "state": "closed",
                            "merged_at": None, "labels": ["agent"], "created_at": "2026-11-21T08:00:00Z"}
        q = retro.queue(issues, [closed(50), closed(51)], "2026-11-22")
        self.assertEqual(q["give_up"], [40])
        self.assertIn(f"close the issue with the label {retro.GAVE_UP_LABEL}", retro.queue_md(q))
        self.assertEqual(retro.GAVE_UP_LABEL, "agent-gave-up")

    def test_workflows_use_the_same_label(self):
        wf = Path(__file__).resolve().parent.parent / ".github" / "workflows"
        for name in ("issue-worker.md", "process-retro.md", "daily-status.md"):
            self.assertIn(retro.GAVE_UP_LABEL, (wf / name).read_text(encoding="utf-8"), name)
        self.assertRegex((wf / "issue-worker.md").read_text(encoding="utf-8"),
                         r"add-labels:\s*\n\s*allowed: \[agent-gave-up\]")


if __name__ == "__main__":
    unittest.main()
