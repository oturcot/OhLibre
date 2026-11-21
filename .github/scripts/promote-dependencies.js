const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const workflows = [
  "ci.yml", "test-ohdio.yml", "package-ohdio.yml", "release.yml", "publish-ohdio.yml",
  "report-ci-status.yml", "python-image-updates.yml", "publish-main-beta.yml",
];
const scripts = [
  "image-archives.sh", "local-compose.sh", "registry-compose.sh", "release-version.sh",
  "publish-dockerhub.sh", "stamp-image-version.sh", "test-ci-authorization.js",
  "test-dependency-merge.js", "test-image-archives.sh", "test-publish-dockerhub.sh",
  "test-release-version.sh", "promote-dependencies.js", "test-promote-dependencies.js",
];
const bootstrapFiles = [
  ...workflows.map(name => `.github/workflows/${name}`),
  ...scripts.map(name => `.github/scripts/${name}`),
  ".github/python-image-digest", "Dockerfile",
];
const marker = ".github/stable-dockerhub-ready";

function copy(source, stable, name) {
  const destination = path.join(stable, name);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(path.join(source, name), destination);
}

function actionUpdates(diff) {
  const removed = new Map();
  const added = new Map();
  for (const line of diff.split("\n")) {
    if (!/^[+-]/.test(line) || line.startsWith("+++") || line.startsWith("---")) continue;
    const match = line.match(/^[+-]\s*(?:-\s*)?uses:\s*["']?([^@\s]+)@([^"'\s#]+)/);
    if (!match) throw new Error(`Unexpected dependency workflow change: ${line}`);
    const [, name, version] = match;
    if (line[0] === "-") {
      if (!removed.has(name)) removed.set(name, new Set());
      removed.get(name).add(version);
    }
    else {
      if (added.has(name) && added.get(name) !== version)
        throw new Error(`Multiple updated versions for ${name}`);
      added.set(name, version);
    }
  }
  if ([...removed.keys()].some(name => !added.has(name)) || [...added.keys()].some(name => !removed.has(name)))
    throw new Error("Action changes must replace existing action versions.");
  return new Map([...added].map(([name, version]) => [name, { version, previous: removed.get(name) }]));
}

function targetVersion(name, current, update) {
  if (current === update.version) return current;
  const parse = ref => /^v?\d+(?:\.\d+)*$/.test(ref) ? ref.replace(/^v/, "").split(".").map(Number) : null;
  const old = parse(current);
  const next = parse(update.version);
  if (!old || !next) {
    if (update.previous.has(current)) return update.version;
    throw new Error(`Cannot safely compare ${name}@${current} with ${update.version}.`);
  }
  for (let i = 0; i < Math.max(old.length, next.length); i++) {
    if ((old[i] || 0) > (next[i] || 0)) return current;
    if ((old[i] || 0) < (next[i] || 0)) return update.version;
  }
  return current;
}

function updateActions(stable, updates) {
  const dir = path.join(stable, ".github/workflows");
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isFile() || !/\.ya?ml$/.test(entry.name)) continue;
    const file = path.join(dir, entry.name);
    const old = fs.readFileSync(file, "utf8");
    const updated = old.replace(/^(\s*(?:-\s*)?uses:\s*["']?)([^@\s]+)@([^"'\s#]+)/gm,
      (line, prefix, name, version) =>
        updates.has(name) ? `${prefix}${name}@${targetVersion(name, version, updates.get(name))}` : line);
    if (updated !== old) fs.writeFileSync(file, updated);
  }
}

function bootstrap(source, stable) {
  const compose = path.join(stable, "docker-compose.yml");
  const original = fs.readFileSync(compose, "utf8");
  const updated = original.replace(
    /^    image: ghcr\.io\/oturcot\/radio-canada-podcast:latest$/m,
    "    image: oturcot/ohlibre:latest",
  );
  if (updated === original) throw new Error("Unexpected stable Compose image; refusing migration.");
  for (const name of bootstrapFiles) copy(source, stable, name);
  fs.writeFileSync(compose, updated);
  fs.writeFileSync(path.join(stable, marker), "1\n");
}

function promote({ source, stable, sha }) {
  if (!/^[0-9a-f]{40}$/.test(sha)) throw new Error("Invalid merge commit SHA.");
  const git = (...args) => execFileSync("git", ["-C", source, ...args], { encoding: "utf8" });
  const changes = git("diff", "--name-only", `${sha}^1`, sha, "--",
    "Dockerfile", ".github/python-image-digest", ".github/workflows/").trim().split("\n").filter(Boolean);
  if (!changes.length) throw new Error("No dependency changes to promote.");
  const diff = git("diff", "--no-ext-diff", "--no-color", "--unified=0", `${sha}^1`, sha, "--", ".github/workflows/");
  const updates = actionUpdates(diff);

  if (!fs.existsSync(path.join(stable, marker))) {
    bootstrap(source, stable);
    return;
  }

  updateActions(stable, updates);
  if (changes.includes(".github/python-image-digest")) copy(source, stable, ".github/python-image-digest");
  if (changes.includes("Dockerfile")) {
    const patch = git("diff", "--binary", `${sha}^1`, sha, "--", "Dockerfile");
    execFileSync("git", ["-C", stable, "apply", "--3way", "-"], { input: patch, stdio: ["pipe", "inherit", "inherit"] });
  }
}

module.exports = { promote, actionUpdates, updateActions, bootstrap, bootstrapFiles, marker };
