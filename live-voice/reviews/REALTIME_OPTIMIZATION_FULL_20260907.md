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
