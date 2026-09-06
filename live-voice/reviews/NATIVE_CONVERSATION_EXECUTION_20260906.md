# Native conversational execution

User-authorized implementation packet, 2026-09-06. The user accepted execution
after the scoped Native architecture audit and the latency/experience discussion.
This packet replaces the previous repair-only active scope; prior fixes remain
regression obligations. Root TESTING.md owns verification and review cadence.

## Intended behavior and scope

Native Realtime owns foreground conversation and typed business proposals.
Authenticated server code validates and dispatches Task operations without a
second semantic model or Agent receipt paraphrase. Real Jiuwen Agent/tools own
analysis; Task Core/Executor keep all canonical business authority. Cascade keeps
its current route and semantics; no silent cross-mode fallback.

Foreground Agent work has identity and lifecycle separate from spoken responses.
Acceptance and queried progress are truthful; speech interruption does not cancel
accepted work. Explicit work/Task cancellation, updates and supersession have
exact identities. Results can be queried and scheduled without reviving retired
audio. Restore authorized context/work facts on Native replacement sessions;
never replay mutations or label generated/unheard text as heard.

Owned defects: incomplete semantic/Agent/reconnect context; read-only question
misrouted to task.adjust; pending-response and cursorless interruption gaps;
Native truncated Task results; existing-session model-selection propagation;
Task projection refresh/retry; retention of critical diagnostic milestones.

## Modules, risk and interfaces

- **Main (Tier 3):** Native business proposal/carrier, Registry dispatch and exact
  authority, context/work orchestration, Runtime/client/server integration,
  accepted decision and deployment. New typed business proposals require an
  explicit version/capability; old strict payloads must not silently change.
- **Media (Tier 2/3):** Engine/Gateway response interruption and sequencing,
  Provider context/result integration once Main's interface is fixed; Native
  audio fixtures and actual serialized client regressions. Preserve ACK truth.
- **Execution (Tier 3):** scoped conversation/context and work ownership module,
  Agent runtime/harness integration, bounds/cancel/recovery tests. Interface
  changes are coordinated with Main before editing shared owners.
- **UI (Tier 2/3):** Task projection, critical diagnostics, actual model selection,
  work/conversation display as protocol becomes available, mounted regressions.

Main owns shared semantics. Workers operate in separate task worktrees and may
edit/test/commit only assigned files to their task branch. Main alone integrates;
workers must not merge, change the integration branch or update remote refs.
Main continues on the clean task branch; the running Demo stays on its current
process until the candidate is verified. No unrelated worktree is touched.

Dependencies are explicit: proposal and work contracts precede their media/UI
integration. Existing Task authority and authenticated context selection precede
Provider disclosure. Stop generation and played-cursor truncation are separate;
an already admitted work item is not cancelled by retiring its speech response.

## Work sequence

1. Record D-119's accepted Native contract expansion and scoped tests; baseline
   current connected seams. Use isolated test data/logs, not the running Demo.
2. Implement typed Task/read/Agent-work proposals and exact authorized dispatch;
   complete context/result transfer and model binding. No new keyword classifier.
3. Implement independent work/result lifecycle and Native response arbitration;
   integrate interruption fixes, recovery, late results and bounded capacity.
4. Integrate Task projection, model confirmation, work state, text/notification
   ownership and milestone diagnostics with actual strict serialization.
5. Review coherent diffs independently, fix findings, run affected Python/Node
   and mounted integration checks and production build. Test Native and Cascade.
6. Commit verified coherent modules, deploy through existing controlled launcher
   if needed, preserving credentials/project/data/Task state. Bind source/assets
   and real Provider/Agent evidence; report physical-user acceptance separately.

## Acceptance and exclusions

Use all applicable P/N/B/S/T/C/R/I/F/K/X dimensions in root TESTING.md, particularly:
real positive Task A/B create/read/adjust/cancel; independent refund question has
zero Task mutation; long analysis plus interjected question/update/cancel; exact
context after prior Native speech and reconnection; complete long result tail;
pending-created and cursorless interruption; delayed/duplicate/multiple function
results; unknown outcomes and retry without replay; stale/foreign scope rejection
with zero forbidden Agent/Tool/Task/audio/history effects; Task refresh failure
without re-execution; existing-session model switch; one Task-event notification;
critical timeline retention under high-frequency audio; Cascade regressions.

Required seams include Registry -> actual Agent WebSocket serialization -> strict
Gateway client -> media owner -> mounted UI, not just independent helper mocks.
Reuse the existing audit's two failing current-behavior probes and prior scoped
tests. Reclassify old exclusions when their boundary is now owned. Measure useful
receipt/first verified conclusion/final result/first audible and interruption
separately; filler does not establish a latency improvement.

No broad performance tuning, new provider/model settings, production/public
deployment, remote update, fixture answers, forged ACK, source-text keyword
policy, or wholesale Cascade rewrite. A new work store must make its restart
semantics explicit; accepted/pending/unknown cannot be called completed.

## Verification record

Implementation and checks are pending. Per-module exact evidence and integration
results will replace this paragraph as work completes. No candidate/physical PASS
is implied by accepting this packet.
