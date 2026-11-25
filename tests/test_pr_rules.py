"""Tests of scripts/pr_rules.py: the AGENTS.md rules that code checks (CAS-393, 2026-11-25), and of
the places that run it (CI, the Agent PR gate) and of the parser contract the live service needs."""
import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import pr_rules as pr
import rcb

WF = ROOT / ".github" / "workflows"


class Repo:
    """A throwaway git repository: base commit, then a branch with the PR's change."""

    def __init__(self, base_files, head_files):
        self.dir = tempfile.TemporaryDirectory()
        self.path = self.dir.name
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        self.env = env
        self.run("init", "-q", "-b", "main")
        self.write(base_files)
        self.run("add", "-A")
        self.run("commit", "-qm", "base", "--allow-empty")
        self.run("checkout", "-qb", "pr")
        self.write(head_files)
        self.run("add", "-A")
        self.run("commit", "-qm", "change", "--allow-empty")

    def run(self, *args):
        return subprocess.run(["git", *args], cwd=self.path, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def write(self, files):
        for name, text in files.items():
            p = Path(self.path, name)
            if text is None:
                p.unlink()
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

    def check(self, **kw):
        cwd = os.getcwd()
        os.chdir(self.path)
        try:
            files = pr.parse_diff(pr.git("diff", "--no-renames", "-U0", "main...pr"))
            return pr.check(files, "main", "pr", **kw)
        finally:
            os.chdir(cwd)
            self.dir.cleanup()


RUFF = '[lint]\nselect = ["E4", "F", "B"]\nignore = ["E731"]\n'


class Suppressions(unittest.TestCase):
    def test_added_noqa_and_eslint_disable_fail(self):
        out = Repo({"scripts/a.py": "x = 1\n", "docs/a.js": "var a;\n"},
                   {"scripts/a.py": "import os  # noqa: F401\nx = 1\n",
                    "docs/a.js": "var a; // eslint-disable-line no-unused-vars\n"}).check()
        self.assertEqual(len(out), 2, out)
        self.assertTrue(all(o.startswith("suppression: ") for o in out))

    def test_other_inline_silencers_fail(self):
        for line in ("/* eslint no-undef: 0 */", "/* global foo */", "x = 1  # type: ignore",
                     "subprocess.call(c)  # nosec", "el.innerHTML = s; // codeql[js/xss]"):
            ext = "py" if "#" in line else "mjs"
            out = Repo({}, {f"tests/x.{ext}": line + "\n"}).check()
            self.assertEqual(len(out), 1, (line, out))

    def test_vendored_prose_and_query_tests_pass(self):
        out = Repo({}, {"dashboard/x.js": "// eslint-disable-next-line\n",
                        "docs/vendor/l.js": "/* eslint-disable */\n",
                        "codeql/javascript/test/Q/test.js": "// eslint-disable\n",
                        "AGENTS.md": "Never use noqa or eslint-disable.\n"}).check()
        self.assertEqual(out, [])

    def test_a_removed_noqa_is_fine(self):
        self.assertEqual(Repo({"scripts/a.py": "import os  # noqa\n"}, {"scripts/a.py": "import os\n"}).check(), [])


class LintConfigs(unittest.TestCase):
    def test_ruff_looser(self):
        self.assertEqual(pr.ruff_looser(RUFF, RUFF.replace('"B"', '"B", "UP"')), [])
        self.assertEqual(pr.ruff_looser(RUFF, RUFF.replace(', "B"', "")), ["takes B out of select"])
        self.assertEqual(pr.ruff_looser(RUFF, RUFF.replace('"E731"', '"E731", "B007"')), ["adds ignore:B007"])
        looser = RUFF + '\n[lint.per-file-ignores]\n"scripts/x.py" = ["F401"]\n'
        self.assertEqual(pr.ruff_looser(RUFF, looser), ["adds per-file-ignores:scripts/x.py:F401"])
        self.assertEqual(pr.ruff_looser('extend-exclude = ["a"]\n' + RUFF, 'extend-exclude = ["a", "scripts"]\n' + RUFF),
                         ["adds extend-exclude:scripts"])

    def test_ruff_in_a_pr(self):
        out = Repo({"ruff.toml": RUFF}, {"ruff.toml": RUFF.replace('"E731"', '"E731", "F401"')}).check()
        self.assertEqual(out, ["lint-config: ruff.toml adds ignore:F401"])
        self.assertEqual(Repo({"ruff.toml": RUFF}, {"ruff.toml": RUFF.replace('"B"', '"B", "SIM"')}).check(), [])

    def test_eslint_may_only_grow(self):
        base = 'export default [\n  js.configs.recommended,\n  { rules: { eqeqeq: "error" } },\n];\n'
        stricter = base.replace("];\n", '  { rules: { "no-var": "error" } },\n];\n')
        self.assertEqual(Repo({"eslint.config.mjs": base}, {"eslint.config.mjs": stricter}).check(), [])
        for looser in (base.replace('"error"', '"off"'), base.replace("  js.configs.recommended,\n", ""),
                       base.replace("[\n", '[\n  { ignores: ["scripts/**"] },\n'),
                       base.replace("[\n", '[\n  { rules: { "no-undef": "warn" } },\n')):
            out = Repo({"eslint.config.mjs": base}, {"eslint.config.mjs": looser}).check()
            self.assertTrue(out and all(o.startswith("lint-config: ") for o in out), (looser, out))

    def test_deleting_a_query_fails(self):
        q = "codeql/javascript/queries/Q.ql"
        out = Repo({q: "select 1\n"}, {q: None}).check()
        self.assertEqual(out, [f"lint-config: deletes {q}; a CodeQL query and its test stay"])


class FilesAndBody(unittest.TestCase):
    def test_generated_data(self):
        out = Repo({"docs/data/alerts.json": "[]\n"}, {"docs/data/alerts.json": "[1]\n"}).check()
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("generated-data: "))

    def test_parser_change_needs_a_test(self):
        out = Repo({"scripts/rcb.py": "A = 1\n"}, {"scripts/rcb.py": "A = 2\n"}).check()
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("parser-test: "))
        self.assertEqual(Repo({"scripts/rcb.py": "A = 1\n"},
                              {"scripts/rcb.py": "A = 2\n", "tests/test_rcb.py": "# case\n"}).check(), [])

    def test_ai_coauthor_in_body(self):
        files = {}
        self.assertEqual(pr.check(files, "", "", body="Fixes the map.\n"), [])
        for body in ("x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
                     "x\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"):
            out = pr.check(files, "", "", body=body)
            self.assertEqual(len(out), 1, body)
            self.assertTrue(out[0].startswith("ai-coauthor: "))
        self.assertEqual(pr.check(files, "", "", body="Co-authored-by: Taras <t@k>\n"), [])

    def test_process_issues_and_one_issue(self):
        closes = [{"number": 96, "labels": ["agent-health"]}, {"number": 7, "labels": ["bug"]}]
        out = pr.check({}, "", "", closes=closes)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("process-issue: closes #96"))
        out = pr.check({}, "", "", workflow="issue-worker", closes=closes[1:] * 2)
        self.assertTrue(out[0].startswith("one-issue: "))
        self.assertEqual(pr.check({}, "", "", workflow="site-fixer", closes=closes[1:] * 2), [])

    def test_commits_and_squash_body(self):
        log = "a" * 40 + "\x1ffix: x\n\nCo-authored-by: Claude Code <c@a>\n\x1e" + "b" * 40 + "\x1ffix: y\n\x1e"
        self.assertEqual(pr.commit_problems(log), ["ai-coauthor: commit aaaaaaaaa has «Co-authored-by: Claude Code <c@a>»"])
        text = "* fix: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\nGenerated with Claude Code\nkeep\n"
        self.assertEqual(pr.squash_body(text), "* fix: x\n\nkeep\n")


