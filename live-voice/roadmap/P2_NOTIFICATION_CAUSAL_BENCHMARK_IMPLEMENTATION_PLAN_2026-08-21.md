# P2 Notification Causal Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a current-source A1 curve for 10, 50 and 100 serial P2
notifications without Browser, audio, Provider or product side effects.

**Architecture:** One development-only Node runner imports the compiled real
`ProductWebP2ActivationOwner`. A deterministic request adapter returns one
ordered notification per RPC after a controlled delay; the final element is
`chat.final`. The runner verifies clean Git state and writes one closed JSON
report outside the repository.

**Tech Stack:** TypeScript production owner compiled by `tsc`, Node ESM,
`node:test`, monotonic `performance.now()`.

**Spec:**
[LATENCY_OPTIMIZATION_PLAN_2026-08-18.md](LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
§§3.3 and 4.

## Global Constraints

- Capability/module: P2 notification transport benchmark; D-046 Tier 1 because
  this packet is a development-only runner with no product/protocol mutation.
  The later bounded-pull B candidate remains Tier 3.
- Dependency: reviewed product/probe source at `ca07a8dd5`; the documentation
  commit `50c816d8d` changes no runtime behavior.
- Total notification populations are exactly `10`, `50` and `100`; the final
  notification carries `chat.final`, so expected serial cost is `N * 85 ms`.
- Formal A1 uses exactly five attempts per population and `85` ms per RPC.
- The runner must use `ProductWebP2ActivationOwner.nextNotification()`; a loop
  that sleeps without invoking the real owner is not accepted.
- Allowed request effects are P2 activate, notification-next and close only.
  Submit, presentation ACK, barge-in, P3, Agent, Tool, Task, history and audio
  effects must all remain zero.
- Output contains no transcript, credential, URL, path, hostname, project,
  Session or private exception text.
- This result is `P2 causal A1`, never an E2E, physical, first-audible or
  Production baseline.
- Scope excludes production owner/protocol changes, batching, coalescing,
  server push, Browser automation, VAD, STT, TTS and physical validation.

---

### Task 1: Executable deterministic owner benchmark

**Files:**

- Create:
  `jiuwenswarm/channels/web/frontend/scripts/liveVoiceP2NotificationCausalBenchmark.mjs`
- Create:
  `jiuwenswarm/channels/web/frontend/tests/liveVoiceP2NotificationCausalBenchmark.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**

- Consumes:
  `ProductWebP2ActivationOwner`, `PRODUCT_P2_ACTIVATE_METHOD`,
  `PRODUCT_P2_NOTIFICATION_NEXT_METHOD` and `PRODUCT_P2_CLOSE_METHOD` from the
  compiled `productWebActivation.js`.
- Produces:
  `runP2NotificationCausalBenchmark(input) -> Promise<Readonly<Report>>` and a
  CLI accepting `--output`, `--git-commit`, `--run-id`, `--samples`,
  `--delay-ms` and `--batch-size`; the supplied commit must equal
  `git rev-parse HEAD` and
  `git status --porcelain --untracked-files=all` must be empty.
- Report schema: `live-voice.p2-notification-causal-report.v0`, with closed
  top-level keys `schema_version`, `run_id`, `git_commit`, `source_state`,
  `sample_count`, `delay_ms`, `batch_size`, `notification_counts`, `rows` and
  `forbidden_effects`.
- Each row contains `notification_count`, `attempts`, `successful`,
  `notification_rpc_count`, `expected_serial_ms`, `samples_ms`, `p50_ms` and
  `p95_ms`.

- [x] **Step 1: Write the failing tests**

Cover one fast virtual-time positive scenario and the closed negative/boundary
contract:

```javascript
const report = await runP2NotificationCausalBenchmark({
  runId: 'p2-a1-test',
  gitCommit: 'a'.repeat(40),
  notificationCounts: [2, 4],
  sampleCount: 2,
  delayMs: 85,
  now: () => virtualNow,
  sleep: async ms => { virtualNow += ms; },
});

assert.deepEqual(report.rows.map(row => row.notification_rpc_count), [4, 8]);
assert.deepEqual(report.rows.map(row => row.p50_ms), [170, 340]);
assert.deepEqual(report.forbidden_effects, {
  submit: 0,
  presentation_ack: 0,
  barge_in: 0,
  p3: 0,
  agent: 0,
  tool: 0,
  task: 0,
  history: 0,
  audio: 0,
});
```

Reject unknown/duplicate CLI keys, unsafe run IDs, non-40-hex commits,
non-canonical integers, counts outside `1..256`, samples outside `1..30`, delay
outside `0..1000` and output overwrite. Existing
`productWebActivation.test.mjs` retains the production owner's wrong-binding,
missing/invalid response and replay oracles.

- [x] **Step 2: Run RED**

```bash
cd jiuwenswarm/channels/web/frontend
node --test tests/liveVoiceP2NotificationCausalBenchmark.test.mjs
```

Expected: FAIL because the runner module does not exist.

- [x] **Step 3: Implement the minimal runner**

Implement only:

```javascript
export async function runP2NotificationCausalBenchmark(input) { /* closed owner loop */ }
export async function main(argv = process.argv.slice(2)) { /* parse and write x */ }
```

The deterministic adapter prepares all `N` notifications before timing, waits
exactly once per `notification.next`, verifies exact increasing
`notification_sequence`, and returns the final presentation only at position
`N`. Use nearest-rank percentiles and `fs.open(output, 'wx')`; emit only the
sanitized run ID to stdout. Do not add a generic metrics framework.

Add one package script that compiles only the real owner/dependencies and runs
the benchmark CLI:

```json
"benchmark:live-voice-p2-notifications": "tsc src/features/live-voice/formal/productWebActivation.ts --target ES2020 --module ES2020 --moduleResolution Bundler --rootDir src --outDir node_modules/.cache/live-voice-integrated-web --lib ES2020,DOM --skipLibCheck --noEmitOnError --strict --noUnusedLocals --noUnusedParameters && node scripts/liveVoiceP2NotificationCausalBenchmark.mjs"
```

- [x] **Step 4: Run GREEN and affected regression**

```bash
cd jiuwenswarm/channels/web/frontend
node --test tests/liveVoiceP2NotificationCausalBenchmark.test.mjs
npm run test:live-voice-integrated-web
```

Expected: benchmark tests PASS; integrated Web remains PASS.

- [x] **Step 5: Static and diff checks**

```bash
cd jiuwenswarm/channels/web/frontend
npx prettier --check \
  scripts/liveVoiceP2NotificationCausalBenchmark.mjs \
  tests/liveVoiceP2NotificationCausalBenchmark.test.mjs \
  package.json
cd ../../../..
git diff --check
```

- [x] **Step 6: Commit the benchmark**

```bash
git add \
  jiuwenswarm/channels/web/frontend/package.json \
  jiuwenswarm/channels/web/frontend/scripts/liveVoiceP2NotificationCausalBenchmark.mjs \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceP2NotificationCausalBenchmark.test.mjs
git commit -m "test(live-voice): add causal P2 notification benchmark"
```

### Task 2: Freeze the current-source A1 artifact

**Files:**

- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/p2-causal/`
- Modify:
  `live-voice/roadmap/P2_NOTIFICATION_CAUSAL_BENCHMARK_IMPLEMENTATION_PLAN_2026-08-21.md`

**Interfaces:**

- Consumes the Task 1 CLI and exact clean implementation commit.
- Produces the private A1 report and a documentation status stating whether the
  current-source 10/50/100 curve was established.

- [x] **Step 1: Verify clean source and create a fresh external target**

Use a detached clean worktree at the exact Task 1 commit. Define the target
without unresolved placeholders:

```bash
P2_A1_COMMIT=$(git rev-parse HEAD)
P2_A1_RUN_ID="p2-a1-$(date -u +%Y%m%dT%H%M%SZ)-${P2_A1_COMMIT:0:9}"
P2_A1_DIR="/home/renan/openJiuwen-ai/live-voice-latency-runs/p2-causal/$P2_A1_RUN_ID"
P2_A1_OUTPUT="$P2_A1_DIR/report.json"
test ! -e "$P2_A1_DIR"
mkdir -p "$P2_A1_DIR"
```

- [x] **Step 2: Execute A1**

```bash
cd jiuwenswarm/channels/web/frontend
npm run benchmark:live-voice-p2-notifications -- \
  --output "$P2_A1_OUTPUT" \
  --git-commit "$P2_A1_COMMIT" \
  --run-id "$P2_A1_RUN_ID" \
  --samples 5 \
  --delay-ms 85 \
  --batch-size 16
```

Expected: exit `0`; 15 successful attempts; notification RPC totals are 50,
250 and 500 for the 10/50/100 rows; every forbidden effect is zero.

- [x] **Step 3: Validate the artifact independently**

Load the JSON in a separate Node process and assert exact keys, commit/run
binding, finite nonnegative samples, nearest-rank p50/p95, expected counts and
zero forbidden effects. The validator must not rewrite the report:

```bash
node - "$P2_A1_OUTPUT" "$P2_A1_COMMIT" "$P2_A1_RUN_ID" <<'NODE'
import fs from 'node:fs';
import assert from 'node:assert/strict';
const [path, commit, runId] = process.argv.slice(2);
const report = JSON.parse(fs.readFileSync(path, 'utf8'));
assert.deepEqual(Object.keys(report).sort(), [
  'batch_size', 'delay_ms', 'forbidden_effects', 'git_commit', 'notification_counts',
  'rows', 'run_id', 'sample_count', 'schema_version', 'source_state',
]);
assert.equal(report.git_commit, commit);
assert.equal(report.run_id, runId);
assert.equal(report.source_state, 'clean');
assert.equal(report.batch_size, 16);
assert.deepEqual(report.notification_counts, [10, 50, 100]);
assert.deepEqual(report.rows.map(row => row.notification_rpc_count), [50, 250, 500]);
assert.ok(Object.values(report.forbidden_effects).every(value => value === 0));
NODE
```

- [x] **Step 4: Record only sanitized status**

Update this plan with the exact source SHA, run ID, row p50/p95, RPC counts and
PASS/FAIL. Keep the raw report external. Do not change `STATUS.md` to claim E2E
or optimization credit.

- [x] **Step 5: Commit the A1 status update**

```bash
git add live-voice/roadmap/P2_NOTIFICATION_CAUSAL_BENCHMARK_IMPLEMENTATION_PLAN_2026-08-21.md
git commit -m "docs(live-voice): record causal P2 A1"
```

## Completion Gate

- Task 1 and Task 2 pass on exact clean source.
- The report proves the real Web P2 owner performs one notification RPC per
  delivered notification under the current contract.
- A1 contains 10/50/100 curves, five attempts each and zero forbidden effects.
- No Browser, service, Provider or product runtime is started.
- No batching optimization is implemented in this packet.
- A complete scoped Tier-1 diff review closes before A1; the later Tier-3 B
  protocol change requires its own independent module and integration review.

## A1 Result — 2026-08-21

**Status:** `PASS — P2 CAUSAL BASELINE ONLY`

- Exact source: `a9142dd2d9b69000a086d4c6b97c2a711ee4cd9c`
- Run ID: `p2-a1-20260820T232850Z-a9142dd2d`
- Controlled delay: 85 ms per notification RPC
- Attempts: 5 per population, 15/15 successful
- Forbidden submit, presentation ACK, barge-in, P3, Agent, Tool, Task,
  history and audio effects: all zero

| Total notifications, final last | RPCs across 5 attempts | p50 | p95 |
|---:|---:|---:|---:|
| 10 | 50 | 854.286 ms | 858.858 ms |
| 50 | 250 | 4,297.356 ms | 4,345.995 ms |
| 100 | 500 | 8,640.025 ms | 8,698.774 ms |

The curve confirms the expected near-linear one-notification-per-RPC cost on
the current source. It is the A1 oracle for one P2 transport candidate; it is
not a physical Live Voice, Browser, first-audible or Production baseline. The
private 0600 report remains outside the repository.
