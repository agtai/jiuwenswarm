# Realtime optimization: full implementation and unified acceptance

The user's 2026-09-07 continuation authorizes all handoff optimization points,
one reviewable local commit per point, parallel implementation and Main-owned
integration. The already integrated first bounded batch `ebeb5aa4` remains
unchanged historical evidence in the [first packet](REALTIME_OPTIMIZATION_20260907.md).
This packet replaces its next-work trigger; evidence synchronization does not
block independent implementation. [STATUS](../STATUS.md) owns current credit.
[Root guidance](../../AGENTS.md) and [TESTING](../../TESTING.md) own Git authority,
writer leases, scenario dimensions and review. No remote update is authorized.

## Scope checkpoint

Main owns shared semantics and integration. Workers receive separate worktrees
and exact file assignments; they do not perform Git operations. The integration
baseline is `ebeb5aa4db828b69489ce205de85ebd1d3a1c5a5`. Each point's code, tests,
review evidence and corresponding document update form its own commit. Record
discovered shared-contract extensions before implementing them. Use Astra max
or ultra for the difficult lifecycle/design reviews already authorized by the
user. Final user acceptance considers the cumulative candidate.

| Point | Intended behavior and owned boundary | Risk, dependencies and acceptance |
|---|---|---|
| P0 | Complete content-free Native timing: transport lock/encode/send/receive, first arguments, endpoint and existing Runtime/media/browser milestones. Preserve source-qualified fact acquisition. | Tier 2 passive observations. Explicit origin identity, bounded records, failed sinks cannot alter outcomes; no payloads. Source-time audio offsets are not wall-clock latency. |
| P1 | Advertise simple operation-specific Provider tools; deterministically decode into the unchanged internal proposal/action and replay contract. Keep correction bounds, clarification and exact IDs/revisions. | Tier 3 Provider schema adapter. All 13 positive operations, closed malformed/duplicate inputs, legacy compatibility, same-call conflicts, real selected-Provider negotiation and emitted-argument validation. No inferred arguments or new classifier. |
| P2 | Reduce repeated context while preserving exact full query/recovery truth; wake on terminal Work events; prepare continuation safely before prior actual playback ends. | Tier 3 scheduler/context/durable seams. Main owns overlap design, bounded prepared audio, exact old/new identities and cancellation/recovery. No removing ACK fences without replacement. Full canonical receipts stay authoritative. |
| P3 | Make semantic endpoint eagerness a controlled Native setting; compare auto/high under the same pauses and late supplements. | Tier 2 configuration/timing. Default auto until evidence supports promotion; auto-response and auto-interruption remain false. Exact selected model and Cascade unchanged. |
| P4 | Deliver a short, sourced conclusion as early as the authoritative Agent result permits; preserve complete results and requested detail. | Tier 3 if a separate early stage is introduced: immutable work/revision/context/source provenance, durable publication and distinct nonterminal presentation. Raw tokens/reasoning/tool output never become conclusions. Prompt-only changes cannot claim precompletion delivery. |
| P5 | Use the existing async downlink frame/byte window instead of one frame per ACK; first frame immediate and controls responsive while source stalls. | Tier 2 transport lifecycle. At most one source pull and one control receive, exact credit, source EOF plus final ACK, cancellation/fault cleanup; synchronous Cascade regression. Startup reserve stays unchanged here. |
| P6 | Recover from supply gaps using real queued PCM reserve with bounded deadlines. | Tier 2 browser audio state, depends on P5 supply diagnosis. Deterministic baseline/candidate arrival traces must reduce reserve delay without adding glitches; stop/tail/pause/stale response isolation. Physical continuity remains separately measured. |
| P7 | Prepare true terminal notifications earlier and reconcile reactivation while user speech retains playback priority. | Tier 3 if TTS preparation precedes playback arbitration: bounded exact event/activation/response/text owner, no early playback/history/ACK, ticket expiry and invalidation. Existing synthesis cannot be naively prefetched because it cancels its prior owner. |
| P8 | Remove source-proven execution setup redundancy and evaluate actual Agent rounds/tool work from evidence. | Tier 2 model lifetime. A fresh selected Native model can avoid a second identical client construction; cached models remain isolated. No model/provider change, skipped reads, pooling or invented eliminated model calls. |
| P9 | Evaluate service/ACK/transcription overhead against the measured boundary and preserve authority. | Tier 0 decision if no justified bottleneck exists; code only for a demonstrated safe improvement. Never trade admission/identity/ACK correctness for small unproven savings. |

