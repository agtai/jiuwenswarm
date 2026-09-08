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

## G literal artifact instruction repair — Tier 1 prompt boundary

The real failed successor exposed lossy model-generated arguments, not parser
rewriting: own only Native business instructions. Require exact source filenames
in executable request_text rather than an opaque Task ID; distinguish Task display
names from paths; preserve latest explicit filename and dictated punctuation.
No new classifier, text rewrite, capability, schema, executor access or mutation
policy. Reuse bound-call contract tests for byte-preserving executable arguments;
only a real spoken create/derive with correct files can close semantic fidelity.
Bound tool and Native engine regression: 223 passed. Main reviewed the complete
prompt diff; it adds no server-side text transformation or expanded authority.

Real 5cf391d6/450-ms rerun: task-e18d9b72f0a54e5caf7dd903e385b8dd completed
the exact requested 深圳出差行程_海边版.md (SHA-256
3a6203d43d107082e1fce2dc0e7b1765a7366857998fd38e8653d92ed6bb62a0),
with dates, meeting, two-person budget, unchanged source and prior variant.
Its 9560.550 ms first received PCM still fails confirmation latency. Real trace
shows context.get then task.result before task.create, about 5.49 seconds of
query loops even though the user named the source file. After the actual Task
receipt, response.create took about 1 ms; optional refresh is no longer that wait.

Extend this Tier 1 prompt boundary to distinguish a completely specified project
file transformation from an explicit Task result/adjustment request. Submit the
file instruction directly; the artifact executor performs source reading. Retain
context/result lookup when the required source, target ID or revision is actually
missing, all server admission, and the existing Task-vs-file routing policy.
This removes redundant model-led reconnaissance, not authority checks.
The affected Engine/bound-tool suite passes 223 tests; independent read-only
trace review confirmed the query cycle and the existing schema's direct file
operation. Actual rerun remains required before claiming the latency gain.

## H nonterminal Work receipt continuation — Tier 2

Four real fresh work.start traces show 175–204 ms of Engine context refresh
after a true work receipt. Reuse the existing restricted receipt continuation only for an
exact work.start accepted/running snapshot with unsettled execution and no result
or rejection. This is factual analysis-start feedback, never durable Task
acceptance or completion. Own receipt recognition, Engine restricted successor
selection and focused integration tests. Preserve Router full-context receipts,
including feature-off callers. Keep all
admission, work persistence, unified journal completion, final authority checks,
work state/notification owners, ACK and STOP semantics. No concurrent second
voice response or pre-admission placeholder is introduced. Mixed operation groups,
terminal/rejected/unknown Work receipts and feature-off use the existing full
context route. Restricted successors allow only context.get before further
business calls; verify duplicate/reordered receipts, stale/malformed states,
zero forbidden Task/Tool/history effects, exact STOP and restored fresh context.
Require independent review and real new work.start reruns; savings are measured
separately and cannot alone establish the 1–1.5-second early-feedback target.

Independent review found two P2 issues before deployment: an optimization of the
Router receipt would break the feature-off contract; a terminal event arriving
while the response waited for the send lock could make pending feedback stale.
The Router optimization was removed. Receipt intake, queue selection and actual
locked send now recheck exact work identity/revision against observed facts;
terminal or newer work restores fresh full context outside the send lock and
rechecks response ownership before publication. The 43 focused checks pass,
including both arrival orderings, feature-off context, STOP late audio, durable
work receipt replay and zero Task mutations. Seven affected Engine/business/work
test files pass 316 tests. Independent re-review closed both P2 findings and ran
eight race/fallback probes, including actual speech-start STOP while a downgraded
request waits for refresh: no successor, extra facts, PCM or ACK survived.
Router logic is unchanged; only the Engine refresh portion is optimized.

## Background read convergence extension — Tier 2 scope checkpoint

