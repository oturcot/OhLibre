const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const workflows = path.join(__dirname, "..", "workflows");
function condition(file, job) {
  const yaml = fs.readFileSync(path.join(workflows, file), "utf8");
  const match = yaml.match(new RegExp(`^  ${job}:\\n    if: >-\\n((?:      .*\\n)+)`, "m"));
  assert.ok(match, `Missing ${job} condition in ${file}`);
  return match[1].trim();
}

function permitted(expression, overrides = {}) {
  const github = {
    actor: "oturcot",
    repository_owner: "oturcot",
    repository: "oturcot/OhLibre",
    event_name: "pull_request",
    ref: "refs/heads/main",
    ...overrides,
    event: {
      pull_request: {
        user: { login: "oturcot" },
        head: { repo: { full_name: "oturcot/OhLibre" }, ref: "feature", sha: "new" },
      },
      review: { user: { login: "oturcot" }, state: "approved", commit_id: "new" },
      workflow_run: { event: "pull_request", actor: { login: "oturcot" }, conclusion: "success", head_branch: "main" },
      ...overrides.event,
    },
  };
  return vm.runInNewContext(expression, { github });
}

const authorize = condition("ci.yml", "authorize");
const fork = {
  user: { login: "contributor" },
  head: { repo: { full_name: "contributor/OhLibre" }, ref: "feature", sha: "new" },
};
const dependabot = {
  user: { login: "dependabot[bot]" },
  head: { repo: { full_name: "oturcot/OhLibre" }, ref: "dependabot/update", sha: "new" },
};
assert.equal(permitted(authorize), true);
assert.equal(permitted(authorize, { actor: "dependabot[bot]", event: { pull_request: dependabot } }), true);
assert.equal(permitted(authorize, { actor: "contributor", event: { pull_request: fork } }), false);
assert.equal(permitted(authorize, { event: { pull_request: fork } }), false);
assert.equal(permitted(authorize, { actor: "contributor" }), false);
assert.equal(permitted(authorize, { event_name: "pull_request_review", event: { pull_request: fork } }), true);
assert.equal(permitted(authorize, {
  event_name: "pull_request_review",
  event: { pull_request: fork, review: { user: { login: "oturcot" }, state: "approved", commit_id: "old" } },
}), false);
assert.equal(permitted(authorize, {
  event_name: "pull_request_review",
  event: { pull_request: fork, review: { user: { login: "contributor" }, state: "approved", commit_id: "new" } },
}), false);
assert.equal(permitted(authorize, { event_name: "push", actor: "contributor" }), false);
assert.equal(permitted(authorize, { event_name: "workflow_dispatch", actor: "contributor" }), false);
assert.equal(permitted(authorize, { event_name: "merge_group" }), true);

const report = condition("report-ci-status.yml", "report");
assert.equal(permitted(report), true);
assert.equal(permitted(report, {
  event: { workflow_run: { event: "pull_request", actor: { login: "contributor" } } },
}), false);
assert.equal(permitted(report, {
  event: { workflow_run: { event: "pull_request_review", actor: { login: "oturcot" } } },
}), true);
const merge = condition("merge-dependencies.yml", "merge");
assert.equal(permitted(merge), true);
assert.equal(permitted(merge, {
  event: { workflow_run: { event: "pull_request", conclusion: "success", actor: { login: "contributor" } } },
}), false);
assert.equal(permitted(merge, {
  event: { workflow_run: { event: "pull_request", conclusion: "success", actor: { login: "dependabot[bot]" } } },
}), true);
const update = condition("python-image-updates.yml", "update");
assert.equal(permitted(update, { event_name: "schedule" }), true);
assert.equal(permitted(update, { event_name: "workflow_dispatch", actor: "contributor" }), false);
const select = condition("publish-main-beta.yml", "select");
assert.equal(permitted(select, { event_name: "schedule" }), true);
assert.equal(permitted(select, { event_name: "workflow_dispatch", actor: "contributor" }), false);
assert.equal(permitted(select, {
  event_name: "workflow_run",
  event: { workflow_run: { event: "push", head_branch: "main", actor: { login: "contributor" } } },
}), false);
console.log("CI authorization tests passed.");
