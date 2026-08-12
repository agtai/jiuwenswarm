# Live Voice W2 Integrated Demo product acceptance

> Run state and current checklist: [STATUS.md](../STATUS.md)
> Authority: D-071, with D-046 risk tiers and D-074 staged review
> Manual journey: [INTEGRATED_SHOWCASE.md](../demo/INTEGRATED_SHOWCASE.md)

This contract decides whether the cumulative P1/P2/P3alpha W2 Demo (D-075 stage S3) is product-accepted. It is retained for W2 regression/reproduction and does not define Alpha A0–A3. Under D-071, acceptance requires applicable automated verification plus one complete human product journey. It does not require a signed evidence Gate, Replacement Ledger score, fixed artifact manifest or repeated full-showcase runs.

`W2` is a delivery-order label, not a promised calendar week. A PASS proves the bounded Integrated Demo product scope only; it does not claim Production, complete P3, D1/D2, public compatibility or an audit-grade release certification.

## 1. Tested-source and environment record

- Identify the tested Git commit and confirm the source worktree has no unexplained change before and after the run.
- Record the actual browser/OS, input/output device class, Provider/model labels, persistent Session, project/fixture and enabled product flags without recording credentials.
- Use the real JiuwenSwarm Agent and real Tool/Task sources. Fakes remain limited to automated tests and controlled fault injection.
- Keep machine-private logs outside Git. A concise sanitized acceptance record is sufficient; signatures, trust policies, evidence owners and fixed evidence roots are not required.
- A previously passed human step may be reused when the tested source and relevant environment are unchanged and no later change affects that behavior. Do not repeat it merely for ceremony.

## 2. Automated verification

Run the risk-proportional checks applicable to the final W2 source:

1. affected Python and TypeScript unit/contract/integration suites;
2. positive P1/P2/P3alpha product journeys;
3. committed-only, identity/scope, replay, stale-output, cancel and wrong-target negative cases;
4. feature-off and original text Chat/Agent/Tool regressions;
5. P3 create/cancel/retry/restart, outbox/lease/cleanup and terminal UI reconciliation;
6. Speech/Media boundaries, Provider failure, playout/capture stop and zero forbidden side effects;
7. frontend build, formatting/static checks and `git diff --check`.

Required positive scenarios must pass. Required negative scenarios must reject or fail closed, and every path capable of Agent, Tool, Task, history, audio or protected-state mutation must prove zero forbidden effects. A known flaky, skipped or unexecuted applicable check remains `PARTIAL` until explained and accepted.

## 3. One complete human product journey

The user performs the following applicable steps once on the tested source. Automated assertions cannot replace the named human observations.

### P1 — physical speech and playout

1. Start capture with the selected physical input device.
2. Speak a short request, inspect/edit the recognized final text and explicitly confirm it.
3. Verify only the confirmed text reaches the real Agent.
4. Verify the real response is displayed and heard completely through TTS.
5. Verify the successor capture starts and can be stopped without a second unintended Agent/Tool submission.

### P2 — Agent/Tool, correction and interruption

1. Submit a short request that forces one safe read-only Tool operation and verify its real result.
2. Start a deliberately slower response, then issue a committed correction or interruption.
3. Verify the microphone and UI remain responsive, old output does not return, the new Turn targets the correct response, and no unrelated task is cancelled.
4. Verify the truthful visible status, history and audible result.

### P3alpha — detached task and non-blocking behavior

1. Create a real task only after the product's required clarification/confirmation; unconfirmed intent must produce zero task mutation.
2. While it runs, continue an unrelated P1/P2 conversation and verify neither path freezes or cancels the other.
3. Exercise the bounded same-task A→B→C journey: cancel A, retry B to a truthful terminal result, then retry C and observe the documented restart/reconciliation behavior.
4. Verify task ID, attempt, status, result and progress remain bound to the correct task and are visible on the origin surface.

### Recovery and degradation

1. Refresh or reconnect the same product page and verify current P2/P3 state recovers without duplicate dispatch or stale output.
2. Exercise one safe visible Provider/media/permission or Executor failure and confirm a bounded truthful error plus a usable text fallback.
3. Close Live Voice and confirm microphone, audio, timers, tasks, pending outbox, owners/leases and dedicated services return to their expected final or explicitly reported nonterminal state.

## 4. Acceptance decision

The result is one of:

- `PASS — W2 PRODUCT-ACCEPTED`: applicable automated checks pass, every applicable human step above passes, and no unresolved critical product defect remains;
- `PARTIAL — MANUAL ACCEPTANCE OPEN`: implementation and automated verification are usable, but one or more human-visible steps have not yet been observed or need an affected rerun;
- `BLOCKED`: a required external condition such as device, Provider, project or browser permission is unavailable;
- `FAIL`: an applicable product requirement or invariant fails.

Record:

```text
tested_source:
worktree_clean_before_after:
automated_checks:
human_environment:
P1_result:
P2_result:
P3alpha_result:
recovery_and_degradation_result:
limitations:
acceptance_result:
```

There is no numeric product score. Historical Replacement Ledger `0/100` means only that the retired signed-evidence scheme was never completed; it does not describe feature completeness and must not block W2 or Alpha.