The real server300 Shenzhen-bay attempt made 198 successful read/list requests
over 100 model rounds (332 seconds), without a write. The requested evening
section is absent and the protected source already ends in Guangzhou at 15:30.
Tool results were delivered; no evidence establishes why the model continued
reading. This execution convergence gap is included explicitly in the repair.

Own the process-local background Task model checkpoint, its dedicated adapter
binding, a stable Executor failure reason, and focused SDK/Executor tests. Before
the next model call, six consecutive completed rounds with the identical bounded
plain-text read_file batch (tool names, effective arguments and hashes of each
complete returned window) fail as
BACKGROUND_TASK_READ_NO_PROGRESS. Writes, changed results/arguments, new accepted
user requirements, missing/incomplete tool batches and non-file tools reset this
narrow detector. Only original SDK message types with the context identity
metadata and exact consecutive cat_n line prefixes qualify. list_files, PDF,
Notebook, empty, error/interruption, offloaded/compressed and unknown results
are excluded and reset it. It is active only in the exact isolated background Task session;
ordinary chat, Native dialogue and general Code sessions are unchanged. Retain
existing Task identity, admission, cancellation, adjustment, durability and cleanup
owners. A guard stop must use the existing failure path and never apply even a
partial checkout patch or report a successful forced answer. No tool permission,
model/provider, global runtime configuration or durable schema changes are owned.

Acceptance includes real SDK callback rejection before another model call;
duplicate callbacks, reordered tool completions, changed output, normal read/write/
verify and adjustment/cancel isolation; actual Executor failed outcome with zero
target/artifact application; and a real conflicting request plus a satisfiable
file transformation. The detector only covers the repeated batch observed here,
not every possible non-progressing model trajectory. Independent review required.

The real SDK/context callback suite passes 16 checks; the real production
Resolver/Manager/Facade/Executor seam passes all five outcomes (normal completion,
wrapped exception, chat.error, swallowed successful answer, cancellation). All
guard cases trigger through six complete controlled read batches in real SDK
context (the tests do not invoke a physical file tool). Failed attempts
retain BACKGROUND_TASK_READ_NO_PROGRESS and do not apply an isolated partial.txt;
cancellation retains its original outcome. Normal completion still writes and
seals the expected target file. Full Executor/checkpoint regression: 161 passed,
2 host-dependent skips in 217.20 seconds. The background Code-mode boundary passes
14 tests. Independent complete-diff review closed the placeholder/context identity/
exception-mapping findings and approved the bounded implementation. Real Provider
conflict/control runs remain required.

## Requested restatement and grounded result answers — Tier 1

The 1f499b8f 30-round batch had a content failure despite complete incoming
transcription: case 15 returned only `负一` for a request to repeat dates, people,
budget, meeting time and the final evening condition. Three identical-audio
repeats on the unchanged runtime returned `4`, then two complete restatements.
This is reproducible incorrect model output, not evidence of transport clipping.
The broad default instruction to omit restatements conflicts with this explicit
user request; that conflict is repaired without claiming it proves the cause of
the numeric answers. Own only Native spoken-response instructions and affected
Engine/closed-tool regression, retaining tool-only call frames and full answers.

A result query also denied an available total even though its exact authoritative
Task receipt contained 620+60+90+80=850 and the other option's 1260. Clarify that
the requested facts in actual result_text must be used, with option labels when
needed; absence of an identically named heading is not absence of the data.
Ask for clarification using observed human task names when needed, without
asking the user to supply internal IDs. No new matching classifier, fact filter,
tool authority or pre-playback ASR/validation gate is introduced. Re-run identical
speech, real result queries and the final ordinary sample batch on the change.

Main reviewed the complete Tier 1 prompt diff. All 266 affected Engine, bound
tool and receipt successor checks pass; whitespace check passes. This is prompt
scope and regression evidence, not proof that the observed incorrect answers
have been eliminated. New-runtime repetitions and content audit remain required.