## Evidence rules

The original other-server rehearsal logs are absent locally. Its 49.783 seconds,
category allocations and 35–40 second target remain an imported budget, not this
candidate's measurements. Fresh controlled evidence must preserve the selected
model/provider, project and source; retain failed samples. Mocks and timing
traces prove their owned boundaries, not microphone/speaker quality or a speedup.
The real Demo must execute committed final speech through JiuwenSwarm Agent and
tools. Full Work/Task creation, adjustment/cancellation, status/results, unrelated
questions, wrong-scope/stale calls, interruption, reconnect, notifications, heard
history and Cascade compatibility remain required at unified candidate acceptance.

## Per-point implementation evidence

### P0 — Native transport and argument timing

Added optional activation-scoped Session observations for selected control events:
send-lock wait, JSON encoding, actual socket-send duration and receive/decode time.
Audio frames and argument deltas are not logged by the transport. Engine records
at most eight first argument items per response, completed arguments, endpoint
offset and item-to-committed-turn linkage. Existing first audio, receipt, wait,
Runtime and browser observations remain distinct. The offline profile exporter
pairs Native send/argument spans only within exact clock and activation identities;
missing starts and unfinished spans remain explicit.

Commands use the root `.venv/Scripts/python.exe`, isolated `logs/p0-data` and
`-q -o addopts='' --no-cov -o log_cli=false`:

- `pytest tests/unit_tests/live_voice/test_native_transport_diagnostics.py tests/unit_tests/live_voice/test_native_business_diagnostics.py tests/unit_tests/live_voice/test_openai_realtime_session.py tests/unit_tests/live_voice/test_openai_realtime_native_engine.py tests/unit_tests/live_voice/test_demo_profiling.py`: 231 passed before final review corrections.
- The same affected set excluding the unchanged Engine regression file, after
  review corrections and report additions: 71 passed. New coverage includes two
  utterances, injected observer delay, failed sinks, bounded deltas, unknown input,
  source isolation and incomplete/cross-clock report records.
- Independent reviewer found endpoint attribution to the previous committed turn
  and diagnostic work included in socket duration. Both were corrected with
  regression oracles. The reviewer independently ran 24 Session/diagnostic checks
  before those corrections. Scoped static/diff checks accompany the commit.
  Follow-up independent review ran 37 diagnostic/report checks, confirmed both
  corrections and the exact report joins, and found no remaining actionable issue.

These observations enable a new comparison; they do not restore the missing
rehearsal, determine actual speech end from a Provider offset, establish factual
answer quality or prove any latency reduction. Source-qualified fact policy is
also part of P4's formal answer boundary.

### P1 — Operation-specific Provider tools

The Provider receives 13 simple flat tools. Their names select existing operations;
the adapter fills only internal unused null fields and invokes unchanged action,
proposal and carrier validation. Legacy `jiuwen_business` input remains readable
but is not advertised alongside the new tools. Unsupported names, unknown fields,
duplicate JSON keys, malformed/oversized/deep input and invalid required text
reject without inferred values. Flat rejection metadata survives the real sink.
The Engine keeps its original call fingerprint, sibling settlement, two-round
correction limit, target/context authority and cancellation behavior.

The complete schema grows from 3,386 to 13,123 UTF-8 bytes; representative generated
arguments shrink (`work.start` 345→237, `task.adjust` 316→248, `task.status` 279→168).
These are synthetic serialization sizes. The change removes irrelevant generated
fields; it does not claim lower total input cost or improved first-call accuracy.

Checks use root Python, isolated `logs/p1-data`, and the P0 pytest options:

