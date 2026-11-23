import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import retro  # noqa: E402

SINCE = "2026-11-14T00:00:00Z"


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
