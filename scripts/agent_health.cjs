// Agent health: one issue per gh-aw agent workflow while its runs fail, closed by itself when a run
// succeeds again. Replaces gh-aw's issue per failure ("[aw] X: engine driver crashed", "timed out")
// and its ever-growing "[aw] Detection Runs" tracker, both turned off in the workflows' frontmatter.
//
// The state lives in GitHub itself: every call rebuilds the issue from the workflow's latest runs,
// so a missed event (runs started with GITHUB_TOKEN fire no workflow_run) is caught by the schedule.
// Used by .github/workflows/agent-health.yml through actions/github-script; tests: tests/agent_health.test.mjs.

const LABEL = "agent-health";
const LABELS = ["agentic-workflows", LABEL];
// Steps whose failure says nothing about the agent's work. gh-aw v1.2.2's step-summary parser throws
// "Maximum call stack size exceeded" on long sessions after the agent finished and its outputs went out.
const IGNORED_STEPS = new Set(["Parse agent logs for step summary"]);
// Conclusions that are neither a success nor a failure of the agent.
const NEUTRAL = new Set(["cancelled", "skipped", "action_required", "neutral", "stale"]);
const SHOWN = 10;

const marker = (path) => `<!-- agent-health: ${path} -->`;

/** The failed steps of a run's jobs that count, as "job / step" strings. */
function failedSteps(jobs) {
  const out = [];
  for (const job of jobs || []) {
    if (job.conclusion !== "failure" && job.conclusion !== "timed_out" && job.conclusion !== "cancelled") continue;
    const bad = (job.steps || []).filter((s) => s.conclusion === "failure" || s.conclusion === "timed_out" || s.conclusion === "cancelled");
    if (!bad.length) out.push(`${job.name} (${job.conclusion})`);
    for (const s of bad) if (!IGNORED_STEPS.has(s.name)) out.push(`${job.name} / ${s.name}${s.conclusion === "failure" ? "" : ` (${s.conclusion})`}`);
  }
  return out;
}

/** Minutes a step or job ran, or null. */
function minutes(a, b) {
  if (!a || !b) return null;
  return Math.round((Date.parse(b) - Date.parse(a)) / 60000);
}

/**
 * The failure streak of one workflow: runs newest first (completed only), jobsOf(run) gives its jobs.
 * Returns {streak: [{run, steps, mins}], recovered: run|null}; recovered is the newest good run.
 */
async function streakOf(runs, jobsOf) {
  const streak = [];
  for (const run of runs) {
    if (run.status !== "completed" || NEUTRAL.has(run.conclusion)) continue;
    if (run.conclusion === "success") return { streak, recovered: run };
    const jobs = await jobsOf(run);
    const steps = failedSteps(jobs);
    if (!steps.length) return { streak, recovered: run }; // only an ignored step failed: the agent did its work
    const agent = (jobs || []).find((j) => j.name === "agent");
    streak.push({ run, steps, mins: agent ? minutes(agent.started_at, agent.completed_at) : null });
    if (streak.length >= 30) break;
  }
  return { streak, recovered: null };
}

function title(name, streak) {
  const timedOut = streak.some((f) => f.steps.some((s) => /timed_out|cancelled/.test(s)));
  return `[aw] ${name}: ${streak.length} failed run${streak.length > 1 ? "s" : ""} in a row${timedOut ? " (timeout)" : ""}`;
}

function body(name, path, streak) {
  const rows = streak.slice(0, SHOWN).map(({ run, steps, mins }) =>
    `| [${run.id}](${run.html_url}) | ${run.created_at.replace("T", " ").slice(0, 16)} UTC | ${run.event} | ${mins ?? "?"} min | ${steps.join("<br>")} |`);
  const first = streak[streak.length - 1].run;
  return [
    marker(path),
    `**${name}** has failed ${streak.length} time${streak.length > 1 ? "s" : ""} in a row, since ${first.created_at.replace("T", " ").slice(0, 16)} UTC.`,
    "",
    "| Run | Started | Event | Agent job | Failed steps |",
    "| --- | --- | --- | --- | --- |",
    ...rows,
    streak.length > SHOWN ? `\n…and ${streak.length - SHOWN} older failed runs.` : "",
    "",
    "This issue is kept by `agent-health.yml`: it is rewritten after every run of the workflow and closes by itself " +
      "when a run succeeds. Fix the cause in the workflow or close it with the reason; do not open a second one.",
  ].join("\n");
}