- New tools + existing contract/carrier in the worker: 104 passed.
- Integrated tools, contract, Engine and business diagnostics: 273 passed.
- New `test_native_named_tools_engine.py`: 16 passed, including all 13 operations,
  same-turn invalid adjustment correction alongside accepted work, original call-ID
  conflict and cancelled-response zero business/audio effects.
- Independent review: 113 tools/Engine/diagnostic checks and 24 existing correction,
  conflict/recovery/compatibility checks passed. An additional in-memory probe
  rejected all 13 tools with business disabled and zero delegate/audio/receipt/ACK
  or new Provider-send effects. No actionable findings. Scoped Ruff `F,E9` and
  `git diff --check` passed.

Real selected-Provider conformance used the existing private Speech configuration
and `gpt-realtime-2`, with synthetic server facts and user requests. No Registry,
Agent, Tool or Task was executed. Both named and legacy schemas negotiated, and
both `work.start` and `task.adjust` produced valid first calls with the expected
operation/context/target/revision in two runs. This is Provider→production-decoder
evidence, not the full business or physical journey. First-call times vary between
samples; four cases per run are insufficient for a latency/success-rate claim.

The local probe is retained at `logs/p1_provider_probe.py`, with content-free
`logs/p1-provider-evidence-initial.json` and `logs/p1-provider-evidence.json`.
The first run sampled the normal 25ms cleanup budget and reported `closed=false`;
that missing cleanup evidence was retained. The second run gave the probe a
bounded two-second close wait and verified all four sessions closed. Production
cleanup settings and model/provider configuration were not changed.

### P5 — Async downlink supply within the existing window

The async leaf now sends ready frames within the negotiated frame/byte window
instead of waiting one network round trip per frame. It retains at most one
source read and one control receive; ready controls precede further sends, the
first ready frame is immediate, and a single byte-fit pending frame is bounded.
Completion still requires source EOF and the final exact ACK. The Registry
supplies its existing cleanup owner, reserving two slots without increasing
capacity. Cancellation-resistant reads/close operations remain retained; the
socket leaf returns truthful incomplete-cleanup facts after its bounded wait.
Generator close happens once after an active source read actually settles.

The source, focused leaf tests, registration tests' send-triggered ACK helper and
the Registry's cleanup-owner call site are the only P5 product/test changes.
Window sizes, protocol, startup 250ms reserve and actual-playback ACK are unchanged.

- Worker leaf + registration suite: 257 passed; Main's integrated repeat: 257
  passed (`6.81s`), using isolated `logs/p5-data` and P0 pytest options.
- The decisive eight-frames-before-first-ACK oracle fails against `ebeb5aa4`
  loaded only inside a test process: old source sends frame 0 and then times out.
- Initial independent review ran 112 relevant checks and found an unbounded
  cleanup wait on hostile source/receive cancellation. Fixed using the existing
  bounded cleanup owner; added hostile source/recv/close, second cancellation,
  cancellation before first pull and exhausted-owner scenarios.
- Follow-up independent review ran 36 affected leaf and 10 registered Native
  seam checks; all passed with no remaining actionable finding. Complete scoped
  source review, compilation and whitespace checks passed.

The correction proves removal of the source-backed one-frame/ACK bottleneck and
retained cancellation ownership. It does not prove a 0.5–1 second physical gain.

### P3 — Controlled endpoint experiment; auto remains the default

`LIVE_VOICE_NATIVE_VAD_EAGERNESS` accepts exactly `auto` or `high` for Native.
Invalid values reject before Session construction; Cascade never reads the setting.
The Web factory captures validated configuration; subsequent environment changes
cannot replace it. `create_response=false` and `interrupt_response=false` remain
fixed. Diagnostics label the requested strategy without claiming Provider confirmation.
The controlled launcher accepts `-NativeVadEagerness`, records it in the runtime
contract and permits the explicitly selected optimization branch for later clean
candidate startup. No default model change accompanies this setting.