class Wiring(unittest.TestCase):
    """The checks run where AGENTS.md says they do."""

    def test_ci_runs_the_rules_and_strict_linters(self):
        ci = (WF / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/pr_rules.py check", ci)
        self.assertIn("scripts/pr_rules.py commits", ci)
        self.assertIn("check --ignore-noqa", ci)

    def test_gate_runs_main_copy_and_protects_it(self):
        gate = (WF / "agent-pr-gate.yml").read_text(encoding="utf-8")
        before_checkout = gate.split('gh pr checkout "$n"')[0]
        self.assertIn("scripts/pr_rules.py check", before_checkout)
        self.assertIn("scripts/pr_rules.py squash-body", gate)
        self.assertIn("--ignore-noqa", gate)
        self.assertRegex(gate, r"PROTECTED: .*pr_rules")

    def test_eslint_ignores_inline_config(self):
        self.assertRegex((ROOT / "eslint.config.mjs").read_text(encoding="utf-8"), r"noInlineConfig:\s*true")


class ParserContract(unittest.TestCase):
    """The live service (server/) imports the parser: AGENTS.md said «keep these working»."""

    def test_every_name_the_service_uses_exists(self):
        tree = ast.parse((ROOT / "server" / "app.py").read_text(encoding="utf-8"))
        used = {n.attr for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "rcb"}
        self.assertGreaterEqual(used, {"parse_list", "build_alert", "fetch", "LIST_URL", "Gazetteer", "PARSER_VERSION"})
        self.assertEqual(sorted(u for u in used if not hasattr(rcb, u)), [])

    def test_alert_categories_are_fixed(self):
        cats = {c for c, _ in rcb.CATEGORIES} | {"other"}
        self.assertEqual(cats, {"air", "drill", "water", "weather", "ordnance", "fire", "chemical", "other"})
        self.assertEqual(set(rcb.TTL), cats)


if __name__ == "__main__":
    unittest.main()
