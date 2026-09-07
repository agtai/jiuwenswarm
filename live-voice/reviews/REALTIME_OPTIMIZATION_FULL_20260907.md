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