/** Reconcile one workflow ({id, name, path}) with its issue. Returns what was done. */
async function reconcile({ github, owner, repo, workflow, openIssues, closedIssues = [], core }) {
  const { data } = await github.rest.actions.listWorkflowRuns({ owner, repo, workflow_id: workflow.id, status: "completed", per_page: 40 });
  const jobsOf = async (run) => (await github.rest.actions.listJobsForWorkflowRunAttempt({ owner, repo, run_id: run.id, attempt_number: run.run_attempt || 1, per_page: 100 })).data.jobs;
  const { streak, recovered } = await streakOf(data.workflow_runs, jobsOf);
  const issue = openIssues.find((i) => (i.body || "").includes(marker(workflow.path)));
  if (!streak.length) {
    if (!issue) return "ok";
    const how = recovered ? `[run ${recovered.id}](${recovered.html_url}) succeeded at ${recovered.updated_at.replace("T", " ").slice(0, 16)} UTC` : "no failed run is left";
    await github.rest.issues.createComment({ owner, repo, issue_number: issue.number, body: `Recovered: ${how}. Closing.` });
    await github.rest.issues.update({ owner, repo, issue_number: issue.number, state: "closed", state_reason: "completed" });
    core.info(`${workflow.name}: closed #${issue.number}`);
    return `closed #${issue.number}`;
  }
  // A streak whose issue was closed after its newest failure was handled (the process-doctor closes an
  // issue when its cause is fixed, before the agent runs again): no second issue for the same runs.
  const newest = Date.parse(streak[0].run.updated_at || streak[0].run.created_at);
  const prev = closedIssues
    .filter((i) => i.closed_at && (i.body || "").includes(marker(workflow.path)))
    .sort((a, b) => Date.parse(b.closed_at) - Date.parse(a.closed_at))[0];
  if (prev && Date.parse(prev.closed_at) > newest) {
    if (!issue) return `handled in #${prev.number}`;
    if (issue.number > prev.number) {
      await github.rest.issues.createComment({ owner, repo, issue_number: issue.number,
        body: `Closing: the same failed runs as #${prev.number}, which was closed after them. A new failure opens a new issue.` });
      await github.rest.issues.update({ owner, repo, issue_number: issue.number, state: "closed", state_reason: "not_planned" });
      core.info(`${workflow.name}: closed duplicate #${issue.number} of #${prev.number}`);
      return `closed duplicate #${issue.number}`;
    }
  }
  const t = title(workflow.name, streak), b = body(workflow.name, workflow.path, streak);
  if (!issue) {
    const { data: made } = await github.rest.issues.create({ owner, repo, title: t, body: b, labels: LABELS });
    core.info(`${workflow.name}: opened #${made.number}`);
    return `opened #${made.number}`;
  }
  if (issue.title === t && issue.body === b) return `kept #${issue.number}`;
  await github.rest.issues.update({ owner, repo, issue_number: issue.number, title: t, body: b });
  core.info(`${workflow.name}: updated #${issue.number}`);
  return `updated #${issue.number}`;
}

/** gh-aw's own failure notices, which agent-health replaces: an issue per failure and the detection tracker. */
function isLegacy(issue) {
  if (issue.state !== "open" || issue.pull_request) return false;
  const body = issue.body || "";
  if (body.includes("<!-- agent-health:")) return false;
  return body.includes("<!-- gh-aw-failure-issue: true") || issue.title === "[aw] Detection Runs";
}

/** Close gh-aw's old failure issues with a pointer to the health issue of that agent, if any is open. */
async function retireLegacy({ github, owner, repo, core }) {
  const open = await github.paginate(github.rest.issues.listForRepo, { owner, repo, state: "open", labels: "agentic-workflows", per_page: 100 });
  const health = open.filter((i) => (i.body || "").includes("<!-- agent-health:"));
  const done = [];
  for (const issue of open.filter(isLegacy)) {
    const wf = ((issue.body || "").match(/gh-aw-failure-issue: true, workflow_id: ([\w.-]+)/) || [])[1];
    const now = wf && health.find((h) => h.body.includes(`/${wf}.lock.yml -->`));
    const where = now ? `Its runs still fail: see #${now.number}.` : wf ? "Its runs pass again." : "";
    const text = issue.title === "[aw] Detection Runs"
      ? "Closing: detector failures stay in each run's diagnostics now (threat-detection.report-as-issue: false), so this tracker no longer grows."
      : `Closing: gh-aw no longer opens an issue per failure. agent-health.yml keeps one self-closing issue per failing agent instead. ${where}`;
    await github.rest.issues.createComment({ owner, repo, issue_number: issue.number, body: text.trim() });
    await github.rest.issues.update({ owner, repo, issue_number: issue.number, state: "closed", state_reason: "not_planned" });
    core.info(`closed legacy #${issue.number}`);
    done.push(`closed legacy #${issue.number}`);
  }
  return done;
}

