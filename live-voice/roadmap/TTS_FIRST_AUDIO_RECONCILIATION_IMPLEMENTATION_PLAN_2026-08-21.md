# TTS First-Audio Reconciliation and Causal Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile Hongxing's divergent TTS/successor-capture fixes, establish
a no-Chrome current-source A1, and accept or reject one current-contract
first-audio candidate through A1/B/A2.

**Architecture:** A candidate-neutral Node runner drives the real
`ProductP1VoiceRoute` with deterministic Speech, media and audio dependencies.
It varies successor-capture ACK delay independently from TTS/downlink readiness
and records PresentationUnit-to-first-source boundaries. If A1 confirms the
gate, B ports the semantics of `874cf327c` and `35cae3d9a`: downlink and
successor capture start concurrently, capture-readiness failure degrades only
interruption, and a completed playout receipt no longer depends on early duplex
media.

**Tech Stack:** TypeScript, Node test runner, existing Integrated Web
compile/test harness, Python Gateway registry tests, JSON mode-600 causal
reports, Git worktrees, pytest and Ruff.

**Spec:**
[NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md](NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md)

## Global Constraints

- Planning/reference HEAD: `9e14c3b9c0ca30f6709f88831443c71fcc612e15`.
- Exact accepted P2 candidate remains in history; do not modify its notification
  batching semantics.
- Hongxing comparison commits are `6cd8840d5`, `874cf327c`, `35cae3d9a` and
  physical tested `e1df8b452`. Inspect and port; do not cherry-pick them
  wholesale across divergent history.
- The B candidate owns the semantics of `874cf327c` plus its required receipt
  correction from `35cae3d9a`. `6cd8840d5` capture-lease rotation is excluded
  and routed separately.
- No Chrome, browser process, microphone, speaker, WebAudio device, Agent/model,
  Tool, Task mutation, VAD threshold change, sentence streaming, cache or
  adaptive playout implementation in this packet.
- Browser-owner TypeScript runs under Node with deterministic fakes. This grants
  component evidence only, never physical first-audible credit.
- Raw reports remain outside Git, use exclusive create and mode 600, and contain
  no text, PCM, credentials, tickets, device IDs, URLs or exception strings.
- A1/B/A2 use identical runner source, fixtures and injected delays. A1 and A2
  run on the exact same reference commit.
- Risk: Tier 3 because B changes cross-Web/Gateway playout-receipt authority and
  cancellation/recovery semantics.
- Every failure path asserts zero Agent, Tool, Task, history, duplicate TTS,
  revived audio and foreign-scope effects.

---

## Task 1: Cold reconciliation of Hongxing TTS/capture changes

**Files:**

- Create:
  `live-voice/reviews/TTS_CAPTURE_RECONCILIATION_REVIEW_2026-08-21.md`
- Read only: current source and `git show` for `6cd8840d5`, `874cf327c`,
  `35cae3d9a`, `e1df8b452`

**Interfaces:**

- Consumes: current `ProductP1VoiceRoute`, Gateway downlink receipt owner and
  the three historical evidence records on the Hongxing commits.
- Produces: a closed hunk disposition table used by Tasks 3 and 4:
  `port`, `already_present`, `superseded`, `exclude`.

- [ ] **Step 1: Freeze current and divergent source facts**

Run:

```bash
git status --short --branch
git rev-parse HEAD
for commit in 6cd8840d5 874cf327c 35cae3d9a e1df8b452; do
  git cat-file -e "$commit^{commit}"
  git merge-base --is-ancestor "$commit" HEAD && echo "$commit present" || echo "$commit absent"
done
git diff --stat 6cd8840d5..874cf327c
git diff --stat 874cf327c..35cae3d9a
```

Expected: all commits resolve; the four Hongxing commits are absent from the
current ancestry; worktree is clean.

- [ ] **Step 2: Compare only the owning hunks**

Run:

```bash
git diff 6cd8840d5..874cf327c -- \
  jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts \
  jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx \
  jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx \
  jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs

git diff 874cf327c..35cae3d9a -- \
  jiuwenswarm/gateway/live_voice/dedicated_media_registration.py \
  jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts \
  jiuwenswarm/channels/web/frontend/src/services/webClient.ts \
  tests/unit_tests/gateway/test_dedicated_media_registration.py \
  jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs
```

For every changed function, record current line/function, historical intent,
current equivalent and disposition. Do not copy STATUS/history hunks.

