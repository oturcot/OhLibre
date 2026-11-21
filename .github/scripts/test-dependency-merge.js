const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { bootstrapFiles, marker } = require("./promote-dependencies.js");

const workflow = fs.readFileSync(path.join(__dirname, "../workflows/report-ci-status.yml"), "utf8");
const match = workflow.match(/      - name: Merge tested dependencies\n[\s\S]*?          script: \|\n((?:            .*\n)+)/);
assert.ok(match, "Missing dependency merge script");
const script = match[1].replace(/^            /gm, "");

async function exercise(options = {}) {
  const calls = [];
  const run = {
    id: 12, run_attempt: 1, workflow_id: 3, event: "pull_request",
    head_sha: "head", head_branch: options.pr?.head?.ref || "dependabot/update", html_url: "https://ci/12",
  };
  const pr = {
    number: 7, state: "open", user: { login: "dependabot[bot]" },
    head: { sha: "head", ref: run.head_branch, repo: { full_name: "owner/repo" } },
    base: { ref: "main" }, labels: [],
    ...options.pr,
  };
  const jobs = options.jobs || [
    { name: "ohdio / test", conclusion: "success" },
    { name: "Gated tests", conclusion: "success" },
  ];
  const rest = {
    repos: {
      listPullRequestsAssociatedWithCommit: async () => [pr],
      listCommitStatusesForRef: async () => ({ data: options.statuses || [
        { context: "CI / gated tests", state: "success", target_url: "https://ci/12/attempts/1" },
      ] }),
      compareCommitsWithBasehead: async () => ({ data: { behind_by: options.behind || 0 } }),
    },
    pulls: {
      listFiles: async () => options.files || [{ filename: ".github/workflows/ci.yml", status: "modified" }],
      updateBranch: async args => calls.push(["update", args]),
      merge: async args => { calls.push(["merge", args]); return { data: { merged: true } }; },
    },
    actions: {
      listJobsForWorkflowRunAttempt: async () => ({ data: { jobs } }),
      listWorkflowRuns: async () => options.runs || [{ ...run, run_number: 1 }],
    },
    issues: { createComment: async args => calls.push(["comment", args]) },
  };
  const github = { rest, paginate: async (method, args) => method(args) };
  await vm.runInNewContext(`(async () => {\n${script}\n})()`, {
    github, context: { repo: { owner: "owner", repo: "repo" }, payload: { workflow_run: run } },
    core: { info: () => {} },
  });
  return calls;
}

module.exports = (async () => {
  assert.equal((await exercise())[0][0], "merge");
  assert.deepEqual((await exercise({ behind: 1 })).map(c => c[0]), ["comment"]);
  const promotion = {
    user: { login: "owner" },
    head: { sha: "head", ref: "automation/promote-dependency-release", repo: { full_name: "owner/repo" } },
    base: { ref: "stable" }, labels: [{ name: "dependencies" }],
  };
  assert.deepEqual((await exercise({ pr: promotion, behind: 1 })).map(c => c[0]), ["update"]);
  assert.equal((await exercise({ pr: promotion, files: [
    { filename: ".github/scripts/publish-dockerhub.sh", status: "added" },
    { filename: "docker-compose.yml", status: "modified" },
  ] }))[0][0], "merge");
  assert.equal((await exercise({ pr: promotion, files: [...bootstrapFiles, marker]
    .map(filename => ({ filename, status: "modified" })) }))[0][0], "merge");
  await assert.rejects(exercise({ pr: promotion, files: [
    { filename: ".github/scripts/unexpected.sh", status: "added" },
  ] }), /Unexpected dependency changes/);
  assert.deepEqual(await exercise({ pr: { ...promotion, user: { login: "contributor" } } }), []);
  assert.deepEqual(await exercise({ pr: { user: { login: "contributor" } } }), []);
  await assert.rejects(exercise({ files: [{ filename: "downloader.py", status: "modified" }] }), /Unexpected dependency changes/);
  await assert.rejects(exercise({ jobs: [] }), /Required job did not pass/);
  await assert.rejects(exercise({ statuses: [{ context: "CI / gated tests", state: "pending" }] }), /No matching successful gated status/);
  await assert.rejects(exercise({ runs: [{ id: 99, run_attempt: 1, event: "pull_request", head_branch: "dependabot/update", run_number: 2 }] }), /newer CI run/);
  console.log("Dependency merge tests passed.");
})();
