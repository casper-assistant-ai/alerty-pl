import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import changelog

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "changelog.py"


def c(subject, body=""):
    return {"sha": "0" * 40, "date": "2026-11-21T00:00:00+01:00", "subject": subject, "body": body,
            "cc": changelog.parse(subject, body)}


class Parse(unittest.TestCase):
    def test_conventional(self):
        p = changelog.parse("feat(map): day slider")
        self.assertEqual((p["type"], p["scope"], p["breaking"], p["desc"]), ("feat", "map", False, "day slider"))

    def test_breaking_bang_and_footer(self):
        self.assertTrue(changelog.parse("feat!: new data format")["breaking"])
        self.assertTrue(changelog.parse("fix: x", "BREAKING CHANGE: alerts.json moved")["breaking"])

    def test_rejects_free_text_and_unknown_types(self):
        self.assertIsNone(changelog.parse("Add a map"))
        self.assertIsNone(changelog.parse("feature: a map"))
        self.assertIsNone(changelog.parse("feat:no space"))


class Versions(unittest.TestCase):
    def test_level(self):
        self.assertEqual(changelog.level([c("docs: readme"), c("fix: y")]), "patch")
        self.assertEqual(changelog.level([c("fix: y"), c("feat(map): x")]), "minor")
        self.assertEqual(changelog.level([c("feat!: x"), c("fix: y")]), "major")
        self.assertIsNone(changelog.level([c("docs: readme"), c("chore(data): 2 active")]))

    def test_bump(self):
        self.assertEqual(changelog.bump((1, 5, 1), "minor"), (1, 6, 0))
        self.assertEqual(changelog.bump((1, 5, 1), "patch"), (1, 5, 2))
        self.assertEqual(changelog.bump((1, 5, 1), "major"), (2, 0, 0))

    def test_lint(self):
        self.assertEqual(changelog.lint_subjects(["feat: a", "chore(data): 1 active, 2 alerts", "data: old bot"]), 0)
        self.assertEqual(changelog.lint_subjects(["Update stuff"]), 1)

    def test_lint_good_subjects(self):
        good = [
            "feat(map): day slider over the archive",
            "fix(parser): keep the old archive on a failed page",
            "feat(site)!: alerts.json moves to per-powiat files",
            'revert: "feat(map): day slider" again',
            "perf(parser): fewer detail-page fetches",
            "chore(release): v1.0.0",
        ]
        self.assertEqual(changelog.lint_subjects(good), 0)

    def test_lint_breaking_subjects(self):
        self.assertEqual(changelog.lint_subjects(["feat!: new data format", "fix(parser)!: drop legacy fields",
                                                  "fix: x (BREAKING CHANGE: alerts.json moved)"]), 0)
        self.assertTrue(changelog.parse("fix: x", "BREAKING CHANGE: alerts.json moved")["breaking"])
        self.assertEqual(changelog.level([c("fix: x", "BREAKING CHANGE: alerts.json moved")]), "major")

    def test_lint_bad_subjects(self):
        bad = ["Add a map", "feature: a map", "feat:no space", "fix:", "feat(): empty scope",
               "feat(Map): uppercase scope", "feat: ", "fix\nsecond line"]
        self.assertEqual(changelog.lint_subjects(bad), 1)


class LintCli(unittest.TestCase):
    """`lint --title` checks one PR title without touching git."""

    def run_lint(self, title):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "lint", "--title", title],
                              capture_output=True, text=True)

    def test_good_title_passes(self):
        # ci.yml strips the "[agent-name] " prefix before linting a PR title
        r = self.run_lint("test(changelog): cover lint")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_agent_prefix_alone_is_not_conventional(self):
        self.assertEqual(changelog.lint_subjects(["[issue-worker] test(changelog): cover lint"]), 1)

    def test_bad_title_fails_with_a_hint(self):
        r = self.run_lint("Honest status signals")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a Conventional Commit", r.stderr)
        self.assertIn("feat", r.stderr)

    def test_cut_title_fails_and_names_the_cut(self):
        # PR #180: the create-pull-request tool stored 128 characters, a line break and a marker that is cut
        # too; the type and the scope were right, so the hint of the format misled the CI doctor (#189)
        title = ("chore(process): issue-worker runs of managed issues call noop, a python clock for the 80% "
                 "rule, the ledger of t\n[Content truncat")
        self.assertEqual(len(title), 128)
        self.assertIsNone(changelog.parse(title))  # the rejection stays
        self.assertEqual(changelog.lint_subjects([title]), 1)
        r = self.run_lint(title)
        self.assertEqual(r.returncode, 1)
        self.assertIn("the title was cut: 128 characters, the cut after 111", r.stderr)
        self.assertIn("shorten the PR title", r.stderr)
        self.assertNotIn("Use <type>", r.stderr)

    def test_cut_marker_without_a_line_break_is_rejected_too(self):
        title = "fix(map): a day slider over the whole archive of [Content truncat"
        self.assertIsNotNone(changelog.parse(title))  # CC alone takes the marker for a description
        self.assertEqual(changelog.lint_subjects([title]), 1)

    def test_a_long_whole_title_passes(self):
        # 128 is a rule for agents, not a limit of the lint: a commit subject has none
        title = ("fix(changelog): the lint names a PR title that the tooling cut, with its length and "
                 "where the cut fell, and keeps rejecting it on the line break and on the marker")
        self.assertGreater(len(title), 128)
        self.assertEqual(changelog.lint_subjects([title]), 0)


