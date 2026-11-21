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
             "created_at": "2026-11-20T10:00:00Z", "merged_at": None, "state": "open", "labels": ["agent", "needs-attention"]},
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


if __name__ == "__main__":
    unittest.main()
