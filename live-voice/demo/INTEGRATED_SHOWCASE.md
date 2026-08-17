# Live Voice W2 cumulative P1/P2/P3alpha showcase

> Runtime/acceptance state: see [STATUS.md](../STATUS.md)
> Week 2 pass/fail authority: [INTEGRATED_DEMO_ACCEPTANCE.md](../validation/INTEGRATED_DEMO_ACCEPTANCE.md)
> Environment procedure: [E2E_RUNBOOK.md](../runbooks/E2E_RUNBOOK.md)
> Stable delivery/replacement map: [WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md](../roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md)

This script defines the S3/W2 complete human product journey used by D-071 after automated verification. It does not close Alpha; the historical Alpha A3 journey was `ALPHA_SHOWCASE.md`, now recoverable from Git history. The current product-readiness journey does not retroactively replace it. This is not a second implementation status source: only actually observed behavior may pass, and unavailable or unsupported behavior must remain explicit.

## 1. Showcase claim

In one Session and one cumulative mode, demonstrate:

```text
real microphone
→ formal/fallback Speech and Audio route
→ committed conversational Turn
→ Conversation Runtime / Interaction / Agent Bridge
→ real JiuwenSwarm Agent and Tool
→ streamed or declared fallback speech output
→ continued conversation and exact response interruption
→ committed task command
→ formal Task Core / real D0 Executor
→ TaskEvent / WorkProgress
→ Runtime-arbitrated result notification
```

The UI/trace must identify every segment as `formal`, `fallback`, `demo_substitute`, `unsupported`, or `unknown`.

## 2. Preflight

1. Record the tested source, confirm a clean worktree, and use isolated runtime data plus the exact registered project.
2. Verify selected Speech/Media/Agent/Executor routes and capability flags before opening the microphone.
3. Run a text-only Agent/Tool smoke and a structured task create/status/cancel smoke against the same project and data boundary.
4. Confirm the Demo target is safe for one real side-effecting task or select an isolated/disposable project.
5. Confirm route telemetry, correlated events and sanitized diagnostic logging are active.
6. Confirm text fallback remains usable.

## 3. Integrated script

### Turn 1 — real Agent/Tool path

Speak a short request that forces a read-only Terminal Tool fact, such as the current short commit. The result must come from the real Tool, be displayed truthfully, spoken once and followed by continued listening.

### Turn 2 — non-blocking interaction and interruption

Start a deliberately slow read-only Agent request. While it is working or speaking, add a committed correction. Demonstrate:

- microphone/media remain responsive;
- the new Turn targets the exact current response/round;
- old output is fenced and does not return;
- no unrelated task is cancelled;
- route telemetry shows CR/RM/II/AB owners or explicitly labels the remaining substitute.

### Turn 3 — create a real detached task

> Acceptance rule: closing the bounded D-031 project-bound carrier does not make this cumulative script runnable. Consult STATUS for the formal Integrated-mode dependencies, and do not substitute the shell-disabled Compatibility Adapter for Task Core/Event/Executor authority.

Issue a task intent without confirmation and show zero task mutation plus a clarification/confirmation request. Then give the exact confirmation in the isolated target. Show the real task ID, command ID, target, Executor and accepted/running facts.

### Turn 4 — keep talking while the task runs

Ask an unrelated conversational question. The voice interaction must continue while the task remains independent. Show that response/round cancellation has not changed the task lifecycle.

### Turn 5 — task progress and result

Query the exact task or wait for source-backed progress/terminal return. Show TaskEvent/WorkProgress provenance, exact outcome and Runtime notification arbitration. If information is unavailable, say `unknown` or `unsupported`; do not invent a percentage or result.

### Turn 6 — failure and text degradation

Exercise one controlled Provider/media/permission or Executor failure. Show a bounded error/fallback and continue through text without stale speech, false success or hidden mutation.

## 4. Closeout

1. Exit Live Voice and confirm microphone/audio/timers stop.
2. Confirm the task is in its real final or explicitly nonterminal/reconciliation state; do not assume cancellation rolled back side effects.
3. Display the actual route map and record which user-visible steps passed, failed or were unavailable.
4. Confirm the worktree and isolated data boundary.

Recommended closing statement:

> This run used one cumulative product path. The route trace shows which P1, P2 and P3alpha segments are formal, which use declared fallback, and which remain substitutes. The Agent, Tool, task identity, status and result were real; automated verification and the human observations recorded here determine the W2 product result, not Alpha.
