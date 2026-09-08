# Realtime six-hour repair execution boundary

User-authorized execution began 2026-09-07 23:55:37 UTC (2026-09-08
01:55:37 Europe/Paris); delivery target is 05:55:37 UTC / 07:55:37 Paris.
The user's later instruction selects the current checkout, not the D: path in
the input snapshot. Baseline: `d8ee9e6d39ea6cc73994b5dd86d3d3662bc43ae1`, clean,
`hx/0812_live_voice_w3`, 0/0 against local `origin/hx/0812_live_voice_w3`.
The three later input-snapshot commits are not present at this baseline.

## Selected implementation and ownership

Main is the sole filesystem writer and Integration Owner. Start with the
existing transport; do not introduce WebRTC or an AudioWorklet replacement
without measurements demonstrating that the repaired supply needs it.

| Boundary | Intended behavior and owned source/tests | Risk and acceptance |
|---|---|---|
| A: prepared supply | Native Engine and continuation tests: sample-accounted absolute delivery deadlines with at most 320 ms available catch-up credit, cooperative control priority, existing bounded source/transport backpressure | Tier 2. Same-byte replay is contiguous, exactly once, no per-frame processing drift; STOP preempts buffered PCM, stale generation never revives |
| B: diagnostics | Common diagnostics/log sanitization and their tests; media route observations: retain redaction while avoiding quadratic key matching and repeat sanitization of unchanged LogRecords; keep bounded collection and observable drops | Tier 3 security-preserving performance change. Credential/PII cases and mutated records remain masked; diagnostic-on yielding-I/O load, CPU/loop lag and bounded queue compared to off |
| C: admission | Registry/Native Runtime/media registration and owned tests: observe lock wait/holder chain, isolate media from unrelated business waits; exact admission precedes all PCM | Tier 3 candidate. Preserve cancellation, per-generation authorization, retry, actual-playout ACK and heard history. Refine implementation scope from lock evidence before changing authority |
| D: notification | Gateway media registration/app gateway and notification tests: Native-ready wakes the exact pending owner without shortening business polling or competing consumers | Tier 3 candidate. Sequence, exact request ownership, duplicate, simultaneous result, close/recovery and wrong-scope zero-effect checks required |
| E: endpoints/device | Native configuration/launcher, browser audio observations and owned tests: requested gpt-realtime-2.1, speed 1.25; measured endpoint and reserve changes only | Tier 2 configuration; any new protocol is Tier 3. Provider confirms actual values; physical timing and interruptions are required for experience credit |
| F/G/H: business | Native Engine/router/tools and owned tests: authentic minimal receipt can trigger concise speech without full-context refresh; future mutation still uses fresh authorization/revision; evaluate argument/durable-acceptance work from actual source | Tier 3 candidate. Pending, accepted, spoken and completed remain distinct; no duplicate Task, fabricated result, internal tool speech, or stale-fact authorization |

Dependencies: current private Provider/Agent selection, registered Code project,
preserved data, actual service ownership and current assets. Existing model and
project configuration must be inventoried without logging credentials. This
machine's initial runtime contract says gpt-realtime-2 and has no speed field;
the requested 2.1/1.25 must be implemented and explicitly verified, not claimed
as already active. No CUA, mouse/keyboard automation, push, history rewrite,
Task/file deletion, account changes, new services or data migration.

A's control-priority regression exposed the shared Realtime session receive
wrapper's extra per-event child task. Include that kernel receive method and
session timeout/cancel regressions in A's Tier-2 boundary: retain one receiver,
the same bounded timeout, idle retry and typed failures, using Python's current-
task timeout scope. This does not change Provider or media protocol semantics.

Use root TESTING.md's applicable P/N/B/S/T/C/R/I/F/K/X dimensions and independent
module review. Deterministic checks do not satisfy real Provider, Agent/Task/file,
browser or physical acceptance. Real-path scope and final outcome belong in
the current acceptance record; raw logs/audio stay under ignored local paths.

## Evidence inventory and measurement

### C implementation checkpoint

First retain per-batch Runtime admission and its exact audio authority. Add
passive wait/holder spans to the existing Registry and default Native Runtime
locks. For notification requests, move external authority preparation/lease
cleanup outside the global Registry critical section, capturing the exact
route or retained replay binding first and rechecking it under the lock before
publishing any operation. Authorization is not cached for later mutations.
Replays retain their original binding, sequence and fingerprint; a retired or
replaced route cannot gain a new notification operation after the async read.
Owner: Composition Registry/Native Runtime, Tier 3. Tests cover concurrent
audio admission, cancellation during auth, close/replacement, replay conflict,
sequence bounds and existing notification/Native regressions. A blocked
authorization fixture is mechanism evidence, not attribution of the old spikes.
Reply-level media authority and removing per-batch RPC remain contingent on
real measurements; they are not silently introduced in this child repair.

C checkpoint validation: `c-before-tests.txt` reproduces audio admission and
route close blocked behind authorization (2 failures/1 pass). The fixed races,
including same-binding owner replacement, real replay-ledger eviction, identical
concurrent replay and conflicting fingerprint, plus passive-lock cancellation
and sink failure checks pass: `c-race-tests.txt`, 9 passed. Snapshots include
notification sequence/consumption, Native audio/heard history, operation ledgers,
actual Agent facade calls and P3 semantic/query/retry admission calls.
The full Registry comparison is **not green**: 68 existing failures are identical
on `f2d3cdc7` and C; the baseline additionally fails the two new blocking cases.
Retain these failures, specifically completed terminal notification heard-history,
for integration attribution. Read-only independent review found no new code
blocker; its interleaving/actual-Agent-call evidence requests were incorporated.

