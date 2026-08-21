# Accepted Optimizations Latency Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an exact no-Chrome A1/B/A2 measurement of the combined
accepted P2 bounded-pull and TTS successor-ACK-overlap behaviors, then add a
default-off manual Web panel that reports separately labelled exploratory
timings.

**Architecture:** A platform-neutral TypeScript checkpoint core owns one
monotonic event graph, closed truth classes, deterministic workloads and direct
stage/round totals. A Node CLI composes the real Product Web P2 and Product P1
owners with controlled external dependencies, writes private reports and
compares exact A1/B/A2 populations. A separate manual Web adapter consumes the
existing Browser latency batch plus a diagnostic-only local last-voiced-frame
estimate; it never enters the deterministic comparer.

**Tech Stack:** TypeScript, Node.js 24, esbuild, React, WebAudio AudioWorklet,
Python 3.11 for repository checks only, Vitest/Node test runner, existing Live
Voice P1/P2 owners and latency contracts.

**Spec:**
`live-voice/roadmap/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_SPEC_2026-08-21.md`

## Global Constraints

- Work only on branch `latency_checkpoint_accepted_optimizations` in
  `/home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/latency-checkpoint-accepted-optimizations`.
- Planning base is `5b87a59927f866c9a63c0bb774e4a9e2650628b9`.
- The deterministic total is exactly `speech_end → confirmed_ack_and_next_turn_ready`.
- A1/B/A2 run W1/W2/W3 five times each, 45 attempts total, with no retry.
- A1/A2 use P2 batch size 1 plus the sequential TTS reference source; B uses
  P2 batch size 16 plus the accepted TTS-overlap source.
- Runner, fixture, sample count, delays, privacy and non-optimization config are
  identical across populations.
- `MEASURED`, `CONTROLLED`, `DERIVED`, `ESTIMATED` and `OUT_OF_SCOPE` remain
  closed, explicit truth classes in every report.
- Positive controlled waits use actual monotonic observations and accept
  lateness up to `max(25 ms, 5% of target)`; early completion is invalid.
- Raw reports are exclusive-create, mode `0600`, outside Git and contain no
  credentials, endpoint, user transcript, PCM, Provider payload, exception
  text, Session/project path or user identity.
- Deterministic runs perform zero real Agent, Tool, Provider, network, Browser,
  microphone, history or Task mutation.
- Manual Web samples use lane `manual_web_exploratory` and cannot be loaded by
  the deterministic comparer.
- Manual last-voiced-frame timing is always `ESTIMATED`; exact EOT and ACK marks
  remain separately visible.
- Default-off/unarmed/wrong-Session/stale paths have zero diagnostic and product
  side effect.
- Risk is Tier 3; independent code review precedes A1 and independent evidence
  review follows A1/B/A2.
- No remote ref update is authorized.

## File Map

- `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/acceptedOptimizationsCheckpoint.ts`:
  closed workload/config/event/attempt/report types, truth taxonomy, scheduler,
  summaries and comparison.
- `jiuwenswarm/channels/web/frontend/scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs`:
  Node CLI, real P2/P1 owner composition, private run/report/compare commands.