The real comparison used the existing configured TTS voice/model to make four
bounded stimuli, then paced identical PCM bytes into fresh `gpt-realtime-2`
sessions at 24kHz/20ms. Eight sessions negotiated and closed; zero automatic
responses or business effects occurred. Complete content-free observations and
PCM digests are in [the endpoint evidence](../evidence/REALTIME_ENDPOINT_COMPARISON_20260907.json).

| Same-byte stimulus | auto endpoint after PCM end | high endpoint after PCM end | Commit count auto/high |
|---|---:|---:|---:|
| Clear sentence end | 1440ms | 932ms | 1 / 1 |
| 600ms mid-sentence pause | 238ms | 222ms | 1 / 1 |
| 1200ms hesitation pause | 132ms | 123ms | 1 / 1 |
| Complete sentence, 800ms pause, late supplement | 322ms | 396ms | 1 / 2 |

High prematurely ended the first part of the late-supplement stimulus. It fails
the no-extra-split condition, so auto remains the production default. These
single paired samples support that conservative decision, not a general speedup
estimate. PCM end is a known stimulus boundary, not measured human speech end;
the observed interval includes Provider/network behavior. Browser/microphone
acceptance remains open. Local stimulus/probe files remain in `logs/p3-stimuli`
and `logs/p3_endpoint_probe.py`.

Independent review passed 40 configuration/endpoint checks, four Web-factory
checks and an environment-change isolation probe with no findings. Main's initial
broader app run passed 124 and failed one existing GPT-5.6 SDK-version guard.
The required pinned SDK was built and installed only in the optimization
worktree's `.venv`; the original environment remains unchanged. Windows checkout
CRLF initially prevented applying the committed SDK patch; resuming the owned
fresh checkout with the exact LF Git blob built the prescribed wheel without
altering its source delta. Both failed logs are retained. After processing the
base environment's dependency path hooks, config/endpoint/app plus actual SDK
compatibility tests pass 165/165. Final Engine/launcher regressions pass 209 with
five explicitly POSIX-only process-group cases skipped on Windows. Scoped Ruff
`F,E9`, `git diff --check` and the PowerShell parser pass. Independent launcher
review found PowerShell's default case-insensitive ValidateSet could admit `HIGH`
before the backend rejected it; the parameter now rejects case variants before
any launcher effects, matching the backend's exact setting contract.
The reviewer rechecked the actual parameter AST: auto/high accept, HIGH/Auto
reject during binding, and the complete script parses. No findings remain.

### P8 — Reuse the fresh selected model for one Native execution

The catalog resolver constructs a new Model from an independently read configuration
for every exact Native binding. The adapter now observes that same execution-private
instance instead of immediately constructing another identical client. The cached/default
path still clones its configuration and model; no cross-request model pool is introduced.
Model identity, options, provider, read-only tool policy and final output are unchanged.

Main's formal policy/adapter/model-diagnostic suite passes 65 checks, including concurrent
complete/failure/cancellation isolation and restoration after output settlement. Independent
review traced the production catalog and builder, ran the 17 policy checks, and found no
actionable issue. Scoped Ruff `F,E9` and diff checks pass. Local evidence is
`logs/p8-model.txt`; tests use the isolated patched SDK and `logs/p8-data`.

This removes one redundant setup construction per selected Native execution. It does
not eliminate an Agent model round. The imported seven-call background trace is absent
locally and does not prove redundant reasoning or reads; no model switch, read suppression,
or speculative pooling is justified. A new real Agent/file-tool probe accompanies P4
and cumulative acceptance; neither a background-task speedup nor the imported target
is established by this setup change.

### P4 — Scope checkpoint before implementation

Main selects a Tier 2 Native read-only answer policy within the existing final-result
boundary: lead with the shortest complete supported conclusion and essential caveats,
then give the requested detail. Bind facts to their source, subject and effective time;
read necessary project evidence without a narration or planning round. Keep all committed
text, selected context and source refs intact, and retain stronger Task receipt/result
contracts. This owns `formal_live_voice.py`, the trusted formal adapter prompt section
and focused envelope/adapter tests. P8's execution-private model setup is its dependency.
Acceptance requires exact preservation/override tests and a real JiuwenSwarm/file-tool
quality sample with unchanged model settings; prompt instructions alone do not prove
that facts are correct or delivery is faster.