- [ ] **Step 3: Write the reconciliation review**

The review must include this exact table shape:

```markdown
| Historical commit/function | Current owner | Disposition | Reason / required oracle |
|---|---|---|---|
| `874cf327c::playAgentText` | `productP1VoiceRoute.ts` | `port` | downlink must not await successor ACK |
| `35cae3d9a::complete_downlink` | `dedicated_media_registration.py` | `port` | receipt completion independent of early duplex observation |
| `6cd8840d5::capture rotation` | separate packet | `exclude` | recovery/lease scope, not first-audio candidate |
```

Also record which old tests remain semantically applicable versus superseded by
current generation/latency ownership.

- [ ] **Step 4: Verify and commit Task 1**

```bash
git diff --check
git add live-voice/reviews/TTS_CAPTURE_RECONCILIATION_REVIEW_2026-08-21.md
git commit -m "docs(live-voice): reconcile TTS capture latency fixes"
```

---

## Task 2: Candidate-neutral TTS first-audio benchmark

**Files:**

- Create:
  `jiuwenswarm/channels/web/frontend/scripts/liveVoiceTtsFirstAudioCausalBenchmark.mjs`
- Create:
  `jiuwenswarm/channels/web/frontend/tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs`
- Modify: `jiuwenswarm/channels/web/frontend/package.json`
- Modify only for test export when unavoidable:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`

**Interfaces:**

- Produces CLI:

```text
npm run benchmark:live-voice-tts-first-audio -- \
  --output ABSOLUTE_NONEXISTENT_JSON \
  --git-commit 40_LOWER_HEX \
  --run-id PUBLIC_TOKEN \
  --samples 5
```

- Produces report schema
  `live-voice.tts-first-audio-causal-report.v0`.
- Task 3 consumes the exact clean runner commit and report.

- [ ] **Step 1: Write RED closed-CLI/report tests**

Test exact arguments, absolute/nonexistent output, clean/matching Git commit,
run ID, `samples=5`, exclusive mode-600 output and stable private failure token.

```javascript
test('TTS causal CLI freezes the four populations and private report', async () => {
  const config = parseArgs(validArgs({ samples: 5 }));
  assert.deepEqual(config.successorAckDelaysMs, [0, 250, 750, 1100]);
  assert.equal(config.samples, 5);
  await writeReport(config.output, completeReport(config));
  assert.equal((fs.statSync(config.output).mode & 0o077), 0);
  assert.throws(() => writeReport(config.output, completeReport(config)), /OUTPUT_EXISTS/);
});
```

- [ ] **Step 2: Run RED**

```bash
cd jiuwenswarm/channels/web/frontend
node --test tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs
```

Expected: fail because the runner does not exist.

- [ ] **Step 3: Implement closed config and report types**

The report contains only:

```javascript
{
  schema_version,
  run_id,
  git_commit,
  source_clean: true,
  candidate_mode: 'legacy_sequential' | 'successor_ack_decoupled',
  samples: 5,
  populations: [{ successor_ack_delay_ms: 0|250|750|1100, attempts: [...] }],
  summaries,
  decision,
  forbidden_effects
}
```

Each attempt contains outcome/reason and numeric content-free points:

```text
presentation_received_ms
tts_request_started_ms
tts_descriptor_ready_ms
successor_capture_requested_ms
successor_first_ack_ms | null
downlink_opened_ms
downlink_first_frame_received_ms
first_source_scheduled_ms
playout_receipt_accepted_ms
```

Allowed outcomes are `completed|degraded_interruption|failed|invalid|unknown`.
Failed/invalid/unknown attempts carry no comparison latency samples.

- [ ] **Step 4: Write RED real-owner journey tests**

Instantiate the real `ProductP1VoiceRoute` with deterministic current-product
Speech/media/audio fakes. Drive one exact authoritative response and assert:

```javascript
assert.equal(attempt.tts_request_started_ms, 0);
assert.equal(attempt.successor_first_ack_ms, injectedAckDelay);
assert.ok(attempt.first_source_scheduled_ms >= attempt.downlink_opened_ms);
assert.equal(effects.agent, 0);
assert.equal(effects.tool, 0);
assert.equal(effects.task, 0);
assert.equal(effects.history, 0);
```

Legacy 1100 ms ACK must reproduce the current bounded startup failure and stay
in the denominator. The benchmark must not encode candidate success as its
oracle.

- [ ] **Step 5: Implement deterministic runner composition**

Reuse current test fakes/build helpers rather than copying product logic.
Inject one monotonic manual clock and schedule descriptor, ACK, downlink frame
and first-source callbacks against absolute deadlines. Count every request and
audio source. Do not invoke a shell, network, Provider or Browser.

- [ ] **Step 6: Add benchmark package command**

Add:

```json
"benchmark:live-voice-tts-first-audio": "tsc src/features/live-voice/formal/productP1VoiceRoute.ts --target ES2020 --module ES2020 --moduleResolution Bundler --rootDir src --outDir node_modules/.cache/live-voice-integrated-web --lib ES2020,DOM --skipLibCheck --noEmitOnError --strict --noUnusedLocals --noUnusedParameters && node scripts/liveVoiceTtsFirstAudioCausalBenchmark.mjs"
```

Use the same strict compiler flags as the existing P2 benchmark command.

- [ ] **Step 7: Run GREEN and affected regressions**

```bash
cd jiuwenswarm/channels/web/frontend
node --test tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs
node --test tests/productP1VoiceRoute.test.mjs
npm run test:live-voice-integrated-web
npx tsc --noEmit
npx prettier --check scripts/liveVoiceTtsFirstAudioCausalBenchmark.mjs tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs
git diff --check
```

- [ ] **Step 8: Commit Task 2**

```bash
git add \
  jiuwenswarm/channels/web/frontend/package.json \
  jiuwenswarm/channels/web/frontend/scripts/liveVoiceTtsFirstAudioCausalBenchmark.mjs \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs \
  jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts
git commit -m "test(live-voice): add TTS first-audio causal benchmark"
```

---

## Task 3: Clean A1 and candidate eligibility decision

**Files:**

- Private create:
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-first-audio/$RUN_ID/report.json`
- Create:
  `live-voice/evidence/TTS_FIRST_AUDIO_A1_RESULT_2026-08-21.md`

**Interfaces:**

- Consumes the committed Task 2 runner on one clean exact reference.
- Produces decision `NO_MATERIAL_SUCCESSOR_ACK_GAP` or
  `SUCCESSOR_ACK_DECOUPLING_ELIGIBLE`.

- [ ] **Step 1: Freeze one clean A1 source**

```bash
git status --porcelain --untracked-files=all
git rev-parse HEAD
```

Require empty status. Record exact Node version and runner hash without private
machine paths in committed evidence.

- [ ] **Step 2: Run A1**

```bash
cd jiuwenswarm/channels/web/frontend
RUN_ID="tts-a1-$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short=10 HEAD)"
RUN_DIR="/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-first-audio/$RUN_ID"
install -d -m 700 "$RUN_DIR"
npm run benchmark:live-voice-tts-first-audio -- \
  --output "$RUN_DIR/report.json" \
  --git-commit "$(git rev-parse HEAD)" \
  --run-id "$RUN_ID" \
  --samples 5
```

- [ ] **Step 3: Apply A1 materiality gate**

The candidate is eligible when either delayed-success population (250 or
750 ms):

- has 5/5 valid attempts;
- successor readiness is on the first-source critical path;
- `presentation → first source scheduled` p50 contains at least 200 ms and 15%
  attributable successor-ACK wait against the 0 ms population;
- A1 1100 ms reproduces capture-readiness failure without forbidden effects.

Otherwise record `NO_MATERIAL_SUCCESSOR_ACK_GAP`, stop product implementation
and route Task 6 documentation directly to TTS Provider prewarm.

- [ ] **Step 4: Commit sanitized A1 evidence**

```bash
git add live-voice/evidence/TTS_FIRST_AUDIO_A1_RESULT_2026-08-21.md
git commit -m "docs(live-voice): record TTS first-audio A1"
```

---

## Task 4: Port the current-contract TTS/capture candidate

**Condition:** Execute only if Task 3 returns
`SUCCESSOR_ACK_DECOUPLING_ELIGIBLE`.

**Files:**

- Modify:
  `jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts`
- Modify:
  `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx`
- Modify only if projection requires:
  `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx`
- Modify:
  `jiuwenswarm/gateway/live_voice/dedicated_media_registration.py`
- Modify only for stable direct Gateway reason:
  `jiuwenswarm/channels/web/frontend/src/services/webClient.ts`
