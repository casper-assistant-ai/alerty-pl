import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import agent_retry as ar  # noqa: E402

UTC = dt.timezone.utc
# Claude Code's own records from issue-worker run 45684338261 (2026-11-25, the 5-hour quota of z.ai),
# shortened; the API log of a job has the timestamp, `gh run view --log` adds "job<TAB>step<TAB>".
QUOTA_LOG = (
    '2026-11-25T19:24:01.96Z {"type":"user","message":{"content":[{"type":"tool_result","content":"[1308][Usage limit '
    'reached for 5 hour. Your limit will reset at 2026-11-25 10:00:00] quoted from AGENTS.md"}]}}\n'
    'agent\tExecute Claude Code CLI\t2026-11-25T19:27:44.96Z {"type":"assistant","message":{"model":"<synthetic>",'
    '"content":[{"type":"text","text":"API Error: Request rejected (429) \\u00b7 [1308][Usage limit reached for 5 hour. '
    'Your limit will reset at 2026-11-26 04:01:55][20261126032744a932d41421574474]"}]},"error":"rate_limit",'
    '"is_api_error_message":true,"api_error_status":429}\n'
    '2026-11-25T19:29:26.40Z {"type":"result","subtype":"success","is_error":true,"terminal_reason":"api_error",'
    '"api_error_status":429,"result":"API Error: Request rejected (429) \\u00b7 [1308][Usage limit reached for 5 hour. '
    'Your limit will reset at 2026-11-26 04:01:55][202611260329256bddf080d53c40cc]"}\n'
    '2026-11-25T19:30:35.27Z ##[error]Agent execution exited with code 1\n'
)
# An older Claude Code result record (no terminal_reason), from test_agent_failures.py.
OVERLOAD_LOG = (
    '2026-11-24T05:06:51.1Z {"type":"result","subtype":"success","is_error":true,"num_turns":1,"result":"API Error: 529 '
    '[1305][The service may be temporarily overloaded, please try again later][202611241306501fb03f8bfc3c428e]. '
    'This is a server-side issue"}\n'
)
# The session quoted an API error but ended normally (a later turn limit is not a provider limit).
QUOTED_ONLY_LOG = (
    '2026-11-24T05:00:00Z {"type":"user","message":{"content":[{"type":"tool_result","content":"API Error: 529 [1305]"}]}}\n'
    '2026-11-24T05:10:00Z {"type":"result","subtype":"error_max_turns","is_error":true,"result":"max turns"}\n'
)
PR_SENT_LOG = OVERLOAD_LOG + (
    '2026-11-24T05:05:00Z {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1",'
    '"name":"mcp__safeoutputs__create_pull_request","input":{}}]}}\n'
)
COMMENT_SENT_LOG = OVERLOAD_LOG + (
    '2026-11-24T05:05:00Z {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1",'
    '"name":"mcp__safeoutputs__add_comment","input":{}}]}}\n'
)

AGENT_FAILED = [{"name": "agent", "conclusion": "failure", "steps": [{"name": "Execute Claude Code CLI", "conclusion": "failure"}]},
                {"name": "conclusion", "conclusion": "failure", "steps": [{"name": "Handle agent failure", "conclusion": "failure"}]}]
PARSER_ONLY = [{"name": "agent", "conclusion": "failure", "steps": [{"name": "Parse agent logs for step summary", "conclusion": "failure"}]}]


def run(i, at, conclusion="failure", status="completed", event="schedule", attempt=1, title="Issue worker", ended=None):
    return {"id": i, "created_at": at, "updated_at": ended or at, "status": status, "conclusion": conclusion,
            "event": event, "run_attempt": attempt, "display_title": title, "html_url": f"https://example.test/{i}"}


class ApiError(unittest.TestCase):
    def test_quota_with_reset_in_beijing_time(self):
        e = ar.api_error(QUOTA_LOG)
        self.assertEqual((e["status"], e["code"]), (429, "1308"))
        self.assertEqual(e["reset"].astimezone(UTC), dt.datetime(2026, 11, 25, 20, 1, 55, tzinfo=UTC))

    def test_old_result_record_without_terminal_reason(self):
        e = ar.api_error(OVERLOAD_LOG)
        self.assertEqual((e["status"], e["code"], e["reset"]), (529, "1305", None))

    def test_quoted_errors_do_not_count(self):
        self.assertIsNone(ar.api_error(QUOTED_ONLY_LOG))
        self.assertIsNone(ar.api_error(""))

    def test_session_that_went_on_after_an_error(self):
        ok = '2026-11-24T05:20:00Z {"type":"result","subtype":"success","is_error":false,"result":"done"}\n'
        self.assertIsNone(ar.api_error(OVERLOAD_LOG + ok))

    def test_other_status_is_not_a_limit(self):
        log = '2026-11-24T05:00:00Z {"type":"result","is_error":true,"terminal_reason":"api_error","api_error_status":401,"result":"API Error: 401"}\n'
        self.assertIsNone(ar.api_error(log))