- `jiuwenswarm/channels/web/frontend/tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs`:
  deterministic core, owner composition, CLI/privacy and comparer tests.
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/manualLatencyCheckpoint.ts`:
  manual arm/turn ownership, Browser batch reduction, estimated speech-end and
  JSON/Markdown serialization.
- `jiuwenswarm/channels/web/frontend/tests/liveVoiceManualLatencyCheckpoint.test.mjs`:
  manual ownership, truth labels, privacy, stale/failure and download tests.
- `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceLatencyCheckpointPanel.tsx`:
  default-off diagnostic controls and result table.
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js`:
  armed-only normalized RMS/last-voiced quantum observation.
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`:
  typed content-free voice-estimate bridge.
- `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`:
  optional exact completed Browser latency-batch observer only.
- `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`:
  manual owner/panel wiring without product authority.
- `jiuwenswarm/channels/web/frontend/src/featureFlags.ts` and
  `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts`: manual feature flag.
- `jiuwenswarm/channels/web/frontend/package.json`: focused test and benchmark
  commands.
- `live-voice/runbooks/E2E_RUNBOOK.md`: manual prepare/start/arm/download/report
  procedure.
- `live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md`:
  sanitized English result after real deterministic runs.
- `live-voice/STATUS.md` and latency roadmap/brainstorm: current checkpoint and
  next-headroom facts after evidence closure.

---

### Task 1: Implement the closed checkpoint contract and deterministic clock

**Files:**
- Create: `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/acceptedOptimizationsCheckpoint.ts`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Produces `CheckpointTruthClass = 'measured' | 'controlled' | 'derived' | 'estimated' | 'out_of_scope'`.
- Produces `CheckpointWorkloadId = 'W1' | 'W2' | 'W3'` and
  `CheckpointPopulation = 'A1' | 'B' | 'A2'`.
- Produces `CheckpointPoint` as the exact `D0..D10` event-name union from the
  spec.
- Produces `CheckpointClock { nowMs(): number; waitMs(delayMs: number): Promise<void> }`.
- Produces `runCheckpointAttempt(config, dependencies): Promise<CheckpointAttempt>`.
- Produces `buildCheckpointReport(config, attempts): CheckpointReport` and
  `compareCheckpointReports(a1, b, a2): CheckpointComparison`.

- [x] **Step 1: Write the RED closed-model tests**

  Add literal tests for all five truth classes, three workloads, three
  populations, D0–D10 order, direct segment definitions and the fixed workload
  constants:

  ```javascript
  assert.deepEqual(WORKLOADS.W1, {
    id: 'W1',
    notification_count: 10,
    successor_ack_delay_ms: 250,
    playout_duration_ms: 3000,
    tool_barriers: [],
  });
  assert.equal(WORKLOADS.W3.notification_count, 100);
  assert.deepEqual(WORKLOADS.W3.tool_barriers, [40, 41]);
  ```

  The production mutation each test catches is accepting an unreviewed workload,
  changing one controlled delay or deriving total from summarized segments.

- [x] **Step 2: Run RED and verify the missing module failure**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-accepted-checkpoint
  ```

  Expected: TypeScript/module resolution fails because the checkpoint module is
  absent.

- [x] **Step 3: Implement frozen closed types and validators**

  Use literal closed records and defensive finite-number checks. Define the
  workload table exactly:

  ```typescript
  export const CHECKPOINT_WORKLOADS = Object.freeze({
    W1: Object.freeze({ notification_count: 10, successor_ack_delay_ms: 250, playout_duration_ms: 3000, tool_barriers: Object.freeze([]) }),
    W2: Object.freeze({ notification_count: 50, successor_ack_delay_ms: 750, playout_duration_ms: 6000, tool_barriers: Object.freeze([]) }),
    W3: Object.freeze({ notification_count: 100, successor_ack_delay_ms: 750, playout_duration_ms: 4000, tool_barriers: Object.freeze([40, 41]) }),
  } as const);
  ```

  Define controlled targets `400/500/2000/1000/85` ms and B batch bound `16`.

- [x] **Step 4: Write RED timing/ordering tests with a manual clock**

  Implement a test-only `ManualClock` whose `waitMs` advances exact logical
  time. Assert one literal W1 attempt produces the exact event order and direct
  total. Inject an early wait and excessive-lateness wait to prove both become
  `invalid` with stable reasons `CONTROLLED_WAIT_EARLY` and
  `CONTROLLED_WAIT_LATE`.

- [x] **Step 5: Implement attempt recorder and direct segments**

  Record every D-point once, reject duplicate/missing/rewound observations and
  compute each attempt's `round_total_ms = D10 - D0`. Store controlled targets
  separately from observations. Do not calculate total by adding stage values.