- Test:
  `jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs`
- Test:
  `jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`
- Test:
  `tests/unit_tests/gateway/test_dedicated_media_registration.py`

**Interfaces:**

- Preserves public `playAgentText(...): Promise<void>` and existing playout
  receipt wire shape.
- Produces internal successor readiness state
  `pending|ready|degraded` with stable content-free reason.
- `duplex_media_observed` remains an existing boolean fact; false cannot reject
  an otherwise exact completed playout receipt.

- [ ] **Step 1: Write RED concurrency-order tests**

Required cases:

```text
ACK at 0 ms: downlink and capture start; exact one render/receipt
ACK at 250/750 ms: downlink opens before ACK; barge-in becomes ready later
ACK at 1100 ms: TTS renders; interruption degrades; late ACK cannot revive
no frame/no ACK/device failure: exact capture authority revoked, TTS preserved
cancel during startup: both branches fenced; old downlink/source remains zero
```

Assert `downlink_opened_ms < successor_first_ack_ms` for delayed ACK and zero
Agent/Tool/Task/history calls in every failure/degradation case.

- [ ] **Step 2: Run Web RED**

```bash
cd jiuwenswarm/channels/web/frontend
node --test --test-name-pattern='successor ACK|interruption degradation|late ACK' tests/productP1VoiceRoute.test.mjs
```

Expected: current source waits for ACK or fails before opening downlink.

- [ ] **Step 3: Implement concurrent startup owner**

In `playAgentText`, start exactly two retained operations:

```typescript
const successor = this.#startConcurrentCapture(operationGeneration, latencyRound);
const downlink = this.#openAuthoritativeDownlink(/* exact existing bindings */);
```

Do not `await successor` before opening downlink. Set `playing` only after the
audio adapter schedules the first exact source. Settle successor readiness in a
bounded owner: ready preserves barge-in; no-frame/no-ACK/startup failure stops
and revokes only that successor and publishes degraded interruption. Current
generation/cancel fences own both promises.

- [ ] **Step 4: Write RED Gateway receipt tests**

Drive exact short downlink completion under:

```text
successor accepted frame before completion → duplex_media_observed=true
no successor frame before completion → duplex_media_observed=false, receipt accepted
successor frame only after completion → retained receipt unchanged false
wrong binding/malformed/incomplete downlink → rejected
```

- [ ] **Step 5: Run Gateway RED**

```bash
uv run pytest tests/unit_tests/gateway/test_dedicated_media_registration.py -q --no-cov -k 'early_duplex or playout_receipt'
```

Expected: no-early-duplex exact receipt is currently rejected.

- [ ] **Step 6: Implement receipt truth separation**

Make downlink completion depend on exact authorized transport, frame/queue and
browser render facts, not on successor uplink activity. Return the already
declared `duplex_media_observed` boolean from the retained observation. Preserve
all identity, origin, activation, content-hash, idempotency and replay checks.

- [ ] **Step 7: Run Task 4 focused and cumulative checks**

```bash
uv run pytest tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/live_voice/test_streaming_speech_route.py tests/unit_tests/live_voice/test_openai_streaming_speech.py -q --no-cov
uv run ruff check jiuwenswarm/gateway/live_voice/dedicated_media_registration.py tests/unit_tests/gateway/test_dedicated_media_registration.py
cd jiuwenswarm/channels/web/frontend
node --test tests/productP1VoiceRoute.test.mjs tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
npm run test:live-voice-browser-audio-io
npm run test:live-voice-integrated-web
npx tsc --noEmit
git diff --check
```

- [ ] **Step 8: Commit Task 4**

```bash
git add \
  jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts \
  jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx \
  jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx \
  jiuwenswarm/channels/web/frontend/src/services/webClient.ts \
  jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs \
  jiuwenswarm/channels/web/frontend/tests/liveVoiceIntegratedRoutePanelMounted.test.mjs \
  jiuwenswarm/gateway/live_voice/dedicated_media_registration.py \
  tests/unit_tests/gateway/test_dedicated_media_registration.py
git commit -m "perf(live-voice): decouple TTS from successor capture"
```

---

## Task 5: B, unchanged-source A2 and independent Tier-3 review

**Files:**

- Private create: B and A2 reports under
  `/home/renan/openJiuwen-ai/live-voice-latency-runs/tts-first-audio/`
