import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import agent_failures as af  # noqa: E402

# Lines as they stand in real gh-aw v1.2.2 agent job logs of this repository (24.11.2026).
TIMEOUT_LOG = """2026-11-24T10:37:43.4632609Z {"type":"system","subtype":"thinking_tokens","estimated_tokens":3171}
2026-11-24T10:37:43.7999968Z ##[error]The action 'Execute Claude Code CLI' has timed out after 30 minutes.
2026-11-24T10:38:01.0510167Z ##[error]ERR_API: Maximum call stack size exceeded
2026-11-24T10:38:05.8852935Z Set output 'ai_credits_rate_limit_error'
"""
OVERLOAD_LOG = """2026-11-24T05:06:51.1Z {"type":"result","subtype":"success","is_error":true,"num_turns":1,"result":"API Error: 529 [1305][The service may be temporarily overloaded, please try again later][202611241306501fb03f8bfc3c428e]. This is a server-side issue"}
2026-11-24T05:06:57.6Z {"type":"assistant","message":"API Error: 529 [1305][The service may be temporarily overloaded, please try again later][20261124130657d6d1b2b00ed94dca]. This is a server-side issue"}
2026-11-24T05:07:00.5374996Z ##[error]Agent execution exited with code 1
2026-11-24T05:07:00.5385095Z ##[error]Process completed with exit code 1.
"""


def job(name, conclusion, steps=(), start="2026-11-24T10:00:00Z", end="2026-11-24T10:10:00Z"):
    return {"name": name, "conclusion": conclusion, "started_at": start, "completed_at": end,
            "steps": [{"name": s, "conclusion": c} for s, c in steps]}


def run(i, conclusion, jobs, at="2026-11-24T10:00:00Z", signals=None):
    r = {"id": i, "status": "completed", "conclusion": conclusion, "created_at": at, "event": "schedule",
         "html_url": f"https://example.test/runs/{i}", "jobs": jobs}
    if signals is not None:
        r["signals"] = signals
    return r


CRASH = [job("agent", "failure", [("Execute Claude Code CLI", "failure")])]
PARSER_ONLY = [job("agent", "failure", [("Execute Claude Code CLI", "success"),
                                        ("Parse agent logs for step summary", "failure")])]


class Signals(unittest.TestCase):
    def test_timeout_log(self):
        lines = af.signal_lines(TIMEOUT_LOG)
        self.assertEqual(lines, ["The action 'Execute Claude Code CLI' has timed out after 30 minutes."])
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"], lines), "timeout")

    def test_gh_aw_config_noise_is_not_a_signal(self):
        # the whole log names "rate_limit_error" in gh-aw's outputs; only the signal lines count
        self.assertNotEqual(af.classify([], af.signal_lines(TIMEOUT_LOG)), "provider-overload")

    def test_overload_folds_request_ids(self):
        lines = af.signal_lines(OVERLOAD_LOG)
        api = [l for l in lines if l.startswith("API Error")]
        self.assertEqual(len(api), 1, lines)
        self.assertTrue(any(l.startswith("result: ") for l in lines))
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"], lines), "provider-overload")

    def test_step_names_classify_without_a_log(self):
        self.assertEqual(af.classify(["safe_outputs / Process Safe Outputs"]), "safe-outputs")
        self.assertEqual(af.classify(["agent (timed_out)"]), "timeout")
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"]), "unknown")


class Steps(unittest.TestCase):
    def test_parser_crash_is_not_a_failure(self):
        self.assertEqual(af.failed_steps(PARSER_ONLY), [])
        self.assertEqual(af.failed_steps(CRASH), ["agent / Execute Claude Code CLI"])

    def test_timeout_of_frontmatter(self):
        self.assertEqual(af.timeout_of("---\non:\n  schedule: x\ntimeout-minutes: 50\n---"), 50)
        self.assertEqual(af.timeout_of("---\non: x\n---"), 20)

    def test_known_patterns(self):
        text = "| Signature | Agents |\n| --- | --- |\n| `timeout` | Issue worker |\n| provider-overload | all |\n"
        self.assertEqual(af.known_patterns(text), {"timeout", "provider-overload"})


