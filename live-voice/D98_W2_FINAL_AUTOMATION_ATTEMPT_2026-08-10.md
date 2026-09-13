# D98 W2 final automation attempt record — 2026-08-10

## Scope and status

This frozen record covers the final source-hardening batch through implementation candidate `f93ca5bd309567c5e5a44737d4a75f9cb178fa89` and the user's one-shot, unsigned automatic runtime attempt on that candidate.

The source batch is review-closed. The runtime attempt is **not** acceptance evidence and did not complete Pair 1. Integrated Demo remains `SOURCE-INTEGRATED / GATE-PARTIAL`, and the Replacement Ledger remains `0/100`.

## Source batch

The three commits after the previously pushed orchestration baseline close related browser/runtime authority boundaries:

- `73426af7` keeps recognized-speech confirmation inside the page, holds the P3 safety lock while task-origin dispatch is pending, binds recognized speech to the exact P2 activation and fences stale or duplicate continuations.
- `cfba71ff` makes the automatic product-fault runner anchor on the current successful stock Speech exchange and join only exact media and P2 authority across browser socket changes.
- `f93ca5bd` makes uplink completion explicit: Gateway retains completion before returning the exact detach receipt, the browser waits for that receipt before Speech, and the runner enforces the same ordering.

The batch does not weaken credential ownership, enable evidence, add a direct registry path or turn prepared audio into physical-device evidence.

## Verification and review

- Integrated Web suite, including TypeScript compilation and bundled mounted tests: `239/239` PASS.
- Affected Python Gateway, registration and runner selection: `185/185` PASS.
- Complete rehearsal toolkit suite: `146/146` PASS.
- Full frontend `tsc --noEmit`: PASS.
- Ruff and `git diff --check`: PASS.
- D-053 self-review and cold complete-diff review: PASS after the completion-receipt corrections.
- Independent read-only review: PASS with no remaining P0/P1/P2 finding. It verified retained-before-receipt ordering, exact browser receipt matching, timeout/cleanup fencing and the runner's physical-close boundary.

These results establish source and deterministic-test closure only. They do not substitute for a successful browser/service journey.

## Final one-shot runtime result

The attempt used fresh no-evidence service processes, a fresh Session and disposable data/project state, the existing isolated Chrome profile, the repository prepared WAV and the production Gateway/AgentServer route. No policy evidence owner was enabled and no JSONL evidence artifact was produced.

The exact observed sequence was:

1. The single full navigation reached the intended Session; the formal Start control was visible and P2 activation generation 1 was active.
2. The one permitted P1 Start failed before entering `capturing` with `AUDIO_INPUT_GAP_EXCEEDED`.
3. No Stop/recognize call, Speech Provider request, Agent confirmation/submission, P2 business operation, P3 confirmation/mutation or product-fault probe followed.
4. No reload, retry or duplicate mutation was performed. The browser retained the failure scene.
5. The waiting automatic runner was interrupted, and the fresh Gateway and AgentServer processes were stopped gracefully. Shutdown-only connection closure is not treated as the original failure.

`AUDIO_INPUT_GAP_EXCEEDED` is the browser AudioWorklet's fail-closed result for an input timeline gap beyond its bounded transient/rolling budget. This attempt identifies the stable boundary but does not establish whether the trigger was the prepared-audio device path, Chrome scheduling/profile state or another runtime condition. Raw machine logs and private runtime paths remain outside Git.

## Acceptance judgment and continuation boundary

- Automatic runtime validation is **incomplete**; Pair 1 did not pass, so Pairs 2–4 were not started.
- It is not truthful to say that only final human acceptance remains.
- Per the user's explicit instruction, no further runtime retry belongs to this task after this failed one-shot attempt.
- Any future continuation requires new user direction. Before another full journey, it should first produce a deterministic, no-evidence reproduction of the AudioWorklet input-gap boundary, identify the cause, apply the smallest reviewed correction if needed and pass the affected browser checks. A new end-to-end attempt must not be inferred or silently started from this record.
- Physical microphone capture, complete audible TTS, real-timing barge-in, P3 UI receipts, signed runtime artifacts and `w2_gate_cli evaluate` all remain open.