At 02:30 Paris the existing remote-tracking ref acquired the three exact commits
named by the user's packet (`f08cd261`, `fc02124e`, `d5e9083b`). They were absent
at initial inspection. Integrate this task baseline locally after the C checkpoint,
preserving A/B/C, then rebind tests and deployment to the resulting candidate.
No remote update is authorized or performed.

Local baseline integration passed 494 coherent module checks and independent
merge review; A/B/C remain intact. Actual Provider speed is still unverified.

### D implementation checkpoint

Tier 3 refinement of the authorized notification-wake boundary: introduce one
closed Gateway-to-AgentServer `live-voice.native-notification-wake.v1` request
over the existing private Native carrier. It carries exact activation capability
and response identity, no PCM, task action or browser authority. Only a current
Native response with admitted audio can set one idempotent wake per response.
Gateway queues its local audio descriptor before scheduling this bounded,
session-owned wake. Audio supply does not await the wake RPC.

The existing exact Conversation Runtime consumer receives a wake signal in its
notification buffer wait. It returns the existing transport keepalive without
popping any business notification; the browser's next serialized request can
take the already queued Native descriptor. No second consumer, retained result
queue, shortened poll, fabricated ACK or history write is introduced. Close and
generation replacement fence both the consumer and wake. Required checks cover
simultaneous business readiness, idle and active polls, duplicate/invalid/stale
wakes, cancelled callers, exact sequence replay, bounded Gateway helper cleanup
and unchanged playback authority. Owned surfaces: private Native carrier/client,
Registry, P2 lease, Conversation notification buffer, Native runtime observation,
Gateway session lifecycle and their focused tests. Real RPC timing remains a
separate required measurement.

D checks: 51 core/client cases pass; six-file boundary run reaches 376 passes
with two new Gateway cases blocked by a missing test Origin configuration.
After adding that explicit fixture, all 3 new Gateway cases pass, giving 378
distinct passing boundary cases. The first combined collection also exposed a
duplicate test basename; renamed the Gateway test before boundary execution.
Independent review found no product blocker. Tests prove the retained poll can
wake within a 150 ms test deadline, simultaneous business notifications remain
queued, duplicate/stale/foreign wakes have no new effect, and a blocked/failed
wake does not stop three real fixture PCM frames or session cleanup. These are
controlled tests, not real network or physical latency results.

Provider configuration probe: all four real sessions confirm model
`gpt-realtime-2.1`, speed `1.25`, `inf` output budget, and semantic VAD with
automatic response creation/interruption disabled. Provider accepted omitted,
minimal and low reasoning, plus auto/high VAD. The omitted effort is returned
as absent, not inferred to be low. Every session's retained close completes on
retry with no close error; the first 25 ms wait alone is not closure evidence.
Raw whitelisted observations: `logs/repair-20260908/provider-configuration.json`.
No credentials, Provider IDs or prompts are copied to that evidence. No latency
or semantic-quality credit is assigned to these negotiation-only probes.

### F implementation checkpoint

Tier 3, bounded Task-create acceptance fast path only. For an exact server
`task.create`/`task.create_successor` result with a matching real Task ID and
an accepted receipt, seal and return the existing durable journal result before
optional full context refresh. Do not remove admission/final authority reads or
change Task execution/outbox ownership. Existing background observation owns
the subsequent context refresh and Task discovery.

Engine may create a concise acceptance response once every call
in that response has such a durable acceptance receipt. It skips the redundant
full-context read only for this response. It exposes only `context.get` with
automatic tool choice: acknowledge a satisfied request briefly, or fetch fresh
context before continuing remaining dependent steps. The Runtime checks the
parsed operation before any delegate admission; it cannot mutate through this
fast response. The next context result restores the normal full tool chain.
Work results, argument correction,
queries and multi-operation continuations retain fresh-context sequencing.
The receipt's own fields are the sole speech facts. Later mutations retain the
existing server context/revision/membership checks; interruption still retires
speech without cancelling accepted Tasks. Prepared promotion keeps its existing
fresh-authority fence. Owned surfaces: Native receipt representation, Router,
Engine scheduler and acceptance/replay/negative tests. Check blocked optional
refresh, durable Task/journal counts, duplicate/rejected/wrong-source receipts,
future action freshness and unchanged work continuations.

Independent review caught that an initial forced no-tools response would stop
multi-step requests that depend on the newly accepted Task ID. That version was
not committed or deployed. The context-only continuation above repairs the
semantic regression and is covered by a dependent-followup test. The initial
coherent boundary had 334 passing cases; the revised acceptance and existing
Engine checks passed 187 cases (`f-followup-final-tests.txt`). The added case
continues through fresh context; direct mutation is rejected based on its parsed
operation. Independent review closed the P1 after this verification. No real
acceptance-speech timing is claimed from this controlled test.

The input's September 8 latency directory, 292-second clip, diarized audio,
original project and data directory are absent on this host. Its 15 timestamps
and baseline figures are supplied historical evidence, not independently
recomputed here. Current logs/runtime contract and four listening service ports
exist. Preserve all failures and report unavailable original-PCM/output linkage.

Associate turn/response/source_event/generation; subtract monotonic values only
inside one clock_id. Report ordinary answers, tool prefeedback, accepted speech,
durable Task acceptance and artifacts separately, with sample count/P50/P95/max.
Production diagnostics remain enabled in the on condition. Candidate targets
and the six product requirements are those in the user-supplied execution prompt.

## Physical acceptance preparation

One consolidated operator script is provided in
[the local acceptance script](../../logs/repair-20260908/PHYSICAL_ACCEPTANCE.md).
Run after the exact candidate's controlled deployment has passed readiness.
Until then implementation continues independently. No automation operates the
user's browser or devices.