- [x] **Step 6: Write RED report/summary tests**

  Build five literal attempts with hand-derived values and assert nearest-rank
  p50/p95. Missing/failed/unknown attempts remain denominators and have no
  numeric percentile credit. Assert serialized fields carry a `truth_class`.

- [x] **Step 7: Implement report builder and A1/B/A2 comparer**

  The comparer requires exact runner/fixture/timing fingerprints, A1/A2 source
  equality and only the allowed optimization-mode differences. Emit absolute
  B−A1/B−A2 milliseconds before percentages and calculate baseline drift per
  workload/stage/total.

- [x] **Step 8: Run GREEN, TypeScript and formatting checks**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-accepted-checkpoint
  npx prettier --check \
    src/features/live-voice/benchmark/acceptedOptimizationsCheckpoint.ts \
    tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs \
    package.json
  git diff --check
  ```

- [x] **Step 9: Commit the closed contract**

  ```bash
  git add \
    jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/acceptedOptimizationsCheckpoint.ts \
    jiuwenswarm/channels/web/frontend/tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs \
    jiuwenswarm/channels/web/frontend/package.json
  git commit -m "test(live-voice): add accepted latency checkpoint contract"
  ```

---

### Task 2: Compose the real P2 and P1 owners in one attempt

**Files:**
- Create: `jiuwenswarm/channels/web/frontend/scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/acceptedOptimizationsCheckpoint.ts`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Consumes compiled `ProductWebP2ActivationOwner` and
  `ProductP1VoiceRouteOwner` through the same build route as the accepted P2
  and TTS causal runners.
- Produces `runControlledOwnerAttempt(config, ownerDependencies)` with real
  P2 parse/order/barrier behavior and real P1 downlink/ACK/next-turn join.
- Produces exact counts `A=10/50/100 RPC`, `B=1/4/8 RPC`.

- [x] **Step 1: Write RED W1 optimized-source end-to-end owner test**

  Compile the real owners and inject only controlled external seams. On the B
  source, assert W1 uses one P2 RPC and opens downlink before successor ACK. It
  must end with one confirmed ACK and exact next-turn readiness. The equivalent
  A sequential-source RED/GREEN belongs to Task 4 after that source exists; no
  runtime TTS toggle is invented in this task.

- [x] **Step 2: Verify RED against the absent composition seam**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-accepted-checkpoint -- --test-name-pattern='W1 owner composition'
  ```

  Expected: failure because `runControlledOwnerAttempt` is absent.

- [x] **Step 3: Implement exact notification fixtures**

  Generate immutable notification records with increasing `publish_seq`; W1/W2
  contain only observations before final. W3 contains Tool-start at 40,
  Tool-complete at 41 and final at 99. The fake transport models one item/RPC in
  A and barrier-bounded batches up to 16 in B; the real Web owner performs all
  parsing, validation, retention and local-tail delivery.

- [x] **Step 4: Implement controlled P1 dependencies**

  Use real P1 ownership with deterministic capture readiness, synthesis
  descriptor, downlink frames, playout scheduler and exact receipt. Emit fixed
  24 kHz PCM frame metadata without storing PCM in results. A dependency waits
  ACK before downlink; B follows the accepted source overlap behavior.

- [x] **Step 5: Add W2/W3 RED/GREEN tests**

  Assert W2 A/B RPC counts `50/4`. Assert W3 A/B counts `100/8` and exact batch
  tails `40`, `41`, `99`; no batch crosses a barrier. All workloads preserve one
  final PresentationUnit, one render, one ACK and zero Agent/Tool/Task/history
  mutation.

- [x] **Step 6: Add fault/lifecycle RED/GREEN tests**

  Cover malformed sequence, duplicate final, nested Agent error, wrong Tool
  barrier, delayed/stale ACK, downlink failure, playout failure, close during
  wait, timeout, retry/replay and late successor readiness. Each produces one
  stable terminal outcome and zero forbidden cross-scope effect.

