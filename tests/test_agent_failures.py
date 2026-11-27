import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import agent_failures as af

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
# The quota (429 [1308]) as z.ai answered pr-fixer 45589262864 on 25.11.2026: the code is away from the colon,
# and the JSON line keeps the «·» before it as an escape.
QUOTA_LOG = (
    '2026-11-25T19:27:44.96Z {"type":"assistant","message":{"model":"<synthetic>","content":[{"type":"text",'
    '"text":"API Error: Request rejected (429) \\u00b7 [1308][Usage limit reached for 5 hour. Your limit will '
    'reset at 2026-11-26 04:01:55][20261126032744a932d41421574474]"}]},"error":"rate_limit",'
    '"is_api_error_message":true,"api_error_status":429}\n'
    '2026-11-25T19:29:26.40Z {"type":"result","subtype":"success","is_error":true,"terminal_reason":"api_error",'
    '"api_error_status":429,"result":"API Error: Request rejected (429) \\u00b7 [1308][Usage limit reached for 5 hour. '
    'Your limit will reset at 2026-11-26 04:01:55][202611260329256bddf080d53c40cc]"}\n'
    '2026-11-25T19:30:35.27Z ##[error]Agent execution exited with code 1\n'
)
# A result record whose text carries an astral character (a surrogate pair in JSON) and one that echoed a
# terminal escape (a control character, as an escape): the record is parsed undecoded.
EMOJI_LOG = ('2026-11-24T05:06:51.1Z {"type":"result","subtype":"success","is_error":true,"num_turns":1,'
             '"result":"Fixed \\ud83d\\ude00 in the table"}\n')
ESC_LOG = ('2026-11-24T05:06:51.1Z {"type":"result","subtype":"success","is_error":true,"num_turns":1,'
           '"result":"done, then \\u001b[2Kbefore the end"}\n')


def job(name, conclusion, steps=(), start="2026-11-24T10:00:00Z", end="2026-11-24T10:10:00Z"):
    return {"name": name, "conclusion": conclusion, "started_at": start, "completed_at": end,
            "steps": [{"name": s[0], "conclusion": s[1],
                       **({"started_at": s[2], "completed_at": s[3]} if len(s) > 2 else {})} for s in steps]}


def run(i, conclusion, jobs, at="2026-11-24T10:00:00Z", signals=None):
    r = {"id": i, "status": "completed", "conclusion": conclusion, "created_at": at, "event": "schedule",
         "html_url": f"https://example.test/runs/{i}", "jobs": jobs}
    if signals is not None:
        r["signals"] = signals
    return r


CRASH = [job("agent", "failure", [("Execute Claude Code CLI", "failure")])]
PARSER_ONLY = [job("agent", "failure", [("Execute Claude Code CLI", "success"),
                                        ("Parse agent logs for step summary", "failure")])]
MIRROR = [job("conclusion", "failure", [("Handle agent failure", "failure")])]
# The jobs of two real runs, as GitHub's jobs API gives them (24.11.2026).
# Site fixer 45248741714: the CLI step stopped at the step limit after 25m12s of 25 minutes, conclusion `failure`.
STEP_LIMIT = [job("agent", "failure", [("Execute Claude Code CLI", "failure", "2026-11-23T19:36:47Z", "2026-11-23T20:01:59Z"),
                                       ("Parse agent logs for step summary", "failure", "2026-11-23T20:02:19Z", "2026-11-23T20:02:33Z")],
                  start="2026-11-23T19:35:54Z", end="2026-11-23T20:02:42Z"),
              job("conclusion", "success", [])]
# Parser doctor 45288784687: the agent job was green, only the conclusion job's handler failed.
HANDLER_ONLY = [job("agent", "success", [("Execute Claude Code CLI", "success", "2026-11-23T23:28:08Z", "2026-11-23T23:35:14Z")],
                    start="2026-11-23T23:27:07Z", end="2026-11-23T23:35:34Z"),
                job("conclusion", "failure", [("Handle agent failure", "failure", "2026-11-23T23:38:11Z", "2026-11-23T23:38:15Z")],
                    start="2026-11-23T23:38:00Z", end="2026-11-23T23:38:27Z")]


