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