- [x] **Step 7: Run affected owner regressions**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-accepted-checkpoint
  npm run test:live-voice-integrated-web
  node --test tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs
  npm run test:live-voice-integrated-web
  ```

- [x] **Step 8: Commit owner composition**

  ```bash
  git add \
    jiuwenswarm/channels/web/frontend/scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs \
    jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/acceptedOptimizationsCheckpoint.ts \
    jiuwenswarm/channels/web/frontend/tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs \
    jiuwenswarm/channels/web/frontend/package.json
  git commit -m "feat(live-voice): compose accepted latency checkpoint"
  ```

---

### Task 3: Close private CLI, A/B/A comparison and English rendering

**Files:**
- Modify: `jiuwenswarm/channels/web/frontend/scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Produces CLI subcommands `run`, `compare-a-b-a` and `render-markdown`.
- `run` writes `live-voice.accepted-optimizations-checkpoint.v0`.
- `compare-a-b-a` writes
  `live-voice.accepted-optimizations-checkpoint-comparison.v0`.

- [x] **Step 1: Write RED CLI and privacy tests**

  Invoke the real subprocess with valid and adversarial arguments. Require
  40-hex clean source, population, optimization mode, output path, five samples
  and the exact workload matrix. Unknown arguments, private sentinels, existing
  output and dirty source return stable tokens without echo.

- [x] **Step 2: Implement closed argument parsing and source checks**

  Use no shell, no abbreviation and no environment dump. `run` verifies HEAD
  and clean status before and after attempts. The population-mode map is exact:

  ```text
  A1/A2: p2_batch_size=1, tts_mode=sequential_reference
  B:     p2_batch_size=16, tts_mode=successor_ack_overlap
  ```

- [x] **Step 3: Write RED private-writer tests**

  Prove exclusive mode-0600 creation, failure cleanup, deep reparse, maximum
  size, no symlink/overwrite and no private fields. Inject write/link failures
  and assert no final/temporary file survives.

- [x] **Step 4: Implement atomic private report writing**

  Canonically serialize to a same-directory exclusive temporary file, fsync,
  deep-parse the complete model, then install without overwrite. Only the
  task-owned temporary file may be removed on failure.

- [x] **Step 5: Write RED comparison tests**

  Cover compatible improvement, regression, baseline drift over 10%, source
  mismatch, runner/fixture mismatch, missing workload, failed denominator and
  unapproved optimization difference. Assert totals are summarized from direct
  attempt totals.

- [x] **Step 6: Implement comparison and Markdown renderer**

  Render absolute stage/total p50/p95, B−A1/B−A2 milliseconds, percentages,
  drift and truth class. Render measured residual/proven headroom separately
  from estimated historical hypotheses. Never interpolate raw prompt or PCM.

