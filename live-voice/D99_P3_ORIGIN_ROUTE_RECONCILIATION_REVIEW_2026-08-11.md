# D99 P3 origin-route reconciliation review — 2026-08-11

## Scope and disposition

This record covers the related W2 repair set through local implementation commit `a0453ff19`:

- `1cc0e9cb2` preserves the complete Agent-only provider binding across repeated dotenv loads and process epochs;
- `bf6873596` accepts only request-bound, closed product business errors while continuing to reject unbound Gateway transport failures;
- `a0453ff19` reconciles P3 product progress against authoritative `task.events`, advances the origin route panel from `accepted` to the exact terminal outcome, fences stale Session/task/attempt/connection responses and fixes failed/cancelled reconciliation reason pairing.

The source and deterministic affected-test boundary is closed. Runtime validation is not closed, no candidate has been frozen from this batch, no policy/key/signature/database evidence was created, and the Replacement Ledger remains `0/100`.

## Root cause and correction

The stock Web subscription parsed each `live_voice.task.progress` notification once, but then passed the parsed object back to the raw-envelope adopter. The parsed object deliberately no longer has the raw source `extensions` at the same top-level shape, so the second parse returned `null`. The prior code still retained the delivery ACK, but never retained the UI progress value or advanced the origin task card. This explains the observed backend terminal/UI `accepted` split.

The correction adds a typed parsed-event adoption entry without weakening the raw parser. For each new owned delivery the panel now:

1. requires the exact active Session, progress-generation, origin, task and correlation binding;
2. requires the current `FormalTaskControlLeaf` to own the same task and attempt;
3. validates the projected state, terminal outcome, persistent producer and source event type;
4. queries complete `task.events` into an isolated strict probe;
5. publishes the validated history to the live leaf only while Session, connection generation, owner epoch, task and attempt remain current;
6. adopts the exact progress receipt, updates the panel to the authoritative terminal outcome and only then retains the UI ACK.

Mismatch, foreign task, old attempt, disconnect and late response paths do not update the live replica or retain an ACK. Reconnect uses the new leaf connection generation and can reconcile the same exact task. Backend startup-reconciliation observations now pair `failed` with `TASK_FAILURE` and `cancelled` with `CANCEL_TERMINAL`; other terminal outcomes retain no reason code as required by the observability schema.

## D-053 review

- Implementation self-review: PASS after finding and fixing the parsed-event double-parse defect exposed by the first mounted test.
- Cold complete-diff review against the user request, repository rules, existing lifecycle behavior and actual tests: PASS with no remaining P0/P1/P2 finding. It checked completed/failed UI truth, reconciliation mismatch, reconnect, stale Session/task/attempt/connection fencing, ACK ordering, `1cc0e9cb2` provider isolation and `bf6873596` request/error binding.
- Independent `/review`: unavailable in this task because the user explicitly prohibited delegation to another agent and no separate `/review` tool is exposed. The substitute was a fresh complete-diff cold pass plus strict build, format/static checks and the cumulative regression runs below. This record does not claim an independent semantic reviewer ran; that limitation remains explicit rather than being converted into Gate credit.

## Verification

- Integrated Web strict compilation, bundled unit and mounted component suite: `247/247` PASS.
- Complete W2 rehearsal toolkit plus dotenv/observability affected set: `188/188` PASS.
- Tier-3 affected Python regression across Live Voice, AgentServer P3 route, Gateway ACP and Web channel: `1481/1481` PASS in 109.21 seconds.
- Frontend production `tsc && vite build`: PASS.
- Ruff format/check, Prettier and `git diff --check`: PASS.
- ESLint was not runnable because this frontend tree has no ESLint configuration; no ESLint PASS is claimed.
- Scoped mypy was not clean because `product_w2_observability.py` already reports 30 pre-existing typing errors, chiefly failure to narrow parameters declared as `object`; no mypy PASS is claimed.

These results establish source and deterministic-test closure only. They do not prove the real browser/service journey, two AgentServer epochs, graceful `p2.close`, physical microphone, audible TTS, cleanup or Gate evidence.

## Next boundary

Run the unsigned validation-ready lane on a clean descendant of `a0453ff19`: deterministic WAV, one isolated Chrome page at the exact persisted `/chat/<session_id>`, one CDP page target, exact project/model display, P1, short real-Agent P2 with a forced read-only Terminal Tool, completed and failed P3 origin-panel truth, two consecutive AgentServer epochs, graceful `p2.close` and complete task/outbox/lease/port/fixture cleanup. Keep policy, key, signature, evidence owners and Gate credit disabled. Only after that lane passes may one fresh candidate and its rehearsal authority be created.
