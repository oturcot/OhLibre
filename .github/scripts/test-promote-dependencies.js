const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { actionUpdates, updateActions, bootstrap, bootstrapFiles, marker } = require("./promote-dependencies.js");

const diff = [
  "--- a/.github/workflows/test.yml",
  "+++ b/.github/workflows/test.yml",
  "-      - uses: actions/checkout@v6",
  "+      - uses: actions/checkout@v7",
  "-      - uses: docker/setup-buildx-action@v3",
  "+      - uses: docker/setup-buildx-action@v4",
].join("\n");
const updates = actionUpdates(diff);
assert.equal(updates.get("actions/checkout").version, "v7");
assert.equal(updates.get("docker/setup-buildx-action").version, "v4");
assert.throws(() => actionUpdates("-      - uses: actions/checkout@v6\n+      - run: echo unsafe"), /Unexpected/);
assert.throws(() => actionUpdates("-      - uses: actions/checkout@v6\n+      - uses: other/action@v7"), /replace existing/);

const root = fs.mkdtempSync(path.join(process.env.RUNNER_TEMP || os.tmpdir(), "ohlibre-promotion-test-"));
const source = path.resolve(__dirname, "../..");
const stable = path.join(root, "stable");
fs.mkdirSync(stable);
const compose = path.join(stable, "docker-compose.yml");
const app = path.join(stable, "downloader.py");
fs.writeFileSync(compose, "services:\n  ohdio:\n    image: ghcr.io/oturcot/radio-canada-podcast:latest\n    volumes:\n      - source: ${PODCAST_DIR:-./podcasts}\n");
fs.writeFileSync(app, "stable application\n");
try {
  bootstrap(source, stable);
  assert.match(fs.readFileSync(compose, "utf8"), /image: oturcot\/ohlibre:latest/);
  assert.match(fs.readFileSync(compose, "utf8"), /\$\{PODCAST_DIR:-\.\/podcasts\}/);
  assert.equal(fs.readFileSync(app, "utf8"), "stable application\n");
  assert.equal(fs.readFileSync(path.join(stable, marker), "utf8"), "1\n");
  for (const file of bootstrapFiles) {
    assert.deepEqual(fs.readFileSync(path.join(stable, file)), fs.readFileSync(path.join(source, file)));
  }
  const extra = path.join(stable, ".github/workflows/stable-only.yml");
  fs.writeFileSync(extra, "steps:\n  - uses: actions/checkout@v5 # stable-only workflow\n  - uses: actions/checkout@v8\n  - uses: unrelated/action@v1\n");
  updateActions(stable, updates);
  assert.match(fs.readFileSync(extra, "utf8"), /actions\/checkout@v7 # stable-only workflow/);
  assert.match(fs.readFileSync(extra, "utf8"), /actions\/checkout@v8/);
  assert.match(fs.readFileSync(extra, "utf8"), /unrelated\/action@v1/);
  updateActions(stable, actionUpdates("-      - uses: actions/checkout@v7\n+      - uses: actions/checkout@v6"));
  assert.match(fs.readFileSync(extra, "utf8"), /actions\/checkout@v7 # stable-only workflow/);
  assert.match(fs.readFileSync(extra, "utf8"), /actions\/checkout@v8/);
  fs.unlinkSync(extra);
  assert.throws(() => bootstrap(source, stable), /Unexpected stable Compose image/);
} finally {
  for (const file of [...bootstrapFiles, marker]) {
    const target = path.join(stable, file);
    if (fs.existsSync(target)) fs.unlinkSync(target);
  }
  fs.unlinkSync(compose);
  fs.unlinkSync(app);
  fs.rmdirSync(path.join(stable, ".github/workflows"));
  fs.rmdirSync(path.join(stable, ".github/scripts"));
  fs.rmdirSync(path.join(stable, ".github"));
  fs.rmdirSync(stable);
  fs.rmdirSync(root);
}
console.log("Dependency promotion tests passed.");
