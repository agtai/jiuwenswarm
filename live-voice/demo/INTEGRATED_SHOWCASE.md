# Live Voice cumulative P1/P2/P3alpha showcase

> Status: `NOT RUNNABLE YET`
> Week 2 pass/fail authority: [INTEGRATED_DEMO_ACCEPTANCE.md](../validation/INTEGRATED_DEMO_ACCEPTANCE.md)
> Environment procedure: [E2E_RUNBOOK.md](../runbooks/E2E_RUNBOOK.md)

This script demonstrates the cumulative engineering route after formal modules begin replacing V0 shortcuts. It never replaces acceptance evidence. Until the runbook's Integrated mode is implemented and route telemetry identifies every segment, this script is a planned Gate and must not be presented as a working capability.

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

1. Verify immutable candidate SHA, clean worktree, isolated runtime data and exact registered project.
2. Verify selected Speech/Media/Agent/Executor routes and capability flags before opening the microphone.
3. Run a text-only Agent/Tool smoke and a structured task create/status/cancel smoke against the same project and data boundary.
4. Confirm the Demo target is safe for one real side-effecting task or select an isolated/disposable project.
5. Confirm route telemetry, correlated events and sanitized evidence capture are active.
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
3. Display the final Replacement Ledger score and actual route map.
4. Confirm the worktree and isolated data/evidence boundary.

Recommended closing statement:

> This run used one cumulative product path. The route trace shows which P1, P2 and P3alpha segments are formal, which use declared fallback, and which remain substitutes. The Agent, Tool, task identity, status and result were real; the score and limitations come from the Week 2 acceptance contract, not from the presentation alone.