- [x] **Step 7: Run CLI smoke and static checks**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-accepted-checkpoint
  npm run benchmark:live-voice-accepted-checkpoint -- --help
  npx prettier --check scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs \
    tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs package.json
  git diff --check
  ```

- [x] **Step 8: Commit runner closure**

  ```bash
  git add \
    jiuwenswarm/channels/web/frontend/scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs \
    jiuwenswarm/channels/web/frontend/tests/liveVoiceAcceptedOptimizationsCheckpoint.test.mjs \
    jiuwenswarm/channels/web/frontend/package.json
  git commit -m "feat(live-voice): close accepted checkpoint runner"
  ```

  Record this exact clean 40-character commit as the B checkpoint source. No
  product code may change before B unless review remediation requires it.

---

### Task 4: Review and construct the exact A reference

**Files:**
- Review all Task 1–3 paths read-only.
- Modify only in A-reference worktree:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Modify only in A-reference worktree:
  `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`
- Test existing P1/dedicated-media and checkpoint suites.

**Interfaces:**
- Produces independent Tier-3 verdict on B checkpoint source.
- Produces branch `latency_checkpoint_accepted_optimizations_a_reference` and
  its exact clean 40-character A checkpoint source.

- [ ] **Step 1: Request independent Tier-3 review**

  Review spec/plan, complete diff from `5b87a5992` to
  the exact B checkpoint source, P/N/B/S/T/C/R/I/F/K/X evidence, privacy, owner
  authority and comparer neutrality. No A1 call runs with open
  Critical/Important findings.

- [ ] **Step 2: Reproduce and remediate findings with TDD**

  Every material finding receives one causal RED before minimal remediation.
  Rerun Tasks 1–3 gates and record the final clean reviewed B source.

- [ ] **Step 3: Create the A-reference worktree**

  ```bash
  CHECKPOINT_B_SHA="$(git rev-parse HEAD)"
  test "$(printf '%s' "$CHECKPOINT_B_SHA" | wc -c)" -eq 40
  git worktree add \
    /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/latency-checkpoint-accepted-optimizations-a \
    -b latency_checkpoint_accepted_optimizations_a_reference \
    "$CHECKPOINT_B_SHA"
  ```

  The variable is resolved and length-checked from the reviewed clean HEAD in
  the same shell before worktree creation; no ambiguous ref is used.

- [ ] **Step 4: Write RED sequential-reference tests in A**

  In the A worktree, add no new permanent runner API. Run the existing accepted
  TTS A-reference assertions against current owner interfaces: downlink must
  remain unopened until successor ACK, and `duplex_media_observed` validation
  must remain truthful. Confirm current B source fails the sequential oracle.

- [ ] **Step 5: Reverse only accepted TTS product hunks**

  Use `git show` on `56a1fc4eb7` and `cd4d1b7d3` to inspect the accepted hunks,
  then use `apply_patch` only in the two production files named above. Preserve
  all later unrelated latency, identity, cleanup and receipt fixes. Do not
  restore whole historical blobs.

- [ ] **Step 6: Configure P2 baseline without code reversal**

  The A run uses server batch flag false and Web batch size 1. No P2 production
  file changes. Add an A-reference test command proving 10/50/100 RPC counts
  under this mode.

- [ ] **Step 7: Verify A/B diff closure**

  Require runner/fixture hashes identical. The product diff may contain only
  declared TTS sequential/overlap hunks; P2 differs only by run configuration.
  Run:

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-accepted-checkpoint
  npm run test:live-voice-integrated-web
  node --test tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs
  cd ../../../..
  uv run pytest tests/unit_tests/gateway/test_dedicated_media_registration.py -q
  git diff --check
  ```

- [ ] **Step 8: Commit A reference**

  ```bash
  git add \
    jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts \
    jiuwenswarm/gateway/live_voice/dedicated_media_registration.py
  git commit -m "test(live-voice): form accepted checkpoint A reference"
  ```

  Record the exact clean 40-character result as the A checkpoint source. A1
  and A2 must use it unchanged.

---

### Task 5: Execute A1/B/A2 and write the numeric English checkpoint

**Files:**
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/a1/report.json`
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/b/report.json`
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/a2/report.json`
- Create outside Git:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/comparison.json`
- Create: `live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md`

**Interfaces:**
- Consumes the exact reviewed clean A and B checkpoint source commits.
- Produces three private reports, one private comparison and one sanitized
  English evidence document.

- [ ] **Step 1: Run A1 on exact clean A**

  From the A worktree:

  ```bash
  CHECKPOINT_A_SHA="$(git rev-parse HEAD)"
  test "$(printf '%s' "$CHECKPOINT_A_SHA" | wc -c)" -eq 40
  cd jiuwenswarm/channels/web/frontend
  npm run benchmark:live-voice-accepted-checkpoint -- run \
    --population A1 \
    --mode baseline \
    --samples 5 \
    --git-commit "$CHECKPOINT_A_SHA" \
    --run-id accepted-checkpoint-a1-20260821 \
    --output /home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/a1/report.json
  ```

  Require 15/15 completed, A RPC counts 10/50/100 and clean exact settlement.