class Outputs(unittest.TestCase):
    def test_sent_and_harmless(self):
        self.assertEqual(ar.sent_outputs(PR_SENT_LOG), ["create_pull_request"])
        self.assertEqual(ar.sent_outputs(COMMENT_SENT_LOG), [])
        self.assertEqual(ar.sent_outputs(QUOTA_LOG), [])


class Decide(unittest.TestCase):
    def setUp(self):
        self.failed = run(1, "2026-11-25T19:21:11Z", ended="2026-11-25T19:33:30Z")

    def test_quota_waits_for_the_reset_then_retries(self):
        v, why, due = ar.decide(self.failed, [self.failed], AGENT_FAILED, QUOTA_LOG, dt.datetime(2026, 11, 25, 19, 40, tzinfo=UTC))
        self.assertEqual((v, due), ("wait", dt.datetime(2026, 11, 25, 20, 2, 55, tzinfo=UTC)))
        self.assertIn("[1308]", why)
        v, _, _ = ar.decide(self.failed, [self.failed], AGENT_FAILED, QUOTA_LOG, dt.datetime(2026, 11, 25, 20, 3, tzinfo=UTC))
        self.assertEqual(v, "retry")

    def test_overload_retries_ten_minutes_after_the_failure(self):
        now = dt.datetime(2026, 11, 25, 19, 40, tzinfo=UTC)
        v, _, due = ar.decide(self.failed, [self.failed], AGENT_FAILED, OVERLOAD_LOG, now)
        self.assertEqual((v, due), ("wait", dt.datetime(2026, 11, 25, 19, 43, 30, tzinfo=UTC)))
        self.assertEqual(ar.decide(self.failed, [self.failed], AGENT_FAILED, OVERLOAD_LOG, now + dt.timedelta(minutes=5))[0], "retry")

    def test_skips(self):
        now = dt.datetime(2026, 11, 25, 21, 0, tzinfo=UTC)
        self.assertEqual(ar.decide(self.failed, [self.failed], PARSER_ONLY, QUOTA_LOG, now)[0], "skip")
        self.assertEqual(ar.decide(self.failed, [self.failed], AGENT_FAILED, QUOTED_ONLY_LOG, now)[0], "skip")
        v, why, _ = ar.decide(self.failed, [self.failed], AGENT_FAILED, PR_SENT_LOG, now)
        self.assertEqual(v, "skip")
        self.assertIn("create_pull_request", why)
        self.assertEqual(ar.decide(self.failed, [self.failed], AGENT_FAILED, COMMENT_SENT_LOG, now)[0], "retry")

    def test_a_newer_run_for_the_same_work_supersedes_it(self):
        now = dt.datetime(2026, 11, 25, 21, 0, tzinfo=UTC)
        manual = run(2, "2026-11-25T19:57:04Z", conclusion=None, status="in_progress", event="workflow_dispatch")
        v, why, _ = ar.decide(self.failed, [manual, self.failed], AGENT_FAILED, QUOTA_LOG, now)
        self.assertEqual((v, why), ("skip", "run 2 came after it"))
        # a newer failed run, or one for another issue, does not
        other = run(3, "2026-11-25T19:50:00Z", event="issues", title="Fix #150", conclusion="success")
        again = run(4, "2026-11-25T19:55:00Z")
        self.assertEqual(ar.decide(self.failed, [again, other, self.failed], AGENT_FAILED, QUOTA_LOG, now)[0], "retry")


class Candidates(unittest.TestCase):
    def test_only_recent_failed_runs_with_attempts_left(self):
        now = dt.datetime(2026, 11, 25, 21, 0, tzinfo=UTC)
        runs = [run(1, "2026-11-25T20:00:00Z"), run(2, "2026-11-25T20:00:00Z", attempt=3),
                run(3, "2026-11-25T20:00:00Z", conclusion="success"), run(4, "2026-11-25T05:00:00Z"),
                run(5, "2026-11-25T20:00:00Z", conclusion="cancelled"), run(6, "2026-11-25T20:30:00Z", attempt=2)]
        self.assertEqual([r["id"] for r in ar.candidates(runs, now, 12)], [1, 6])


if __name__ == "__main__":
    unittest.main()