class Signals(unittest.TestCase):
    def test_timeout_log(self):
        lines = af.signal_lines(TIMEOUT_LOG)
        self.assertEqual(lines, ["The action 'Execute Claude Code CLI' has timed out after 30 minutes."])
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"], lines), "timeout")

    def test_every_escape_and_control_sequence_is_stripped(self):
        # erase-line, colour, an OSC title, a charset select, NUL, bell, backspace; a tab stays
        log = ("2026-11-24T10:00:00.1Z ##[error]\x1b[2KAgent \x1b[1;31mfailed\x1b[0m\x1b]0;title\x07\x1b(B\x00\x07\x08x\n"
               "2026-11-24T10:00:01Z \x1b[36mplain\x1b[0m line\x7f\n")
        self.assertEqual(af.signal_lines(log), ["Agent failedx"])

    def test_gh_aw_config_noise_is_not_a_signal(self):
        # the whole log names "rate_limit_error" in gh-aw's outputs; only the signal lines count
        self.assertNotEqual(af.classify([], af.signal_lines(TIMEOUT_LOG)), "provider-overload")

    def test_overload_folds_request_ids(self):
        lines = af.signal_lines(OVERLOAD_LOG)
        api = [l for l in lines if l.startswith("API Error")]
        self.assertEqual(len(api), 1, lines)
        self.assertTrue(any(l.startswith("result: ") for l in lines))
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"], lines), "provider-overload")

    def test_quota_1308_is_provider_overload(self):
        # 20 runs of the seven days to 27.11.2026 read `engine-crash`: the code does not follow the colon
        lines = af.signal_lines(QUOTA_LOG)
        self.assertEqual(lines[0], "API Error: Request rejected (429) · [1308][Usage limit reached for 5 hour. "
                                   "Your limit will reset at 2026-11-26 04:01:55][…]")    # the reset time stays
        self.assertEqual(lines[2], "Agent execution exited with code 1")
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"], lines), "provider-overload")
        rate = "API Error: Request rejected (429) · [1302][Rate limit reached for requests][…]"
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"], [rate, lines[2]]), "provider-overload")
        # a 400 that ends the CLI is no overload
        bad = "API Error: 400 invalid_request_error: messages.0: field required"
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"], [bad, lines[2]]), "engine-crash")

    def test_result_record_with_an_emoji_still_parses(self):
        # decoded half by half, the pair is two lone surrogates and the report could not be written as UTF-8
        lines = af.signal_lines(EMOJI_LOG)
        want = "result: subtype=success is_error=True turns=1 terminal_reason=None Fixed 😀 in the table"
        self.assertEqual("\n".join(lines).encode("utf-8"), want.encode("utf-8"))    # json.loads folds the pair
        self.assertEqual(lines, [want])

    def test_result_record_with_an_escaped_escape_stays(self):
        # strict json.loads refuses a decoded control character: the record must still give its result line
        lines = af.signal_lines(ESC_LOG)
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("result: subtype=success is_error=True turns=1 terminal_reason=None done, then "))
        self.assertTrue(lines[0].endswith("before the end"))

    def test_step_names_classify_without_a_log(self):
        self.assertEqual(af.classify(["safe_outputs / Process Safe Outputs"]), "safe-outputs")
        self.assertEqual(af.classify(["agent (timed_out)"]), "timeout")
        self.assertEqual(af.classify(["agent / Execute Claude Code CLI"]), "unknown")


class Steps(unittest.TestCase):
    def test_parser_crash_is_not_a_failure(self):
        self.assertEqual(af.failed_steps(PARSER_ONLY), [])
        self.assertEqual(af.failed_steps(CRASH), ["agent / Execute Claude Code CLI"])

    def test_handler_mirror_is_dropped_when_the_agent_job_did_not_fail(self):
        self.assertEqual(af.failed_steps(PARSER_ONLY + MIRROR), [])
        self.assertEqual(af.failed_steps(HANDLER_ONLY), [])
        self.assertEqual(af.failed_steps(CRASH + MIRROR),
                         ["agent / Execute Claude Code CLI", "conclusion / Handle agent failure"])
        self.assertEqual(af.failed_steps(MIRROR), ["conclusion / Handle agent failure"])

    def test_cli_step_at_the_step_limit_is_a_timeout(self):
        steps = af.failed_steps(STEP_LIMIT, 25)
        self.assertEqual(steps, ["agent / Execute Claude Code CLI (timeout)"])
        self.assertEqual(af.classify(steps), "timeout")
        self.assertEqual(af.failed_steps(STEP_LIMIT), ["agent / Execute Claude Code CLI"])
        self.assertEqual(af.failed_steps(STEP_LIMIT, 60), ["agent / Execute Claude Code CLI"])

        def cli(minutes, seconds, conclusion="failure"):
            end = dt.datetime(2026, 11, 24, 10) + dt.timedelta(minutes=minutes, seconds=seconds)
            return [job("agent", "failure", [("Execute Claude Code CLI", conclusion, "2026-11-24T10:00:00Z",
                                              end.strftime("%Y-%m-%dT%H:%M:%SZ"))])]
        self.assertEqual(af.failed_steps(cli(23, 45), 25), ["agent / Execute Claude Code CLI (timeout)"])   # 95% sharp
        self.assertEqual(af.failed_steps(cli(23, 40), 25), ["agent / Execute Claude Code CLI"])
        self.assertEqual(af.failed_steps(cli(3, 0), 25), ["agent / Execute Claude Code CLI"])
        self.assertEqual(af.failed_steps(cli(25, 0, "timed_out"), 25), ["agent / Execute Claude Code CLI (timed_out)"])

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

    def test_step_limit_is_a_timeout_without_a_log(self):
        # site-fixer 45248741714: no log read, the step's 25m12s of 25 minutes name the signature
        rep = self.rep([run(1, "failure", STEP_LIMIT, at="2026-11-23T19:35:00Z")], timeout=25)
        f = rep["failures"][0]
        self.assertEqual((f["signature"], f["steps"]), ("timeout", ["agent / Execute Claude Code CLI (timeout)"]))
        self.assertEqual(rep["signatures"][0]["known"], False)
        self.assertIn("Execute Claude Code CLI (timeout)", af.markdown(rep))

    def test_handler_mirror_alone_is_not_a_failure(self):
        runs = [run(1, "success", [job("agent", "success")]),
                run(2, "failure", PARSER_ONLY + MIRROR),
                run(3, "failure", HANDLER_ONLY, at="2026-11-23T23:26:00Z")]
        rep = self.rep(runs)
        self.assertEqual((rep["agents"][0]["ok"], rep["agents"][0]["failed"]), (3, 0))
        self.assertEqual((rep["failures"], rep["signatures"]), ([], []))


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