class FullTimestamp(unittest.TestCase):
    """Releases and changes keep the full commit stamp: the Zmiany page shows HH:MM (#49)."""

    def commit(self, sha, date, subject):
        return {"sha": sha, "date": date, "subject": subject, "body": "", "cc": changelog.parse(subject)}

    def test_entry_keeps_the_full_stamp_next_to_the_day(self):
        e = changelog.entry(self.commit("a" * 40, "2026-11-21T21:32:05+01:00", "feat(map): slider"))
        self.assertEqual(e["date"], "2026-11-21")
        self.assertEqual(e["time"], "2026-11-21T21:32:05+01:00")

    def test_released_cut_carries_the_tagged_commit_stamp(self):
        first = self.commit("a" * 40, "2026-11-21T20:00:00+01:00", "feat: the map")
        tagged = self.commit("b" * 40, "2026-11-22T23:04:12+01:00", "fix(map): label")
        with mock.patch.object(changelog, "tags", return_value={tagged["sha"]: (1, 0, 0)}), \
                mock.patch.object(changelog, "commits", return_value=[first, tagged]):
            rels = changelog.releases()
        self.assertEqual(rels[0]["date"], "2026-11-22")
        self.assertEqual(rels[0]["time"], "2026-11-22T23:04:12+01:00")

    def test_unreleased_entry_carries_the_last_commit_stamp(self):
        pending = self.commit("c" * 40, "2026-11-23T06:12:00+01:00", "docs: readme")
        with mock.patch.object(changelog, "tags", return_value={}), \
                mock.patch.object(changelog, "commits", return_value=[pending]):
            rels = changelog.releases()
        self.assertIsNone(rels[0]["version"])
        self.assertEqual(rels[0]["date"], "2026-11-23")
        self.assertEqual(rels[0]["time"], "2026-11-23T06:12:00+01:00")


class NextVersion(unittest.TestCase):
    """next_version() cuts the unreleased commits against the last version tag."""

    def releases(self, pending, last="1.2.3"):
        rels = []
        if pending:
            rels.append({"version": None, "date": "2026-11-22", "sha": "f" * 40, "commits": pending})
        if last:
            rels.append({"version": last, "date": "2026-11-20", "sha": "e" * 40, "commits": []})
        return rels

    def next(self, pending, last="1.2.3"):
        with mock.patch.object(changelog, "releases", return_value=self.releases(pending, last)):
            return changelog.next_version()

    def test_fix_perf_and_feat(self):
        self.assertEqual(self.next([c("fix(map): label")]), "1.2.4")
        self.assertEqual(self.next([c("perf(parser): cache pages"), c("docs: readme")]), "1.2.4")
        self.assertEqual(self.next([c("fix: y"), c("feat(map): slider")]), "1.3.0")

    def test_breaking_asks_for_a_major(self):
        self.assertEqual(self.next([c("feat(site)!: new data format")]), "2.0.0")
        self.assertEqual(self.next([c("fix: x", "BREAKING CHANGE: alerts.json moved")]), "2.0.0")

    def test_nothing_releasable(self):
        self.assertIsNone(self.next([c("docs: readme"), c("chore(data): 2 active")]))
        self.assertIsNone(self.next([]))  # everything is tagged already

    def test_first_release(self):
        self.assertEqual(self.next([c("feat: the map")], last=None), "0.1.0")
        self.assertEqual(self.next([c("feat!: the map")], last=None), "1.0.0")


class LegacyMap(unittest.TestCase):
    """LEGACY maps prose commits (pre-convention, web editor) to Conventional subjects (#55, #57)."""

    def test_every_mapping_parses(self):
        for sha, subject in changelog.LEGACY.items():
            with self.subTest(sha=sha):
                self.assertIsNotNone(changelog.parse(subject), subject)

    def test_web_editor_prose_commit_becomes_ci(self):
        # 8253358 "Update dependabot configuration for weekly checks" reached main as prose and
        # failed the CI lint; commits() must read it through LEGACY as a non-releasing ci change.
        rec = ("8253358fd0a8e80dd42d6eef944638f3bf5c807a\x1f2026-11-23T11:40:00+01:00\x1f"
               "Update dependabot configuration for weekly checks\x1f\x1e")
        with mock.patch.object(changelog, "git", return_value=rec):
            items = changelog.commits()
        self.assertEqual(len(items), 1)
        cc = items[0]["cc"]
        self.assertEqual((cc["type"], cc["scope"]), ("ci", None))
        self.assertIsNone(changelog.level(items))  # a mapped ci/chore commit asks for no release


if __name__ == "__main__":
    unittest.main()
