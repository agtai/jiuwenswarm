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

### Recovery regression checkpoint

Tier 3, existing foreground/notification durability boundary. Independent review
of the 68 Registry and 24 frontend baseline failures found actual recovery bugs:
an unknown unified text input is mistaken for an already accepted foreground on
reconnect; an exact failed response can be popped and discarded when its polling
effect retires; and notification label lookup incorrectly requires an unread
historical event to belong to the Task's current attempt. Repair these within
existing identities and authority. Replay the exact retained unified input
without retiring its accepted foreground; admit an exact current failed response
through the existing response fence; read scoped Task label metadata separately
from exact terminal result/attempt authority. No new intent classifier, guessed
ACK or event watermark is allowed. Owned product surfaces: integrated React
panel, Registry and authenticated P3 metadata read; tests retain wrong-scope,
duplicate, retry, unread predecessor, no-ACK/no-history and current-owner oracles.
Tests with obsolete fake signatures or removed UI controls need explicit current
contract replacements; baseline failure alone is not an exemption.

The three product repairs and exact history fake binding pass independent
read-only review. Review caught and fixed the Task projection callback missing
its post-await activation fence and an initially misplaced history assertion.
Final affected checks: 15 backend and 30 frontend Native/reconnect/failed-response
cases pass, including explicit zero effects for foreign response/generation
failures and no P2 close during unified replay. TypeScript typecheck passes.
Broader current runs: Registry/P3 346 pass, 59 fail; frontend 692 pass, 20 fail,
1 skip. The 59 include 55 Registry semantic/retired-entry fixture cases and four
P3 cases. Existing lifecycle model fixtures default to dialogue and supply no
Task facts; they cannot prove the requested Task scenarios. The independent
audit identifies current semantic-model/SQLite migration anchors, not an
exemption. Remaining frontend cases include removed natural Task controls,
instantaneous-state assumptions and unresolved composite recovery scenarios.
These broad scopes remain PARTIAL. Raw commands/results are retained under
`logs/repair-20260908/recovery-*`.

### E controlled configuration checkpoint

Tier 1 configuration boundary: expose optional Provider reasoning effort for the
authorized latency/quality A/B (`provider-default`, `minimal`, `low`). Omitted
effort remains omitted; do not infer the Provider default or change models.
Validate the closed setting before connection, pass it through the existing
Gateway Engine factory and controlled launcher, and persist requested settings
in the runtime contract. Observe only whitelisted negotiated model/speed/VAD/
effort/output-budget facts from `session.updated`, never prompts, tools or keys.
Tests cover default/explicit modes, invalid values before Provider effects,
Cascade isolation and actual session.update payload. This change does not select
the winning mode; real latency and semantic evidence must justify that decision.

Configuration/Engine/Session checks: 295 pass; existing endpoint, output-budget
and diagnostic privacy checks: 29 pass. PowerShell parser reports no errors.
The source diff was reviewed at this Tier 1 boundary. The Provider's confirmed
settings are observed once after exact session-ID negotiation and cannot change
the negotiated result or record raw instructions/tools/credentials. Real
configured-service A/B remains pending; no effort mode is selected by these tests.

The first controlled candidate `eaf5382066` deployed cleanly at 01:19 UTC with
real speech readiness, all four ports, `gpt-realtime-2.1`, speed 1.25, auto VAD,
inf output budget and unchanged deepseek-v4-flash Agent configuration. No GUI
was operated. Public RPC/media baseline recordings exercised real Provider audio,
Task execution and file creation on the preceding d8ee9e6d deployment. One
ordinary turn received first PCM 2759 ms after synthetic acoustic end; a Task
receipt took 10098 ms. These are n=1 measurements per class, not physical playout.
The real Task completed but its instruction changed the transcribed filename
from 基线 to 记叙; the resulting file is therefore not a business-acceptance pass.
All existing project files and hashes were retained. The first probe failed on
Windows stdout encoding and is explicitly excluded from successful measurements.

One consolidated operator script is provided in
[the local acceptance script](../../logs/repair-20260908/PHYSICAL_ACCEPTANCE.md).
Run after the exact candidate's controlled deployment has passed readiness.
Until then implementation continues independently. No automation operates the
user's browser or devices.
## G implementation checkpoint: one complete intent and frozen sent context

Tier 3 Provider adapter boundary, Main sole writer. The accepted packet explicitly
forbids adding an ASR wait to the interaction critical path. Therefore this change
does not wait for transcription or create a transcript-dependent call queue.
The new closed `jiuwen_bound_*` schemas carry one complete `request_text`; for
create/successor/start/update it is also the exact executable `instruction`, and
for adjustment it is the exact `adjustment`. The common text retains the existing
4096 UTF-8 byte action limit. Names, exact targets and revisions remain explicit.
No summarizer, classifier, guessed filename, inferred target or relaxed validator
is added. Legacy full-field calls retain their existing strict parser.