- Create:
  `live-voice/evidence/TTS_FIRST_AUDIO_CAUSAL_RESULT_2026-08-21.md`

**Interfaces:**

- Consumes exact A1 runner/reference and one Task 4 B commit.
- Produces `SUCCESSOR_ACK_DECOUPLING_ACCEPTED|REJECTED|INCONCLUSIVE`.

- [ ] **Step 1: Run B on the candidate commit**

Use the exact Task 2 command/fixtures. Require 20/20 attempts to be completed
or declared `degraded_interruption` only for the 1100 ms population; no failed,
invalid or unknown attempt receives latency credit.

- [ ] **Step 2: Run A2 in a clean detached/reference worktree**

Run the exact A1 commit, runner, delays and machine. A2 p50 must remain within
10% of A1 per population and have identical outcome counts.

- [ ] **Step 3: Compare stage-by-stage**

B is accepted only when:

- delayed 250/750 ms first-source p50 improves by ≥200 ms and ≥15% against A1
  and A2;
- immediate-ACK p50/p95 regress by no more than 20 ms;
- 1100 ms changes only from startup failure to truthful interruption
  degradation while audio renders exactly once;
- TTS descriptor/downlink/first-frame waits are not displaced later;
- every attempt has exact cleanup and zero forbidden effects.

- [ ] **Step 4: Request independent Tier-3 review**

Review the complete Task 1–4 diff and raw/sanitized A1/B/A2 structure. Remediate
every Critical/Important through RED/GREEN; rerun only affected deterministic
checks and any causal population whose semantics changed.

- [ ] **Step 5: Write and commit sanitized result**

Record exact commits/run IDs, Node/runtime labels, per-population counts,
stage p50/p95, decision and no-Chrome limitation.

```bash
git add live-voice/evidence/TTS_FIRST_AUDIO_CAUSAL_RESULT_2026-08-21.md
git commit -m "docs(live-voice): record TTS first-audio causal result"
```

---

## Task 6: Current documentation synchronization and handoff

**Files:**

- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md`
- Modify:
  `live-voice/roadmap/NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md`
- Modify this plan's checkboxes/result note.

- [ ] **Step 1: Update only current owning facts**

If no material A1 gap, route next to TTS Provider prewarm. If B is accepted,
record causal component credit and keep physical Chrome first-audible open. If
rejected/inconclusive, preserve current product behavior and exact reason.

- [ ] **Step 2: Run final verification**

```bash
uv run pytest tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/live_voice/test_streaming_speech_route.py tests/unit_tests/live_voice/test_openai_streaming_speech.py -q --no-cov
uv run ruff check jiuwenswarm/gateway/live_voice/dedicated_media_registration.py tests/unit_tests/gateway/test_dedicated_media_registration.py
cd jiuwenswarm/channels/web/frontend
node --test tests/liveVoiceTtsFirstAudioCausalBenchmark.test.mjs tests/productP1VoiceRoute.test.mjs tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
npm run test:live-voice-browser-audio-io
npm run test:live-voice-integrated-web
npx tsc --noEmit
git diff --check
```

- [ ] **Step 3: Verify documentation structure and commit**

Check changed relative Markdown links, no duplicate under `docs/zh/live-voice`,
private reports untracked and product default VAD unchanged.

```bash
git add live-voice/STATUS.md live-voice/roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md live-voice/roadmap/NON_AGENT_P1_P2_P3_LATENCY_OPTIMIZATION_BRAINSTORM_2026-08-21.md live-voice/roadmap/TTS_FIRST_AUDIO_RECONCILIATION_IMPLEMENTATION_PLAN_2026-08-21.md
git commit -m "docs(live-voice): route after TTS first-audio experiment"
```

## Completion gate

- Reconciliation records every applicable Hongxing hunk without blind
  cherry-pick or unrelated historical reintroduction.
- Candidate-neutral runner uses the real product owner under Node and produces
  closed, private, exact-source reports.
- A1 decides materiality before product changes.
- B changes only successor-capture/downlink/receipt ownership required by the
  accepted candidate.
- A1/B/A2 compare identical fixtures and preserve exact response, audio,
  receipt, generation and cleanup truth.
- Independent Tier-3 review has no remaining Critical/Important finding.
- No Chrome/device/physical or end-to-end credit is claimed.
- The next owner is explicit: accepted physical confirmation later, or TTS
  prewarm immediately if no material/candidate gain exists.