// The process-doctor agent reads the failures behind every health issue and fixes the process.
const DOCTOR = "process-doctor.lock.yml";
const DOCTOR_SAID = /process[ -]doctor/i; // its comments carry its name (and gh-aw's footer)
const DOCTOR_COOLDOWN_MS = 2 * 3600 * 1000;
// While its issues stay open (a health issue it already read, its own workflow-change issues) the
// doctor looks again every few hours, so a fix that landed closes them the same day.
const DOCTOR_RECHECK_MS = 4 * 3600 * 1000;
const DOCTOR_OWNS = ["agent-health", "workflow-change"];
const BUSY = new Set(["queued", "in_progress", "waiting", "requested", "pending"]);

/**
 * Start the process-doctor for the open health issues it has not commented on yet, at most once per
 * DOCTOR_COOLDOWN_MS and never while a doctor run is waiting or running. Issues opened with
 * GITHUB_TOKEN start no workflow by themselves; a workflow_dispatch made with it does.
 */
async function dispatchDoctor({ github, owner, repo, core, ref = "main", now = Date.now() }) {
  const open = await github.paginate(github.rest.issues.listForRepo, { owner, repo, state: "open", labels: "agentic-workflows", per_page: 100 });
  const labels = (i) => (i.labels || []).map((l) => (typeof l === "string" ? l : l.name));
  const fresh = [], seen = [];
  for (const issue of open) {
    if (issue.pull_request || !labels(issue).some((l) => DOCTOR_OWNS.includes(l))) continue;
    if (!labels(issue).includes(LABEL)) { seen.push(issue.number); continue; } // its own workflow-change issue
    const comments = issue.comments
      ? await github.paginate(github.rest.issues.listComments, { owner, repo, issue_number: issue.number, per_page: 100 })
      : [];
    (comments.some((c) => DOCTOR_SAID.test(c.body || "")) ? seen : fresh).push(issue.number);
  }
  if (!fresh.length && !seen.length) return "doctor: nothing new";
  let runs;
  try {
    ({ data: { workflow_runs: runs } } = await github.rest.actions.listWorkflowRuns({ owner, repo, workflow_id: DOCTOR, per_page: 5 }));
  } catch (e) {
    if (e.status === 404) return "doctor: not installed";
    throw e;
  }
  if (runs.some((r) => BUSY.has(r.status))) return "doctor: already running";
  const last = runs.length ? Date.parse(runs[0].created_at) : 0;
  const wait = fresh.length ? DOCTOR_COOLDOWN_MS : DOCTOR_RECHECK_MS;
  if (now - last < wait) return `doctor: ran at ${runs[0].created_at}, waits`;
  const issue = Math.min(...(fresh.length ? fresh : seen));
  await github.rest.actions.createWorkflowDispatch({ owner, repo, workflow_id: DOCTOR, ref, inputs: { issue: String(issue) } });
  core.info(`dispatched the process-doctor for #${issue} (new: ${fresh.join(", ") || "none"}; open: ${seen.join(", ") || "none"})`);
  return fresh.length ? `doctor: dispatched for #${issue}` : `doctor: recheck of #${issue}`;
}

/** Entry point for actions/github-script. Only workflows that have a .md source (gh-aw agents) count. */
// Which workflows a call reconciles: all of them on the schedule or a manual run; on a workflow_run event
// the one that finished plus every workflow with an open issue. GitHub often skips the :17/:47 schedule
// for hours (24.11.2026: 14:29-15:30 UTC), so open issues and duplicates are rechecked on any event.
function pick(agents, only, openIssues) {
  if (!only) return agents;
  return agents.filter((w) => w.path === only || openIssues.some((i) => (i.body || "").includes(marker(w.path))));
}

async function main({ github, context, core }) {
  const { owner, repo } = context.repo;
  const fs = require("fs");
  const all = await github.paginate(github.rest.actions.listRepoWorkflows, { owner, repo, per_page: 100 });
  const agents = all.filter((w) => w.path.endsWith(".lock.yml") && fs.existsSync(w.path.replace(/\.lock\.yml$/, ".md")));
  const only = context.payload.workflow_run && context.payload.workflow_run.path;
  const openIssues = await github.paginate(github.rest.issues.listForRepo, { owner, repo, state: "open", labels: LABEL, per_page: 100 });
  const todo = pick(agents, only, openIssues);
  const { data: closedIssues } = await github.rest.issues.listForRepo({ owner, repo, state: "closed", labels: LABEL, sort: "updated", direction: "desc", per_page: 100 });
  const done = [];
  for (const workflow of todo) done.push(`${workflow.name}: ${await reconcile({ github, owner, repo, workflow, openIssues, closedIssues, core })}`);
  done.push(...(await retireLegacy({ github, owner, repo, core })));
  done.push(await dispatchDoctor({ github, owner, repo, core, ref: (context.payload.repository || {}).default_branch || "main" }));
  await core.summary.addList(done.length ? done : ["nothing to do"]).write();
}

module.exports = { main, pick, reconcile, retireLegacy, dispatchDoctor, isLegacy, streakOf, failedSteps, title, body, marker, IGNORED_STEPS };
