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
async function reconcile({ github, owner, repo, workflow, openIssues, core }) {
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

/** Entry point for actions/github-script. Only workflows that have a .md source (gh-aw agents) count. */
async function main({ github, context, core }) {
  const { owner, repo } = context.repo;
  const fs = require("fs");
  const all = await github.paginate(github.rest.actions.listRepoWorkflows, { owner, repo, per_page: 100 });
  const agents = all.filter((w) => w.path.endsWith(".lock.yml") && fs.existsSync(w.path.replace(/\.lock\.yml$/, ".md")));
  const only = context.payload.workflow_run && context.payload.workflow_run.path;
  const todo = only ? agents.filter((w) => w.path === only) : agents;
  const openIssues = await github.paginate(github.rest.issues.listForRepo, { owner, repo, state: "open", labels: LABEL, per_page: 100 });
  const done = [];
  for (const workflow of todo) done.push(`${workflow.name}: ${await reconcile({ github, owner, repo, workflow, openIssues, core })}`);
  await core.summary.addList(done).write();
}

module.exports = { main, reconcile, streakOf, failedSteps, title, body, marker, IGNORED_STEPS };