No separate precompletion publication is introduced. The existing Work contract publishes
result text only at terminal; the imported first-output timestamp does not establish a
source-verified intermediate conclusion. Publishing raw deltas, inventing a new partial
truth owner, or adding a model tool round solely to manufacture a stage would not meet
the accepted provenance requirement. This point targets avoidable preambles/answer bulk
and source confusion, with precompletion delivery explicitly remaining unproved.

The implementation applies the source-qualified Native policy through the trusted
formal system section and the current Chinese/English output section. An ordinary
read-only envelope receives the conclusion-first answer contract only when no stronger
Task receipt/result contract exists. Full selected context, exact refs, committed
text, requested detail, final answer and model/tool ownership remain intact.

The initial policy was visible in each real model round but still yielded a long
answer. The final output-section wording produces a conclusion in the first sentence
and removes headings in the recorded sample. The real selected default model remains
`deepseek-v4-flash#0`; both candidate and baseline perform actual `glob` and `read_file`
through AgentManager's formal P2 facade and the patched SDK. They correctly use v2's
35-minute warehouse travel time, reject the superseded 20-minute value and distinguish
the unselected office route. Arrival 09:40 misses the 09:35 check-in cutoff by five
minutes; departure by 09:00 is required. Only the synthetic fixture existed before
and after execution, its bytes and the private configuration remained unchanged,
and Agent cleanup completed.

[Recorded Agent observations](../evidence/REALTIME_AGENT_ANALYSIS_20260907.json)
retain the baseline, initial verbose candidates and final sample. The final sample
contains 349 characters versus the baseline's 605, but takes 12.18 seconds versus
10.06 seconds. Both need three model calls. These cold-session/network-dependent
samples demonstrate source/answer behavior, not overall acceleration or P8 round
reduction. Earlier first-output tokens are not accepted conclusions. The initial
probe mistakenly selected a Code facade and failed before execution; its failure
is retained and the corrected probe uses the same Agent-profile route as production.
Older intermediate samples without exact file hashes are explicitly labelled as
incomplete source bindings. The final sample records both affected source hashes.

Checks: 74 formal policy/adapter/model-diagnostic cases pass, including Chinese and
English execution-only policy restoration, full final-text preservation and three
stronger Task-contract precedence cases. Another 109 ConversationRuntime/speculation
regressions pass. Scoped Ruff `F,E9` and diff checks pass. Local logs are
`logs/p4-final-tests.txt`, `logs/p4-runtime-tests.txt` and `logs/p4-real-*`; the probe is
`logs/p4_real_agent_probe.py`. Independent review ran the nine new policy cases,
verified full input/final-output preservation and Task-contract precedence, and
found no actionable issue.

### P6 — Reject early recovery rescheduling; retain continuity guards

The [P6 decision](REALTIME_P6_RECOVERY_DECISION_20260907.md) retains the original
250–750ms bounded reserve. Independent review found that a filled burst followed
by another delay can gain an extra underrun, and a main-thread stall while stopping
sources can replay PCM already started by the audio clock. Astra max confirmed
both structural counterexamples; the candidate production changes were withdrawn.
No reserve-delay saving is credited and the imported 1–1.5 second target is unmet.

The single P6 commit contains the decision and regression guards. The independent
reviewer reran the exact frozen baseline/candidate comparisons: baseline five cases
pass; the rejected candidate adds a gap and repeats 240 samples (5ms at 48kHz).
Tail and healthy-supply controls pass on both. The reviewer verified both frozen
source hashes and found no remaining production diff or documentation issue.
Main copied only the final tests and decision into the integration worktree;
`npm run test:live-voice-browser-audio-io` passes strict TypeScript, bundling and
all 125 audio/capture cases there (`logs/p6-main-audio-tests.txt`). Main's frontend
dependencies use package junctions with a separate local build cache. No physical
speaker evidence or performance improvement follows from these scheduling tests.

### P9 — Preserve service, ACK and transcript authority

