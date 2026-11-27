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
// pr-fixer 45835195530: the agent job passed (its `no fix` went out) and only the handler step failed.
const handlerOnly = [job("agent", "success", [["Execute Claude Code CLI", "success"]]), job("conclusion", "failure", [["Handle agent failure", "failure"]])];
// A run as GitHub lists it: no jobs, and no conclusion while it is not completed.
const listed = (id, status, conclusion, run_attempt, at) => ({ id, status, conclusion, run_attempt, event: "schedule", created_at: at, updated_at: at, html_url: `https://example.test/runs/${id}` });

// runs: the completed runs; going: the in-progress ones. jobsById: by run id, or by "run id/attempt".
function fakeGithub(runs, jobsById, issues = [], going = []) {
  const calls = [];
  const github = {
    rest: {
      actions: {
        listWorkflowRuns: async ({ status }) => ({ data: { workflow_runs: status === "completed" ? runs : status === "in_progress" ? going : [] } }),
        listJobsForWorkflowRunAttempt: async ({ run_id, attempt_number }) => ({ data: { jobs: jobsById[`${run_id}/${attempt_number}`] ?? jobsById[run_id] ?? [] } }),
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

test("a failed handler step alone is no failure of the agent", async () => {
  const mirror = job("conclusion", "failure", [["Handle agent failure", "failure"]]);
  assert.deepEqual(H.failedSteps(handlerOnly), []);
  assert.deepEqual(H.failedSteps([...crashed, mirror]), ["agent / Execute Claude Code CLI", "conclusion / Handle agent failure"]);
  assert.deepEqual(H.failedSteps([mirror]), ["conclusion / Handle agent failure"]); // no agent job in the list
  const r = run("failure");
  const { calls, args } = fakeGithub([r], { [r.id]: handlerOnly }, [{ number: 232, title: "x", body: H.marker(WF.path) }]);
  assert.equal(await H.reconcile(args), "closed #232");
  assert.equal(calls.at(-1)[1].state, "closed");
});

test("a run being re-run counts by its first attempt, so an older good run recovers nothing", async () => {
  // 2026-11-25: issue 158 was closed as recovered by run 45663764218 of 17:35 UTC while 45684338261 (19:23)
  // was in progress on attempt 2 and its first attempt had failed.
  const good = run("success", "2026-11-25T17:35:00Z");
  const again = listed(45684338261, "in_progress", null, 2, "2026-11-25T19:23:00Z");
  let { calls, args } = fakeGithub([good], { [good.id]: [job("agent", "success")], "45684338261/1": crashed }, [], [again]);
  assert.equal(await H.reconcile(args), "opened #200");
  assert.match(calls[0][1].title, /1 failed run in a row/);
  assert.match(calls[0][1].body, /\[45684338261\]\([^)]*\) \| 2026-11-25 19:23 UTC \(first attempt; re-run under way\)/);
  assert.doesNotMatch(calls[0][1].body, /45663764218/);
  assert.deepEqual(H.namedFailures({ body: calls[0][1].body }), [{ id: 45684338261, at: Date.parse("2026-11-25T19:23:00Z") }]);
  // a first run still waiting for its runner is nothing
  const waiting = listed(45690000000, "in_progress", null, 1, "2026-11-25T20:05:00Z");
  const ok = run("success", "2026-11-25T20:30:00Z");
  ({ calls, args } = fakeGithub([ok], { [ok.id]: [job("agent", "success")] }, [], [waiting]));
  assert.equal(await H.reconcile(args), "ok");
  assert.equal(calls.length, 0);
});

test("a good run older than a failure the issue names closes nothing", async () => {
  const issue = { number: 158, title: "x", body: `${H.marker(WF.path)}\n| Run | Started | Event | Agent job | Failed steps |\n| --- | --- | --- | --- | --- |\n` +
    `| [45684338261](https://example.test/runs/45684338261) | 2026-11-25 19:23 UTC | schedule | 7 min | agent / Execute Claude Code CLI |` };
  // the failure is no longer listed and the newest good run, 17:35, is older than it
  const good = run("success", "2026-11-25T17:35:00Z");
  let { calls, args } = fakeGithub([good], { [good.id]: [job("agent", "success")] }, [issue]);
  assert.equal(await H.reconcile(args), "kept #158");
  assert.equal(calls.length, 0);
  // the same run, re-run to a success, is that failure recovered
  const redone = listed(45684338261, "completed", "success", 2, "2026-11-25T19:23:00Z");
  ({ calls, args } = fakeGithub([redone], { [redone.id]: [job("agent", "success")] }, [issue]));
  assert.equal(await H.reconcile(args), "closed #158");
  assert.match(calls[0][1].body, /Recovered: \[run 45684338261\]/);
  // a good run after the failure closes it as before
  const later = run("success", "2026-11-25T20:30:00Z");
  ({ args } = fakeGithub([later], { [later.id]: [job("agent", "success")] }, [issue]));
  assert.equal(await H.reconcile(args), "closed #158");
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

test("the process-doctor is dispatched once for health issues it has not seen, with a cooldown", async () => {
  const now = Date.parse("2026-11-24T12:00:00Z");
  const make = ({ issues, comments = {}, runs = [], missing = false }) => {
    const calls = [];
    const github = {
      paginate: async (fn, args) => (args.issue_number ? comments[args.issue_number] || [] : issues),
      rest: {
        issues: { listForRepo: () => {}, listComments: () => {} },
        actions: {
          listWorkflowRuns: async () => { if (missing) throw Object.assign(new Error("nf"), { status: 404 }); return { data: { workflow_runs: runs } }; },
          createWorkflowDispatch: async (a) => { calls.push(a); },
        },
      },
    };
    return { calls, args: { github, owner: "o", repo: "r", core: { info() {} }, now } };
  };
  const health = [{ name: "agentic-workflows" }, { name: "agent-health" }];
  const seen = { number: 96, comments: 1, labels: health }, fresh = { number: 99, comments: 0, labels: health };
  const fresh2 = { number: 98, comments: 2, labels: health };
  const change = { number: 97, comments: 0, labels: ["agentic-workflows", "workflow-change"] };
  const notice = { number: 95, comments: 0, labels: ["agentic-workflows"] };
  const said = { 96: [{ body: "**Process doctor:** cause z.ai 529" }], 98: [{ body: "Recovered" }] };

  let t = make({ issues: [notice] });
  assert.equal(await H.dispatchDoctor(t.args), "doctor: nothing new");
  // issues it already read are looked at again only after the recheck interval
  t = make({ issues: [seen, change, notice], comments: said, runs: [{ status: "completed", created_at: "2026-11-24T09:00:00Z" }] });
  assert.match(await H.dispatchDoctor(t.args), /waits/);
  t = make({ issues: [seen, change], comments: said, runs: [{ status: "completed", created_at: "2026-11-24T07:30:00Z" }] });
  assert.equal(await H.dispatchDoctor(t.args), "doctor: recheck of #96");
  assert.equal(t.calls[0].inputs.issue, "96");

  t = make({ issues: [seen, fresh, fresh2], comments: said });
  assert.equal(await H.dispatchDoctor(t.args), "doctor: dispatched for #98");
  assert.deepEqual(t.calls, [{ owner: "o", repo: "r", workflow_id: "process-doctor.lock.yml", ref: "main", inputs: { issue: "98" } }]);

  t = make({ issues: [fresh], runs: [{ status: "in_progress", created_at: "2026-11-24T08:00:00Z" }] });
  assert.equal(await H.dispatchDoctor(t.args), "doctor: already running");
  t = make({ issues: [fresh], runs: [{ status: "completed", created_at: "2026-11-24T11:00:00Z" }] });
  assert.match(await H.dispatchDoctor(t.args), /waits/);
  t = make({ issues: [fresh], runs: [{ status: "completed", created_at: "2026-11-24T09:00:00Z" }] });
  assert.equal(await H.dispatchDoctor(t.args), "doctor: dispatched for #99");
  t = make({ issues: [fresh], missing: true });
  assert.equal(await H.dispatchDoctor(t.args), "doctor: not installed");
  assert.equal(t.calls.length, 0);
});

test("a streak whose issue was closed after its last failure opens no second issue", async () => {
  const bad = run("failure", "2026-11-24T06:43:00Z");
  const closed = [{ number: 101, closed_at: "2026-11-24T14:17:00Z", body: H.marker(WF.path) },
                  { number: 50, closed_at: "2026-11-20T10:00:00Z", body: H.marker(WF.path) }];
  let { calls, args } = fakeGithub([bad], { [bad.id]: crashed });
  args.closedIssues = closed;
  assert.equal(await H.reconcile(args), "handled in #101");
  assert.equal(calls.length, 0);

  // the duplicate opened before this rule closes as not planned
  ({ calls, args } = fakeGithub([bad], { [bad.id]: crashed }, [{ number: 109, title: "x", body: H.marker(WF.path) }]));
  args.closedIssues = closed;
  assert.equal(await H.reconcile(args), "closed duplicate #109");
  assert.deepEqual(calls.map((c) => c[0]), ["comment", "update"]);
  assert.equal(calls[1][1].state_reason, "not_planned");

  // a failure after the close is news: a new issue
  const later = run("failure", "2026-11-24T15:00:00Z");
  ({ args } = fakeGithub([later, bad], { [later.id]: crashed, [bad.id]: crashed }));
  args.closedIssues = closed;
  assert.equal(await H.reconcile(args), "opened #200");
});

test("a workflow_run event also rechecks workflows with an open issue", () => {
  const a = { path: ".github/workflows/a.lock.yml" }, b = { path: ".github/workflows/b.lock.yml" }, c = { path: ".github/workflows/c.lock.yml" };
  const open = [{ body: `x\n${H.marker(b.path)}` }];
  assert.deepEqual(H.pick([a, b, c], null, open), [a, b, c]);
  assert.deepEqual(H.pick([a, b, c], a.path, open), [a, b]);
  assert.deepEqual(H.pick([a, b, c], c.path, []), [c]);
});