class Summary(unittest.TestCase):
    def rep(self, runs, timeout=20, patterns=()):
        wf = {"name": "Issue worker", "file": "issue-worker.md", "timeout": timeout, "runs": runs}
        issues = [{"number": 96, "title": "[aw] Issue worker: 2 failed runs in a row",
                   "labels": ["agentic-workflows", "agent-health"], "doctor_commented": False}]
        return af.summarize([wf], issues, set(patterns), "2026-11-24T12:00:00Z", 7)

    def test_recurring_needs_runs_on_two_days(self):
        same_day = [run(i, "failure", CRASH, signals=["Agent execution exited with code 1"]) for i in range(3)]
        rep = self.rep(same_day)
        self.assertEqual(rep["signatures"][0]["signature"], "engine-crash")
        self.assertFalse(rep["signatures"][0]["recurring"])
        two_days = same_day + [run(9, "failure", CRASH, at="2026-11-23T08:00:00Z", signals=["exited with code 1"])]
        self.assertTrue(self.rep(two_days)["signatures"][0]["recurring"])

    def test_unread_runs_never_recur(self):
        runs = [run(i, "failure", CRASH, at=f"2026-11-2{i}T08:00:00Z") for i in range(1, 5)]
        s = self.rep(runs)["signatures"][0]
        self.assertEqual((s["signature"], s["recurring"]), ("unread", False))

    def test_counts_near_timeout_and_known(self):
        long_ok = run(1, "success", [job("agent", "success", start="2026-11-24T10:00:00Z", end="2026-11-24T10:18:00Z")])
        timed = run(2, "failure", CRASH, signals=["The action 'Execute Claude Code CLI' has timed out after 20 minutes."])
        parser = run(3, "failure", PARSER_ONLY)
        rep = self.rep([long_ok, timed, parser], timeout=20, patterns={"timeout"})
        a = rep["agents"][0]
        self.assertEqual((a["ok"], a["failed"], a["near_timeout"]), (2, 1, True))
        self.assertEqual(rep["signatures"][0]["signature"], "timeout")
        self.assertTrue(rep["signatures"][0]["known"])
        md = af.markdown(rep)
        self.assertIn("#96", md)
        self.assertIn("timed out after 20 minutes", md)


class Gh(unittest.TestCase):
    class Done:
        def __init__(self, code, out="", err=""):
            self.returncode, self.stdout, self.stderr = code, out, err

    def test_logs_are_read_with_escape_sequences_allowed(self):
        calls = []
        def run(cmd, **kw):
            calls.append(cmd)
            return self.Done(0, "\x1b[36mlog\x1b[0m")
        self.assertIn("log", af.gh("repos/o/r/actions/jobs/1/logs", raw=True, run=run))
        self.assertIn(af.ESCAPES, calls[0])

    def test_old_gh_without_the_flag_retries_plain(self):
        calls = []
        def run(cmd, **kw):
            calls.append(cmd)
            if af.ESCAPES in cmd:
                return self.Done(1, err="unknown flag: --allow-escape-sequences")
            return self.Done(0, "log")
        self.assertEqual(af.gh("x/logs", raw=True, run=run), "log")
        self.assertEqual(len(calls), 2)
        self.assertNotIn(af.ESCAPES, calls[1])

    def test_json_calls_do_not_take_the_flag(self):
        calls = []
        def run(cmd, **kw):
            calls.append(cmd)
            return self.Done(0, '{"a": 1}')
        self.assertEqual(af.gh("x", run=run), {"a": 1})
        self.assertNotIn(af.ESCAPES, calls[0])


if __name__ == "__main__":
    unittest.main()