The Engine freezes the exact committed Native turn and the context ID most
recently successfully sent to Provider. Context publication and response creation
share one short send-sequence lock; the immutable binding is installed on the
inflight request before the socket send await and copied on response.created.
Only metadata publication/send is locked, never context refresh, Agent or Task I/O.
Canonical v1, Router authorization/final checks, journal and durable Task/outbox
remain owners of execution truth. Supplied extra context/instruction fields in
bound calls reject closed. Existing STOP, prepared admission, duplicate identity
and receipt-only context.get guards remain binding.

Acceptance covers all 13 schemas, UTF-8/closed fields, exact original requirements,
stale context, delayed response.created, concurrent context publication, same-turn
successors, prepared continuation and unchanged legacy/Cascade. Real parameter
duration and durable receipt latency will be measured after deployment. Physical
audio acceptance remains separate; test passes cannot close it.

G closure at 02:11 UTC: first coherent Engine/tools/Router/runtime/encoding
boundary: 324 passed. Final bound Router, continuation/prepared and receipt-only
boundary: 154 passed after correcting the negative oracle to inspect the actual
canonical rejected business receipt (the transport correctly returned ok).
The real SQLite Task carries the single complete instruction unchanged; exact
replay adds no Task/outbox effects and stale context rejects without another Task.
Independent review closed one P2: a new input could retire a response while it
waited for the new send lock. The implementation now rechecks ownership inside
the lock and retires unsent requests without fabricating a send receipt.
Reviewed before-await response.created, failed facts send, context-bearing output,
prepared promotion, STOP and bound receipt-only mutation rejection. Prepared
context remains frozen even after another context is actually published.

The one text is the complete self-contained specification of this operation,
resolved by Provider from confirmed facts; it is not an unexpanded pronoun or a
copy of unrelated operations from the same turn. No ASR wait was introduced.
Real model requirement preservation and latency gains remain pending deployment.

## H prompt boundary from the real weather journey

Tier 1, Native session/successor instructions and the work.get schema description.
`low-weather-01-1a05e72ce2a6` used the real Agent; its running receipt returned at
01:57:54.828 UTC, followed by repeated work.get calls before first received audio
at 11.678 seconds after acoustic end. The Agent completed at 01:57:59.924 UTC.
The intended change is one concise, operation-specific nonterminal feedback only
when an actual work receipt says accepted/running and no result is available.
Model should then finish its response and let existing exact work-result events
deliver completion. It should not poll work.get repeatedly without a user request.
If an actual complete result is already present, answer it directly. No fixed
filler, additional feedback response owner, audio identity, Task state, queue,
ACK, history or cancellation protocol is added. Running analysis is not durable
background Task acceptance. Validate actual Provider behavior after deployment;
physical completion notifications require actual playout and remain unverified.

H scoped self-review found no changed authority/state path. The affected Native
Engine/bound tools/receipt-only boundary passed 227 tests. This proves preserved
mapping and fences, not that the model obeys the feedback instruction; the next
real trial will measure that separately.
# Foreground speaker preservation and unplayed retirement (Tier 2)

Current-policy regression migration additionally exposed a retained clarification
after exact local cancellation had already dispatched. Tier 2 ownership is the
Registry's direct local-consent continuation replacement: retire the exact prior
clarification before replacing the local variable with the issued confirmation,
using the existing retirement helper, without changing D-116 consent or durable
confirmation semantics. Verify before/after durable-issue failures, exact target
and binding, immutable other Task, single-use continuation and zero duplicate
commands on replay. P3 running-notification oracles follow the already accepted
silent-running policy while retaining authoritative Store events.

The current recovery batch also owns the mounted Cascade foreground presentation
catch/cleanup seam. When an already-settled answer arrives during a new utterance,
retain its visible text, retire only its unplayed presentation, and preserve the
current capture and exact next committed input. Locally retired unplayed audio
must never acquire an ACK during delayed callbacks, notification replay or Exit.
Keep Task deferred-announcement replay, server interruption semantics, protocols,
Task state and Native admission unchanged. Acceptance covers positive next speech,
same-owner capture, bounded exact activation/response identity, late duplicates,
TTS failure/Exit zero ACK, and existing Task fallback. Independent read-only review
identified the capture-close and cleanup-ACK defects; mounted evidence is not
physical microphone/speaker acceptance.

## Recovery closure checkpoint — 2026-09-08 02:46 UTC

- Fixed the lost new utterance on already-settled foreground speaker deferral,
  false cleanup ACK after unplayed TTS, P1/P2 close ordering, exact remote-close
  retry barrier, and obsolete-effect Task notification loss. An exact predecessor
  activation diagnostic is cleared only after its successor actually activates.
- Current mounted focus: 14/14 before the final retry addition; the final four
  extended journeys pass, including failed media revocation followed by Exit
  retry. Broader affected pattern: 23 passed plus one retained obsolete Task-intent
  control fixture failure. TypeScript check passes. Full mounted discovery before
  the final fixture completion: 140 passed, 11 failed, 1 skipped; ten failures
  require the removed Task-intent UI, and the Exit failure is now repaired.
  These overlapping runs are not added into a synthetic total.