Independent cumulative review found one remaining Tier 1 prompt seam: Task
acceptance, Work underway and Work completion use their own response instructions,
which override session instructions. Extend the same explicit-content exception
to these three entry points. Default short factual receipts remain; requested
restatements may use only known requirements, and requested result detail only
the actual completed result. Retain all receipt, freshness, tool and cancellation
guards. Re-run affected Engine/receipt checks and actual composite requests.
The same override also exists in retained legacy jiuwen_delegate continuation;
include it in this instruction-only boundary, preserving its no-tool successor
and exact-result grounding. Explicitly repeated requirements are not execution
facts unless the real delegate result confirms them.
All 223 affected Engine and bound-tool checks pass. Independent complete-diff
review closed all four override conflicts and found no other unconditional
content-compression override. The three identical cached-audio restatements on
082b64a2 each retained every requested condition; this small generated-text and
received-audio sample does not establish general correctness or physical delivery.

## Native adjustment observation seam — Tier 3 scope checkpoint

The real final customer-draft adjustment was accepted while TaskCore still saw
running, then rejected when the earlier Executor completion arrived. Its outbox
was suppressed with zero deliveries, but Native sealed the original pending
receipt alongside completed Task context. Own only the first Native task.adjust
receipt presentation: after context refresh and before initial journal completion,
read the existing authenticated exact Task/Attempt/adjustment control snapshot.
Append a bounded as-of observation; preserve the actual original receipt and
dispatched status. Do not infer application from Task completion, introduce a
second mutation, refresh a sealed replay, or change canonical replay bytes.

Unknown, expired-window, failed or mismatched reads remain unconfirmed; they do
not erase a prior confirmed applied/rejected receipt. Keep cancellation and
current-route final checks. No TaskCore, outbox, Executor, durable schema or
permissions change. Own Router projection, spoken-grounding instructions and
real Registry/SQLite seam tests. Required cases: terminal wins, applied wins,
pending/unknown, failure/wrong scope/attempt, single-flight/replay and zero other
Task/Agent/audio/history effects. Independent review and actual local rerun are
required; this does not retroactively rewrite the earlier failed adjustment.
The new 14 cases exercise real Registry/SQLite terminal-vs-application outcomes,
exact identity, unavailable/unknown observations, concurrent duplicate requests,
byte-identical replay, cancellation, and close/project-rebind at the new await.
The terminal fixture initially violated paired result/artifact validation; the
corrected legal no-result completion produces the actual TaskCore rejection.
Affected Registry/authority/encoding/Engine regression: 251 passed. Independent
complete-diff review approved; original durable commands, unrelated Task, Agent,
audio/history and replay bytes retain their respective checked boundaries.

The actual 800235d9 multi-file handoff Task also reached the six-round identical
read guard and failed, after its adjustment was genuinely adopted. This validates
the bounded failure/zero-partial-application path but leaves positive convergence
open. It did write the requested header in the isolated checkout, then repeated
the same output-verification window six times; this was not zero lifetime progress.
Tier 1 extension owns only the dedicated background Code prompt: reuse
source windows already available, move from sufficient facts to writing, and
verify requested output without repeatedly reading the same source for length,
finish after a successful check, or fix a concrete discrepancy before rechecking.
Changed files, missing windows and output verification still permit reads. No
guard relaxation or forced successful result is introduced. Check background
mode/checkpoint boundaries and rerun the same substantive handoff under a new
output path, retaining the failed original Task and artifact absence.

Exact final prompt: 14 background-mode checks passed (66 deselected); independent
read-only review found no blocking issue. Real positive convergence is still
pending and is not credited from these checks.

The final 300 ms trial exposed a separate preservation failure: the user spoke
output vad300_d.md, but Native delegated vad300_c.md while still requiring all
existing files be preserved. The Executor overwrote the existing C artifact.
Tier 1 extension owns only the dedicated background prompt's handling of this
existing preservation constraint: an existing exact output plus a preserve-files
requirement is a conflict, not permission to replace or invent another path.
No classifier, new authority or forced-success projection is added. Validate
background mode composition, review, and a real conflict Task. Preserve the
incorrect D version and restore C only from its sealed original bytes, recording
that as corrective maintenance rather than Task or product acceptance.

