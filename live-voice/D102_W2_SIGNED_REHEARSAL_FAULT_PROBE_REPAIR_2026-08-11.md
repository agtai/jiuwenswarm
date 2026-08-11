# D102 W2 signed rehearsal fault-probe repair

> Date: 2026-08-11  
> Status: source/test review closed; replacement rehearsal and Gate evidence open  
> Code commit: `38ac3c40`  
> Historical boundary: this record does not rehabilitate the invalid attempt, grant Gate credit, or authorize reuse of any prior candidate, policy, key, browser profile, database, or evidence root.

## Scope and result

The signed rehearsal on candidate `591c96425411cd1a8bb6db11510c9ac08bbe56e2` was closed invalid after all three product-fault runners failed in the P1 fault plane. The six started runtime artifacts were nevertheless stopped cooperatively, closed with clean footers and signed. The isolated Chrome and every dedicated service port were closed, both Git worktrees were clean, no A4 successor was started and no formal policy or Gate evaluation was derived.

The stock product journeys proved useful diagnostic facts without receiving acceptance credit:

- Pair 1 completed prepared-WAV Speech → real Agent → TTS playout, a short Agent turn, a forced read-only Terminal Tool and a completed P3 task with an exact one-line fixture effect that was restored clean. Its P1 retriable probe returned an unexpected nested business outcome.
- Pair 2 completed P1, short and forced-Tool P2, plus a terminal cancelled P3 task with exact terminal ACK and a clean fixture. Its invalid-timeout probe lost the caller's valid nested request identity before the parser returned.
- Pair 3 completed P1 after one pre-Speech capture-gap retry. Its reserve probe used `timeout_ms=1`, which is below the formal Speech minimum, and the same early parser failure also lost the nested request identity. The dependent P2/P3 A→B→C choreography was not started.

The pre-Speech `AUDIO_INPUT_GAP_EXCEEDED` observations were nonfatal capture diagnostics with zero Speech/Agent submission. Prepared WAV remains an operator aid only and creates no physical-microphone or human-heard acceptance claim.

## Repair

Commit `38ac3c40` closes the source defects exposed before a replacement candidate is frozen:

1. `FormalBatchSpeechService` pre-extracts only bounded, trimmed, whitespace-free, valid-UTF-8 `request_id` and `operation_id` values for failed envelopes. Recognition, synthesis and cancellation preserve exact safe caller identity even when later parsing fails; unsafe identities remain `unknown`.
2. Every invalid Speech timeout shape and range now returns the operation-specific `INVALID_SPEECH_TIMEOUT` reason. This includes zero, non-integer, below-minimum and above-maximum inputs and performs no Provider work.
3. The Pair 3 reserve probe uses the formal `MIN_BATCH_TIMEOUT_MS` rather than a parser-invalid 1 ms value.
4. Fault-runner mismatch diagnostics report only escaped public code/reason/retriable fields. They do not include payloads, credentials, raw audio, tokens or private configuration.
5. A production-seam regression composes completed dedicated-media authority with the formal Speech service and the exact planned Pair 1 fault. It proves exact replay, `UNAVAILABLE/SPEECH_W2_RETRIABLE_FAULT_INJECTED`, no Provider call and no capture/operation reservation.

## D-032 / D-046 scenario closure

| Dimension | Result |
|---|---|
| Positive exact planned P1 fault | Exact authenticated completed-media binding returns the planned retriable error twice identically. |
| Pair 2 non-retriable timeout | Zero timeout rejects as `INVALID_ARGUMENT/INVALID_SPEECH_TIMEOUT` while retaining exact safe response identities. |
| Pair 3 zero-effect reserve | Runner sends the public formal minimum; timeout/stale/fresh-capture sequence remains closed and separately bound. |
| Unsafe input | Whitespace-bearing and overlong response identities are not echoed. |
| Synthesis/cancel parity | Early parse failures retain only safe exact request and operation identities. |
| Forbidden Provider/audio/task effects | Invalid timeout and planned-fault tests assert zero Provider calls; the runner still has no direct task authority or persistence import. |
| Replay/concurrency | Existing planned-fault exact replay and concurrency tests remain passing. |
| Flag-off and credential boundary | Existing default-off, server credential and companion-request credential rejection tests remain passing. |

## Verification

- `python -m ruff check` on all five changed source/test files: PASS.
- Focused Speech and fault-runner regression: `87/87` PASS.
- Complete affected Speech RPC, dedicated-media and rehearsal-toolkit matrix: `252/252` PASS with one third-party Authlib deprecation warning.
- `git diff --check`: PASS.

## D-053 reviews

1. Implementation self-review: PASS. It checked safe identity bounds, exact timeout semantics, Provider zero effects, replay behavior, Pair 3 contract coupling and diagnostic privacy.
2. Cold complete-diff review against the signed failure, repository rules, existing behavior and actual tests: PASS after changing diagnostic code/reason rendering to escaped representations so a malformed line cannot inject raw control characters into the runner log.
3. Independent `/review`: not run. No `/review` entry is available in this environment, and the active developer instruction prohibits spawning subagents unless the user explicitly requests them. The recorded substitute is the full `252/252` affected matrix, the production-seam authority regression, Ruff, diff validation and a second complete-diff pass. This substitute is not independent model judgment, so the limitation remains explicit.

## Remaining Gate boundary

The next candidate must be a fresh clean descendant with new candidate-bound policy, browser profile, databases, key roots and evidence roots. Before asking for a new signature, run the real one-page Gateway fault path without evidence and confirm all three P1 probes, especially Pair 1's exact sanitized outcome. Only a fully passing replacement rehearsal may proceed to A4, formal-policy derivation, the four formal experiments and `w2_gate_cli evaluate`. Replacement Ledger credit remains `0/100` until the formal evaluator returns PASS.
