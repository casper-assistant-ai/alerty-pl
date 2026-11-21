import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import changelog  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