- [ ] **Step 2: Run B on exact clean optimized source**

  From the checkpoint worktree, run the same command with population `B`, mode
  `optimized`, the exact clean B HEAD obtained with `git rev-parse HEAD`, run ID
  `accepted-checkpoint-b-20260821` and B output path. Require 15/15 completed,
  B RPC counts 1/4/8, exact barriers and overlap.

- [ ] **Step 3: Run A2 on unchanged exact A**

  Return to the A worktree and repeat Step 1 with population `A2`, run ID
  `accepted-checkpoint-a2-20260821` and A2 output. Verify HEAD and runner hash
  equal A1 before execution.

- [ ] **Step 4: Compare A1/B/A2**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run benchmark:live-voice-accepted-checkpoint -- compare-a-b-a \
    --baseline-before /home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/a1/report.json \
    --candidate /home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/b/report.json \
    --baseline-after /home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/a2/report.json \
    --output /home/renan/openJiuwen-ai/live-voice-latency-runs/accepted-checkpoint-20260821/comparison.json
  ```

- [ ] **Step 5: Render and verify the English update**

  Generate the evidence file from the closed comparison, then manually verify
  every headline against private report aggregates. It must lead with absolute
  W1/W2/W3 `round_total` p50/p95 and only then percentages. Separate measured,
  controlled, derived, estimated and out-of-scope tables.

- [ ] **Step 6: Run independent evidence review**

  The reviewer recalculates p50/p95/deltas/drift, verifies direct total samples,
  hashes/mode0600, denominator, RPC/barrier counts and no forbidden effects.
  Any source-affecting remediation invalidates B and requires a rerun.

- [ ] **Step 7: Commit checkpoint evidence**

  ```bash
  git add live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md
  git commit -m "docs(live-voice): record accepted latency checkpoint"
  ```

---

### Task 6: Implement manual Browser measurement ownership

**Files:**
- Create: `jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/manualLatencyCheckpoint.ts`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoiceManualLatencyCheckpoint.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceBrowserAudioIOAdapter.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Produces `ManualLatencyCheckpointOwner` with `arm`, `observeVoiceEstimate`,
  `observeBrowserBatch`, `fail`, `close`, `snapshot`, `serializeJson` and
  `serializeMarkdown`.
- Produces capture message
  `{ type: 'latency_checkpoint_voice_estimate', capture_generation, sample_cursor, rms, sample_rate_hz, quantum_samples }` only while armed.
- Adds optional content-free `onLatencyCheckpointBatch(batch)` to the P1
  diagnostic environment after exact Browser batch settlement.

- [ ] **Step 1: Write RED manual state-machine tests**

  Assert `idle → armed → listening → response_playout → settled|failed`, one
  exact attempt per arm, no overwrite, stale/wrong Session inertness and close
  terminalization. Unarmed input produces no estimate/batch/result.

- [ ] **Step 2: Implement closed manual owner**

  Bind `session_id`, generated `attempt_id`, page epoch and one activation. It
  accepts only the exact completed Browser round. Calculate exact
  `capture_armed→ACK` and `EOT→ACK`; never subtract Gateway/Agent clocks.

- [ ] **Step 3: Write RED voice-estimator tests**

  With normalized samples, assert RMS threshold `0.02`, update only on an armed
  quantum above threshold, and emit no PCM. The estimate contains 25 ms minimum
  uncertainty and the exact quantum/sample-rate facts. Noise/invalid messages
  are inert.

- [ ] **Step 4: Implement armed-only AudioWorklet estimator**

  Add explicit `latency_checkpoint_arm`/`disarm` messages. Compute normalized
  RMS per input quantum; retain/post only numeric content-free facts. Do not
  change capture frames, cursor, gap limits or product stop behavior.

- [ ] **Step 5: Write RED P1 settled-batch observer tests**

  Prove the optional observer receives one deep-frozen completed batch after
  exact ACK/next-turn settlement, never before. Observer `BaseException` is
  contained. Feature-off/null observer produces zero new clock/storage/effect.

- [ ] **Step 6: Implement the P1 diagnostic observer**

  Invoke only after the existing batch is final and exported; pass no text/PCM
  or mutable identity. The callback cannot influence product outcome, receipt,
  retry, cleanup or presentation.

- [ ] **Step 7: Run manual-core and affected regressions**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-manual-checkpoint
  npm run test:live-voice-browser-audio-io
  npm run test:live-voice-integrated-web
  npx prettier --check \
    src/features/live-voice/benchmark/manualLatencyCheckpoint.ts \
    tests/liveVoiceManualLatencyCheckpoint.test.mjs
  ```