This point closes as the handoff's Tier 0 prioritization decision, with no product
code change and no allocated speedup. The imported trace reports individual service
calls of 0.30–0.75 seconds but only 0.716 seconds exposed as silence; its 1.330 seconds
of ordinary conversation is a different category. Even eliminating the entire
0.716-second service contribution would account for only about 1.44% of the imported
49.783 seconds. Those are source-provided budget figures, not fresh measurements.

The source review confirms that [Native audio ACK](../../jiuwenswarm/server/live_voice/native_interaction_runtime.py)
checks the exact open response and delegates to the presentation ledger before
reconciling heard history. [Business receipt completion](../../jiuwenswarm/server/live_voice/native_business_router.py)
persists the authoritative result before producing its receipt; an optional context
refresh failure cannot rewrite an already committed Task effect. Removing these
steps, deferring persistence past success, conflating network delivery with playback,
or suppressing accurate transcript/history handling would alter authority and recovery.
No current trace establishes a safe duplicated service call worth removing here.

P0 supplies content-free timings for future measurements; P2 owns context/observation
redundancy and P5 owns frame-window supply. Their effects must be attributed to those
boundaries once measured. This decision adds no classifier, shortcut, model change,
new test requirement or release gate. Scoped document links and whitespace are checked;
the affected ACK/replay compatibility tests remain part of P2 and cumulative acceptance.

### P2 review refinement — bounded observation scope retention

Main's cold review reproduced 1,000 retained observation counters from 1,000
unique retired/no-Work scopes, despite the existing 128-record Work bound. Before
repair, Main takes the `native_work_runtime.py` and business-observation test
writer lease; the parallel P2 repair keeps its Engine/helper lease. The intended
Tier-3 behavior bounds counter retention by the existing Work-record capacity.
Overflow rotates the observation epoch, wakes all existing waiters and starts
fresh counters. Existing epoch-mismatch handling requires a complete snapshot;
no observation becomes admission authority and no Work/Task record is removed.
Acceptance includes bounded churn, old/new waiter cleanup, epoch refresh and
unchanged business records. No protocol field, model or product policy is added.

### P7 — Prepare exact terminal notification audio before playback arbitration

The [P7 contract](REALTIME_P7_CONTRACT_20260907.md) records the negotiated local
preparation/claim/cancel family. A true terminal notification may prepare its
existing selected TTS while capture or Native playback retains priority. Exact
activation, Task/attempt/event, response, unit, text digest, locale and rate bind
one bounded slot. Claim alone creates the existing fresh one-use media ticket;
prepared PCM and transport completion never count as heard output.

Independent Astra max review and real media-leaf checks repaired cancellation
after EOF, after transport completion and during ticket attachment, duplicate
claim/play promises, successful leaf-finally cleanup, and exceptional socket
cleanup. The exact child remains revocable until accepted render settlement;
its timeout fences output and never invents playback or revokes the parent mic.
The final independent review has no remaining scoped finding.

Main's combined P2/P5/P7 Gateway passes 331 affected backend cases. Strict Native/P1
and Gateway/privacy checks pass 140 and 35 cases; production frontend build passes.
The independent reviewer additionally ran the two P7 mounted scenarios and the
215-case worker backend boundary. The contract records the identical baseline
mounted/source-pattern failures; broad mounted/product acceptance is not claimed.

[Real selected-TTS observations](../evidence/REALTIME_TASK_TTS_PREPARATION_20260907.json)
retain three source-bound revisions. The final sample uses actual TTS through the
production registered media socket leaf: 113 contiguous 20ms frames, no render
receipt, and cancellation still removes the exact child after transport completion.
Its network-ACK peer and terminal Task/Native activation are synthetic. A separate
preclaim cancellation also passes; both finish with zero retained cleanup owners
and unchanged private configuration. Ready/claim take 1786/0.44ms in that sample,
but no paired reactivation benchmark or 3–4.5 second target achievement follows.
Main logs are `logs/p7-main-*`, `logs/p7-real-integrated-leaf/` and
`logs/p7_real_tts_probe.py`. Physical playback remains part of unified acceptance.