- P3's four previously failing current-policy scenarios now pass. Migrated exact
  local-cancel consent and silent-running oracles exposed and repaired a real
  orphaned prior clarification. Replay compares the complete result and verifies
  Store counts and Executor dispatch/cancel lists are unchanged. Broader P3,
  semantic Registry and bound-tool run: 286 passed, seven failed, all seven in
  the historical Native pre-business-capability path (six explicit unsupported
  capability rejections and one wait for that retired path). Failures remain
  recorded rather than relabeled as passes.
- Independent read-only complete scoped review approved the frontend retirement,
  retry and notification seams and the Registry continuation repair. Main cold
  diff review and diff whitespace check completed. Browser AudioContext/source
  cleanup whose outcome is unknown retains its existing fail-closed policy;
  the retry test injects recoverable exact remote-media transport failure.

## Real G/H checkpoint on deployed 5b0f816d, minimal/auto

- Actual Agent Task `task-8f3c3ebd6c954c75aea00e39abd549ef` completed
  `深圳出差行程.md`; its Task instruction and file preserve dates September 12/13,
  Guangzhou South departure, day-one 10:00 Shenzhen North meeting, two people,
  and 1500 yuan budget, with transport/lodging/food sections.
- Actual successor `task-6ba16c599da341d795ef5d223aeef0f0` completed a beach
  variant with day-two Dameisha and preserved the source SHA-256
  `dec773102201c15cbbce1dbd1f77f1d36d0a5dd9c3415e932999e3ce6821a875`.
  Destination was `深圳出差行程-海边版.md`, not requested
  `深圳出差行程_海边版.md`: exact filename acceptance FAILED. Do not repair the
  artifact manually and claim a successful speech journey. Further spoken
  punctuation verification is required.
- From actual acoustic end to received PCM: creation 7611.576 ms; successor
  4478.574 ms. The earlier absolute 31-second derivative receive timestamp is
  not a 31-second post-utterance latency. Both Task confirmations miss 3 seconds.
- Six ordinary minimal/auto samples: 1537.625–1994.313 ms, median 1868.563 ms;
  six low/auto samples median 1809.312 ms. Small n does not establish minimal
  as faster. No measured physical first-audible result is available.
- The repeated Shenzhen weather query reused a completed work via work.get;
  its 4093.944 ms output is not evidence of a new running-work improvement.
  Four subsequent fresh weather lookups really used work.start and spoke a
  factual underway response without work.get loops. First received PCM:
  3811.511, 3280.662, 3392.102, 3677.203 ms. All remain above the early-feedback
  target. Separate real task.result file query returned the correct 300 yuan
  high-speed rail budget at 4841.630 ms.
- These are authenticated RPC/dedicated PCM/actual Provider + Agent measurements.
  Output transcripts are ASR of recorded received audio, not human listening.
  Record-only enqueue ACKs never create playout receipts or heard-history ACKs.
  A 1959 ms received-frame interval in one ordinary stream was also present at
  Provider ingress; with a simulated 250 ms reserve its previously delivered
  audio covered that interval. It is not evidence of an audible gap or proof
  of audible continuity. Physical browser/device acceptance remains missing.

## E endpoint experiment extension — Tier 2

Controlled high/auto samples still leave endpoint and Provider latency material.
The input packet explicitly permits server VAD at 300/450/600 ms. Add a closed
Native-only endpoint preset selection, defaulting to unchanged semantic VAD;
retain create_response=false, interrupt_response=false, the committed-turn owner,
manual cancellation and all business admission. Own config, Engine/session
configuration observation, Gateway constructor wiring, launcher persistence and
focused configuration/negotiation tests. No browser reserve or DSP changes.
Reject malformed presets before connection. Confirm actual Provider returned
VAD type/silence separately from requested values. Actual fixed-input long
conditions, dates/numbers and pauses must be checked before selecting a default;
a faster first frame alone cannot justify early business mutation or lost words.
Official reference: https://developers.openai.com/api/docs/guides/realtime-vad

Endpoint extension verification: 323 focused tests passed; PowerShell parser
reports zero errors. Independent complete-diff review passed, including exact
unchanged default dictionaries and returned-600/requested-300 diagnostics.
Actual Provider session.updated accepted all three presets on gpt-realtime-2.1,
minimal, speed 1.25, unlimited output, with both automatic response and automatic
interruption disabled. This establishes configuration support only.

High/semantic six ordinary samples were 1520.477–1772.316 ms received first PCM
(median 1611.144 ms). The long dictated filename trial still submitted parentheses
instead of the explicitly spoken underscore and identified its source only by an
opaque Task ID. Task task-591ba4a1710644dcb4eec692ed7f3a51 ended failed with
NO_EFFECTIVE_TARGET_CHANGE; the isolated Agent could not resolve that Task ID to
the source filename and attempted an unavailable bash tool. Original and prior
variant hashes stayed unchanged. Neither acceptance nor audible completion passes.