Final eight-line prompt passed 14 background-mode checks and independent review.
It is a model instruction, not an atomic no-overwrite guarantee. Original C was
restored from project Git blob 50d736d3d7a48ef69b8b1324f8e577e25b862611 with exact
sealed SHA256 16ba045fd856abec5e759c1e416582d482d483b24ecbd6d2227c09937bbb1f1c.
The incorrect D bytes were preserved in ignored evidence and the originally
requested, previously absent vad300_d.md. This maintenance does not rewrite Task
history or grant the incorrect D Task successful product acceptance.

## Post-window source and file-effect repair — Tier 3 checkpoint

The six-hour checkpoint is PARTIAL; execution continues under the same user
request. The D-to-C overwrite demonstrates two separate defects: Native's
rewritten proposal replaces the user's source at Task dispatch, and the Executor
has no executable preservation policy. Main owns both seams. Required independent
design review confirmed there is no existing file-effect contract to reuse.

First implement original-input provenance through Runtime, production origin
binding, P3, durable Task specification/adjustment and the actual Code Agent
request. Freeze the exact admitted anchor commit and a bounded ordered window
of preceding same-activation items as separately identified context. Do not
invent a multi-item command span, concatenate history into authoritative speech,
or infer reference ownership from recency. Retain canonical Provider transcript
text and identities, including absent historical transcripts, separately from
the model's executable proposal. Wait asynchronously and finitely for the
anchor's final transcription at Task dispatch; no Provider-reader or ordinary
first-audio wait. Missing/failed/closed source fails before Task mutation rather
than falling back to rewritten text. Source bytes bind origin, command, immutable
Task fingerprint and exact adjustment. Old persisted records remain explicitly
source-absent with their existing canonical bytes; no retroactive source repair.

Then implement a separately versioned FileEffectPlan proposed by the existing
Code Agent and frozen by the server. Exact create/replace/delete paths, original
existence/hash, required outputs and plan revision must be checked before durable
effect preparation and every normal/recovery apply. Unlisted existing files stay
unchanged. An actually adopted adjustment must bind the corresponding plan
revision; successor Tasks receive their own plan. This is a scope expansion of
the repair, recorded before code, not permission for a new keyword classifier,
provider change, default create-only policy, or model self-issued overwrite grant.

Source and effect enforcement have distinct acceptance. ASR and Agent semantic
interpretation can still be wrong; typed plans do not prove natural-language
correctness. The complete boundary requires the original D replay producing D
while C is unchanged, explicit existing-file editing, preserved derivation,
same-Task adjustment races, changed/appearing targets, retry/restart/D2 recovery,
cancel/close/reconnect and forged/cross-scope source or plan with zero forbidden
formal-file effects. Source-only tests cannot close preservation or physical
acceptance. Applicable regressions and independent complete-diff review precede
each coherent local commit; no deployment of an unfinished boundary.

Source review also identified query amplification: full source evidence must not
be copied into every Task list/status receipt. The read projection retains a
bounded source digest; Store specs, commands, retry lineage and Executor requests
retain the complete evidence. Verify legal large transcripts through actual
serialized Native queries and replay, including UTF-8 and Provider JSON limits.

### Source module implementation and checks after the requested pause

The user resumed explicitly after changing Codex speed. Original transcription
now reaches the existing Direct worker AgentRequest and adopted adjustment
checkpoint. Runtime admission and bounded late-ASR waiting, immutable source
binding, SQLite restart/retry/successor, verified Task.update and source-absent
compatibility are implemented. The independent review found and closed receipt
amplification; actual worker testing found and fixed an old adjustment outbox
payload comparison that otherwise rejected the new source-bearing adjustment.

On the source commit containing this record, commands use
`.venv/Scripts/python.exe -m pytest ... -o addopts= -o log_cli=false -q -s --tb=short`:

