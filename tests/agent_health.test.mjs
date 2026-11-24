// Node test of scripts/agent_health.cjs: one self-closing issue per failing agent workflow.
// Alone: node --test tests/agent_health.test.mjs ; CI runs every tests/*.test.mjs in its "Node tests" step.
import { createRequire } from "node:module";
import test from "node:test";
import assert from "node:assert/strict";

const require = createRequire(import.meta.url);
const H = require("../scripts/agent_health.cjs");

const WF = { id: 7, name: "Issue worker", path: ".github/workflows/issue-worker.lock.yml" };
let n = 100;
const run = (conclusion, at = "2026-11-24T10:05:00Z") => ({
  id: ++n, status: "completed", conclusion, event: "schedule", run_attempt: 1, created_at: at, updated_at: at,
  html_url: `https://example.test/runs/${n}`,
});
const job = (name, conclusion, steps = []) => ({
  name, conclusion, started_at: "2026-11-24T10:06:00Z", completed_at: "2026-11-24T10:38:00Z",
  steps: steps.map(([s, c]) => ({ name: s, conclusion: c })),
});
const crashed = [job("agent", "failure", [["Execute Claude Code CLI", "failure"]]), job("conclusion", "success")];
const parserOnly = [job("agent", "failure", [["Execute Claude Code CLI", "success"], ["Parse agent logs for step summary", "failure"]])];

function fakeGithub(runs, jobsById, issues = []) {
  const calls = [];
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: async () => ({ data: { workflow_runs: runs } }),
        listJobsForWorkflowRunAttempt: async ({ run_id }) => ({ data: { jobs: jobsById[run_id] || [] } }),
      },
      issues: {
        create: async (a) => { calls.push(["create", a]); return { data: { number: 200 } }; },
        update: async (a) => { calls.push(["update", a]); return { data: {} }; },
        createComment: async (a) => { calls.push(["comment", a]); return { data: {} }; },
      },
    },
  };
  return { calls, args: { github, owner: "o", repo: "r", workflow: WF, openIssues: issues, core: { info() {} } } };
}

test("a step-summary parser crash after the agent's work is not a failure", () => {
  assert.deepEqual(H.failedSteps(parserOnly), []);
  assert.deepEqual(H.failedSteps(crashed), ["agent / Execute Claude Code CLI"]);
});

test("a failed run opens one issue with the marker and both labels", async () => {
  const r = run("failure");
  const { calls, args } = fakeGithub([r, run("success", "2026-11-24T09:00:00Z")], { [r.id]: crashed });
  assert.equal(await H.reconcile(args), "opened #200");
  assert.equal(calls.length, 1);
  const [kind, a] = calls[0];
  assert.equal(kind, "create");
  assert.match(a.title, /^\[aw\] Issue worker: 1 failed run in a row/);
  assert.ok(a.body.includes(H.marker(WF.path)));
  assert.deepEqual(a.labels, ["agentic-workflows", "agent-health"]);
});

test("more failures rewrite the same issue instead of adding comments", async () => {
  const a1 = run("failure", "2026-11-24T10:00:00Z"), a2 = run("failure", "2026-11-24T09:00:00Z");
  const issue = { number: 95, title: "old", body: H.marker(WF.path) };
  const { calls, args } = fakeGithub([a1, run("cancelled"), a2], { [a1.id]: crashed, [a2.id]: crashed }, [issue]);
  assert.equal(await H.reconcile(args), "updated #95");
  assert.deepEqual(calls.map((c) => c[0]), ["update"]);
  assert.match(calls[0][1].title, /2 failed runs in a row/);
});

test("an unchanged streak leaves the issue alone", async () => {
  const a1 = run("failure");
  const { args } = fakeGithub([a1], { [a1.id]: crashed });
  const { streak } = await H.streakOf([a1], async () => crashed);
  args.openIssues = [{ number: 95, title: H.title(WF.name, streak), body: H.body(WF.name, WF.path, streak) }];
  assert.equal(await H.reconcile(args), "kept #95");
});

test("a success closes the open issue with one comment", async () => {
  const ok = run("success"), bad = run("failure", "2026-11-24T09:00:00Z");
  const { calls, args } = fakeGithub([ok, bad], { [bad.id]: crashed }, [{ number: 95, title: "x", body: H.marker(WF.path) }]);
  assert.equal(await H.reconcile(args), "closed #95");
  assert.deepEqual(calls.map((c) => c[0]), ["comment", "update"]);
  assert.equal(calls[1][1].state, "closed");
});

test("a run whose only failed step is the parser closes the issue too", async () => {
  const p = run("failure"), bad = run("failure", "2026-11-24T09:00:00Z");
  const { calls, args } = fakeGithub([p, bad], { [p.id]: parserOnly, [bad.id]: crashed }, [{ number: 95, title: "x", body: H.marker(WF.path) }]);
  assert.equal(await H.reconcile(args), "closed #95");
  assert.equal(calls.at(-1)[1].state, "closed");
});

test("issues of other workflows are not touched", async () => {
  const ok = run("success");
  const { calls, args } = fakeGithub([ok], {}, [{ number: 90, title: "x", body: H.marker(".github/workflows/pr-fixer.lock.yml") }]);
  assert.equal(await H.reconcile(args), "ok");
  assert.equal(calls.length, 0);
});

test("gh-aw's old failure issues and the detection tracker are retired, other notices stay", async () => {
  const issues = [
    { number: 84, state: "open", title: "[aw] Issue worker: engine driver crashed", body: "<!-- gh-aw-failure-issue: true, workflow_id: issue-worker, branch: main -->" },
    { number: 88, state: "open", title: "[aw] PR fixer: engine driver crashed", body: "<!-- gh-aw-failure-issue: true, workflow_id: pr-fixer, branch: main -->" },
    { number: 82, state: "open", title: "[aw] Detection Runs", body: "tracker" },
    { number: 8, state: "open", title: "[aw] No-Op Runs", body: "noop" },
    { number: 200, state: "open", title: "[aw] Issue worker: 1 failed run in a row", body: H.marker(".github/workflows/issue-worker.lock.yml") },
  ];
  const calls = [];
  const github = {
    paginate: async () => issues,
    rest: { issues: {
      listForRepo: () => {},
      createComment: async (a) => { calls.push(["comment", a]); },
      update: async (a) => { calls.push(["update", a]); },
    } },
  };
  const done = await H.retireLegacy({ github, owner: "o", repo: "r", core: { info() {} } });
  assert.deepEqual(done, ["closed legacy #84", "closed legacy #88", "closed legacy #82"]);
  const comment = (num) => calls.find((c) => c[0] === "comment" && c[1].issue_number === num)[1].body;
  assert.match(comment(84), /see #200/);
  assert.match(comment(88), /pass again/);
  assert.match(comment(82), /no longer grows/);
});
