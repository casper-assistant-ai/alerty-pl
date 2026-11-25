import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import security_alerts as sa


class SecurityAlertsTest(unittest.TestCase):
    def test_secret_value_is_never_kept(self):
        rec = sa.from_secret_scanning({"number": 3, "secret": "ghp_abcdef", "secret_type": "github_personal_access_token",
                                       "secret_type_display_name": "GitHub PAT", "html_url": "u"})
        self.assertNotIn("ghp_abcdef", repr(rec))
        self.assertEqual(rec["kind"], "secret-scanning")

    def test_code_scanning_shape(self):
        rec = sa.from_code_scanning({"number": 1, "rule": {"id": "js/x", "severity": "warning",
                                                           "security_severity_level": "medium", "tags": ["security"]},
                                     "tool": {"name": "CodeQL"},
                                     "most_recent_instance": {"location": {"path": "a.js", "start_line": 5},
                                                              "message": {"text": "m"}}})
        self.assertEqual((rec["path"], rec["line"], rec["severity"]), ("a.js", 5, "medium"))

    def test_covered_refs_and_pending(self):
        refs = sa.covered_refs([
            {"number": 12, "is_pr": True, "body": "Fix.\n\nAlerts: code-scanning#1, dependabot#4\n"},
            {"number": 13, "body": "Alert: secret-scanning#2"},
            {"number": 14, "body": "mentions code-scanning#9 in prose only"},
        ])
        self.assertEqual(refs, {"code-scanning#1": "PR #12", "dependabot#4": "PR #12", "secret-scanning#2": "issue #13"})
        alerts = [{"kind": "code-scanning", "number": 1}, {"kind": "code-scanning", "number": 9}]
        self.assertEqual([a["number"] for a in sa.mark_pending(alerts, refs)], [9])

    def test_dismissal_reasons(self):
        self.assertEqual(sa.check_dismissal("code-scanning", "false_positive", "x" * 30)[0], "false positive")
        self.assertEqual(sa.check_dismissal("dependabot", "not_used", "x" * 30)[0], "not_used")
        self.assertEqual(sa.check_dismissal("secret-scanning", "used_in_tests", "x" * 30)[0], "used_in_tests")
        with self.assertRaises(ValueError):
            sa.check_dismissal("secret-scanning", "tolerable_risk", "x" * 30)   # a live secret is never "fine"
        with self.assertRaises(ValueError):
            sa.check_dismissal("code-scanning", "revoked", "x" * 30)
        with self.assertRaises(ValueError):
            sa.check_dismissal("code-quality", "false_positive", "x" * 30)
        with self.assertRaises(ValueError):
            sa.check_dismissal("code-scanning", "false_positive", "too short")
        self.assertEqual(len(sa.check_dismissal("code-scanning", "false_positive", "y" * 500)[1]), sa.COMMENT_MAX)

    def test_flows_from_sarif(self):
        sarif = {"runs": [{"results": [{
            "ruleId": "js/x",
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": "a.js"}, "region": {"startLine": 5}}}],
            "codeFlows": [{"threadFlows": [{"locations": [
                {"location": {"physicalLocation": {"artifactLocation": {"uri": "b.js"}, "region": {"startLine": 2}},
                              "message": {"text": "error"}}}]}]}]}]}]}
        self.assertEqual(sa.flows_by_location(sarif), {("js/x", "a.js", 5): [["b.js:2 error"]]})

    def test_markdown_lists_unreadable_kinds(self):
        md = sa.to_markdown({"repo": "o/r", "unreadable": {"dependabot": "HTTP 403: no"},
                             "alerts": [{"kind": "code-scanning", "number": 1, "rule": "js/x", "path": "a.js",
                                         "line": 5, "covered_by": "PR #2"}]})
        self.assertIn("dependabot: not readable", md)
        self.assertIn("covered by PR #2", md)
        self.assertIn("1 open, 0 not covered", md)


if __name__ == "__main__":
    unittest.main()