- Source scenarios: 24 passed, then 2 additional public-source/confirmation and
  command-replay forgery cases passed, then 1 total-source-byte-bound case passed.
  The Direct worker test captures the real dispatch and model-checkpoint request
  carriers using a deterministic test Agent, produces a formal file and verifies
  exact once-only adjustment application/replay. It is not real-model evidence.
- Five legal 60 KB Chinese source records survive SQLite reopen while actual
  serialized Native list/status and replay stay below both Unified 262,144-byte
  and Native 524,288-byte receipt limits. Queries expose only source digests.
- `test_persistent_task_core.py test_project_code_executor.py -k 'adjust or retry
  or query or list or status or successor'`: 150 passed, 359 deselected.
- Shared v2 contract, Native Runtime, Gateway Native client and Realtime Engine:
  331 passed. The earlier affected-module run remains 535 passed, 2 Windows
  symlink skips; only the subsequently affected Store/Executor checks were rerun.
- Complete cold diff and independent source-module review passed. The two
  discovery failures above and corrected test error-code assertions remain in
  ignored logs; they were not converted to pass without affected reruns.

Raw commands/results are retained under ignored `logs/repair-20260908/source-*`.
No remote update occurred. Real Provider/selected Code Agent verification follows
the clean controlled deployment. FileEffectPlan, natural-language fidelity,
latency and physical A–F acceptance remain open; this closes neither the original
overwrite failure nor the six-hour product acceptance.

Source commit `9dc31e63fcf637b1489dbb94b6587bbe9df3941b` was cleanly deployed at
07:12 UTC through the authorized launcher with a fresh tsc/Vite build. Runtime
contract retains gpt-realtime-2.1, speed 1.25, minimal and server-vad-450; actual
TTS→STT and identity/forged-claim negatives passed. Log: swarm-20260908-091151.log.
The real Provider → Native Task → selected deepseek-v4-flash#0 journey created
`task-2f2b686b62944ae8ae855557239ad518` at 07:13:24.336678Z and completed it at
07:13:51.993945Z. Its persisted source contains the exact final D-not-C/preserve
utterance and three preceding source items. It wrote `验收输出/source_d.md`, SHA256
`bf3123cdbc4131ea1cc8c030df35e884ea3386ea8a54b673a2fe84067b94f83f`, with 850 yuan
new transport and 650 yuan remaining; all 25 pre-existing Markdown hashes stayed
unchanged. This is one positive actual-model/source/file sample, not executable
preservation enforcement or a forced model-C/original-D replay.

The paired ordinary reply retained all requested people/date/1500/10:00/second-
night-walk conditions. Received first PCM after measured acoustic end was
1751.552 ms; Task acceptance PCM was 8391.832 ms and still fails 3 seconds. The
Task path made an additional context.get call. Exact same-Gateway-clock raw
Provider PCM→sent joins were 23.964 and 24.150 ms. N=2 is not a new percentile
acceptance sample. No physical speaker, microphone or browser acceptance is
claimed. Ignored source-real-* and native-source-real-* preserve raw evidence.

### Receipt follow-up clarification — Tier 1 checkpoint

The real source-validation Task returned durable acceptance, then the Native
model requested context.get before acknowledging it. Own only the existing
receipt-only response instructions: accepted background work, future result
contents and confirmation of acceptance do not themselves require a fresh query.
An additional operation outside that accepted work still requires fresh context.
No tool is removed, no acceptance is fabricated and no multi-Task dependency is
silently dropped. Keep current receipt/ack/cancel/dependent-call checks; compare
actual Provider receipt turns and latency after the clean local deployment.

Seven affected Engine receipt/feedback/acceptance checks passed (190 deselected).
Independent complete-diff review found no blocking issue: context.get, fresh
context, extra Task operations, and no-audio-with-tool-call rules are retained.
Any measured improvement still requires the real Provider trial.