- [ ] **Step 8: Commit manual ownership**

  ```bash
  git add \
    jiuwenswarm/channels/web/frontend/src/features/live-voice/benchmark/manualLatencyCheckpoint.ts \
    jiuwenswarm/channels/web/frontend/tests/liveVoiceManualLatencyCheckpoint.test.mjs \
    jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js \
    jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts \
    jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts \
    jiuwenswarm/channels/web/frontend/tests/liveVoiceBrowserAudioIOAdapter.test.mjs \
    jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs \
    jiuwenswarm/channels/web/frontend/package.json
  git commit -m "feat(live-voice): add manual latency checkpoint owner"
  ```

---

### Task 7: Add the default-off manual Web panel and download flow

**Files:**
- Create: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceLatencyCheckpointPanel.tsx`
- Create: `jiuwenswarm/channels/web/frontend/tests/liveVoiceLatencyCheckpointPanel.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Modify: `jiuwenswarm/channels/web/frontend/src/featureFlags.ts`
- Modify: `jiuwenswarm/channels/web/frontend/src/vite-env.d.ts`
- Modify: `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`

**Interfaces:**
- Produces flag `VITE_FEATURE_LIVE_VOICE_LATENCY_CHECKPOINT`.
- Produces panel props `{ enabled, sessionId, owner, onArm, onDownloadJson, onDownloadMarkdown }`.
- Displays exact totals and visibly labels the local speech-end value
  `ESTIMATED ± uncertainty_ms`.

- [ ] **Step 1: Write RED flag-off and render tests**

  Assert feature-off creates no owner, AudioWorklet arm, storage read, URL or
  DOM control. Feature-on exact Session renders `Arm next turn`; null/foreign
  Session remains disabled with no product effect.

- [ ] **Step 2: Implement isolated panel component**

  Render compact diagnostic controls outside normal conversation history.
  States and buttons follow the spec. The panel never sends Agent/Tool/Task or
  controls Live Voice activation; it only arms diagnostics for the next product
  turn.

- [ ] **Step 3: Write RED arm/settle/repeat tests**

  Use real manual owner plus Panel seam. Assert one arm, one settled table,
  direct exact totals, estimate label, failed attempt visibility and repeat with
  a distinct attempt ID. A late predecessor cannot overwrite the current row.

- [ ] **Step 4: Implement JSON/Markdown downloads**

  Create a Blob only on explicit click, use a public filename containing no
  Session/prompt, revoke the object URL after click and serialize the closed
  result. No automatic upload or localStorage persistence.

- [ ] **Step 5: Wire Panel to product diagnostics**

  Create the owner only when flag-on and current active Session exists. Arm the
  audio estimator and bind P1 completed-batch callback. Unmount/session switch
  disarms and terminalizes unknown without product mutation.

- [ ] **Step 6: Run UI, build and feature-off gates**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-manual-checkpoint
  npm run test:live-voice-integrated-web
  npm run build
  npx prettier --check \
    src/components/ChatPanel/LiveVoiceLatencyCheckpointPanel.tsx \
    tests/liveVoiceLatencyCheckpointPanel.test.mjs \
    src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx \
    src/featureFlags.ts src/vite-env.d.ts package.json
  git diff --check
  ```

- [ ] **Step 7: Commit manual UI**

  ```bash
  git add \
    jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceLatencyCheckpointPanel.tsx \
    jiuwenswarm/channels/web/frontend/tests/liveVoiceLatencyCheckpointPanel.test.mjs \
    jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx \
    jiuwenswarm/channels/web/frontend/src/featureFlags.ts \
    jiuwenswarm/channels/web/frontend/src/vite-env.d.ts \
    jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanel.test.mjs \
    jiuwenswarm/channels/web/frontend/package.json
  git commit -m "feat(live-voice): add manual checkpoint panel"
  ```

---

### Task 8: Document manual execution and close the branch

**Files:**
- Modify: `live-voice/runbooks/E2E_RUNBOOK.md`
- Modify: `live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md`
- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md`
- Modify: `live-voice/roadmap/NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md`

**Interfaces:**
- Produces copyable manual start/flag/URL/arm/download/report steps.
- Produces final exact-source current-state and next-headroom ranking.

- [ ] **Step 1: Add manual Web runbook steps**

  Document normal backend/frontend start with
  `VITE_FEATURE_LIVE_VOICE_LATENCY_CHECKPOINT=true`, user-owned Browser opening,
  exact saved Session selection, `Arm next turn`, speaking, waiting for ACK,
  downloading JSON/Markdown, repeating and shutdown. State that no automatic
  Chrome launch or input WAV is used.

- [ ] **Step 2: Execute one supervised manual smoke**

  The user may perform this after implementation. If performed now, record only
  public environment classes, outcome and downloaded artifact hash. Do not
  place the manual sample in A1/B/A2 or claim physical acceptance.

- [ ] **Step 3: Update STATUS and latency routes**

  Record the combined deterministic total only after evidence review. Rank
  remaining measured B stage milliseconds separately from estimated hypotheses.
  Preserve all product-readiness and physical gaps.

- [ ] **Step 4: Run cumulative fresh verification**

  ```bash
  cd jiuwenswarm/channels/web/frontend
  npm run test:live-voice-accepted-checkpoint
  npm run test:live-voice-manual-checkpoint
  npm run test:live-voice-integrated-web
  node --test tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs
  npm run test:live-voice-browser-audio-io
  npm run build
  cd ../../../..
  uv run pytest tests/unit_tests/gateway/test_dedicated_media_registration.py -q
  uv run ruff check jiuwenswarm/gateway/live_voice/dedicated_media_registration.py
  git diff --check
  ```

- [ ] **Step 5: Request final Tier-3 review**

  Review complete implementation/history, manual default-off behavior, evidence
  truth labels, exact A/B source construction, private reports and documentation
  links. Fix every reproduced Critical/Important finding with TDD; rerun any
  source-bound population if measured source changes.

- [ ] **Step 6: Commit final documentation**

  ```bash
  git add \
    live-voice/runbooks/E2E_RUNBOOK.md \
    live-voice/evidence/LATENCY_ACCEPTED_OPTIMIZATIONS_CHECKPOINT_2026-08-21.md \
    live-voice/STATUS.md \
    live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md \
    live-voice/roadmap/NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md
  git commit -m "docs(live-voice): close accepted latency checkpoint"
  ```

- [ ] **Step 7: Prepare handoff without remote mutation**

  Report exact branch/worktree/commits, A1/B/A2 totals and stage tables,
  headroom classes, manual UI steps, tests/reviews, private report locations,
  exclusions and clean status. Do not push or merge without separate exact
  authorization.
