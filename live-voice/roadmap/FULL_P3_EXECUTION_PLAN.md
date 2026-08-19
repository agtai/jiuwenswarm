# Complete P3 execution plan

> Status: **PREPARATORY EXECUTION CONTRACT — NOT AN ACTIVE STATUS OR COMPLETION
> CLAIM.** Current product judgement, capability status and the active packet
> remain owned by [STATUS](../STATUS.md). The D-085
> [module code-fact audit](../reviews/MODULE_CODE_FACT_AUDIT_2026-08-17.md) is
> complete and synchronized; its P3 findings are the evidence baseline for
> sizing and activating this plan. This document defines the complete P3
> outcome, coherent workload, dependencies, implementation method and
> acceptance boundary; it does not award implementation, test, review or
> product credit.
>
> Date: 2026-08-18
>
> Sequencing update (2026-08-19): [D-086](../decisions/DECISIONS.md) closes
> P3-G0 as the audited/source-verified P3 authority foundation, transfers the
> failed post-TTS hands-free continuation and combined physical candidate
> Journey to later cumulative P1/P2/P3 acceptance, and allows P3-1 to start.
> This does not convert `f24dd17d` into a controlled-candidate PASS.

## 1. Purpose and required product outcome

The objective is to move from the accepted P3alpha foundation boundary to
complete P3 Voice-driven Agent Control without turning conversation state, Demo
state or legacy scheduler state into Task authority.

Complete P3 means that a user can:

- create more than one independent background Task;
- continue foreground dialogue while those Tasks run;
- address the intended Task explicitly or complete a bounded clarification;
- query Task status, progress, blocking questions, decisions and results;
- provide additional input, update goals or constraints, change priority,
  pause, resume and cancel when the selected Executor/scheduler composition
  declares the capability;
- create an explicit successor revision when an immutable terminal Task must be
  changed;
- disconnect and reconnect without losing durable Task truth, unread results or
  the ability to replay applicable events;
- receive truthful terminal notification and retrieve the legal immutable
  `TaskResult` through text or voice presentation;
- receive D0, D1 and D2 behaviour only to the level actually declared and
  proven by the selected Executor.

The product is not complete merely because command endpoints exist. The
structured API, natural-language bridge, Store, Executor, Integrated Web UI and
voice notification path must all preserve the same identity, authority, state,
cancel, result and recovery semantics on a real path.

Complete P3 is one required component of the D-084 `feature complete` boundary.
It does not by itself prove formal P1/P2 quality, the full Integrated Web
feature-complete carrier, productized deployment or Production readiness.

## 2. Authorities and use of historical material

This plan is interpreted in the following order:

1. current code, tests, configuration, registration and runtime composition at
   the D-085 audited baseline, with affected rows re-checked after later code
   changes;
2. [STATUS](../STATUS.md) for mutable progress, blockers, dependencies and the
   active execution packet;
3. D-084 through D-086 in [DECISIONS](../decisions/DECISIONS.md);
4. stable P1/P2/P3 and shared-contract boundaries in
   [the accepted design snapshot](../architecture/FULL_SOLUTION_2026-07-30.md)
   sections 2, 4 and 5;
5. [root TESTING](../../TESTING.md) for D-032 scenario dimensions, D-046 risk
   tiers and D-074 review cadence;
6. exact-source historical regression contracts where a current package still
   owns the same behaviour.

Historical W2 and P3 records are used narrowly:

- [D104](../D104_P3_REFRESH_RECOVERY_AND_W2_ACCEPTANCE_CONTINUATION_2026-08-11.md)
  supplies the useful pattern of observed boundary, repair contract,
  verification and acceptance separation;
- [D119](../D119_RUNNING_TASK_ADJUSTMENT_AND_TERMINAL_NOTIFICATION_REVIEW_2026-08-16.md)
  preserves adjustment, terminal notification and exact-source regression
  oracles;
- [the P3alpha replacement review](../P3ALPHA_REPLACEMENT_REVIEW_2026-08-05.md)
  preserves Store/Core/Executor authority and fault scenarios that remain
  applicable.

Their old stage names, pass counts, source candidates, timeboxes, signed Gate,
rehearsal runner and next action are historical only. They must not define the
current queue or receive current product credit.

## 3. Activation and baseline Gate

Implementation expansion under this plan starts only after all of the following
are true:

1. The D-085 audit has completed, been synchronized and mapped every P3 finding
   to Task Control Core/Store, Executor & Durability, Voice–Task Bridge or a
   named cross-module owner.
2. STATUS has been reconciled to that exact audited source. A code change after
   the audit repeats the affected audit row before completion credit.
3. The confirmed product-truth blockers in the current packet have been closed
   or explicitly transferred to a package below with no false candidate claim.
4. P3-G0 has closed under D-086 without inventing controlled-candidate credit;
   its deferred physical Journey remains a declared input to P3-9 and the later
   cumulative product decision.
5. Applicable W2/S7/S8 or rehearsal oracles needed by the first P3 packages are
   identified and move with their first current capability owner; no old runner
   is retired before its remaining oracles move.
6. STATUS activates one coherent P3 package with its capability, risk,
   dependencies, scope, exclusions and acceptance rather than activating this
   entire document as one undifferentiated change.

Design clarification and audit-to-package mapping may occur before this Gate.
Product implementation must not use this preparatory plan to bypass D-085,
D-086's explicit risk transfer or the later cumulative acceptance route.

## 4. Frozen ownership model

The following ownership boundaries are non-negotiable unless a newer accepted
decision changes them.

| Owner | Owns | Must not own or infer |
|---|---|---|
| Task Control Core/Store | Canonical Task, Attempt, Command, Event, Result and revision records; legal transitions; command idempotency; durable outbox; reconciliation settlement | Conversation response state, TTS arbitration, Executor-internal execution or UI-selected “current Task” as authority |
| Executor & Durability | Actual Attempt execution; capability declaration; admission observation; progress/checkpoint/effect evidence; attempt cancel/recovery | Canonical Task mutation, Task presentation, unsupported capability success or inferred terminal outcome |
| Voice–Task Bridge | Conversion of committed natural-language intent into a bounded Task command or clarification; target resolution; confirmation policy | Persistence, execution, Task truth, direct TTS or mutation from partial/ambiguous input |
| Structured Command Adapter | Authenticated and authorized structured Task commands | Natural-language guessing, Executor state or presentation truth |
| Conversation Runtime | Interaction/turn/response/generation and voice presentation arbitration | Task lifecycle, Task result creation or implicit task cancellation on barge-in/disconnect |
| Agent Bridge/Harness | Conversational round truth and provenance-preserving WorkProgress mapping | TaskCommand creation or Task completion inference from text/tool chunks |
| Integrated Web | User intent capture, explicit Task selection, controls and projections validated against backend authority | Canonical Task/Attempt state, terminal truth inferred from conversation/project files or a local hint |

Identity relationships must remain explicit:

- `task_id` identifies the durable user work item across conversations and
  reconnects;
- `attempt_id` identifies one actual execution or a contractually defined
  recovery execution;
- `command_id` identifies one idempotent requested operation and its immutable
  fingerprint;
- `event_id` plus source sequence identifies one authoritative lifecycle fact;
- `TaskResult` binds the exact Task and producing Attempt and is immutable;
- presentation/ACK identity is separate from Task/Event identity and cannot
  mutate Task truth.

`playback.stop`, `response.cancel`, `round.cancel` and `task.cancel` remain four
different scopes. Speech barge-in, browser disconnect, response replacement or
Session close must never silently widen into Task cancellation.

## 5. Relative workload and package map

The size labels describe semantic and integration load, not elapsed time:

- **S** — one bounded owner or audit-to-contract settlement;
- **M** — one main owner plus a narrow integration seam;
- **L** — multiple state surfaces or one real cross-module journey;
- **XL** — shared authority/durability, schema/state evolution or cumulative
  product acceptance requiring several owners.

Historical calendar estimates are not reused. An affected-row re-audit or later
code fact may reduce, expand or reorder a package before that package starts.

| Package | Outcome | Primary owner(s) | Risk | Relative size | Hard dependency |
|---|---|---|---:|---:|---|
| `P3-G0` | Audited authoritative P3 foundation with deferred cumulative candidate acceptance | Integration Owner plus affected truth owners | Tier 0 audit / Tier 3 repair | XL composite | D-085 complete; D-086 scope closure |
| `P3-1` | Canonical multi-Task identity, state, Store and migration | Task Control Core/Store | Tier 3 | XL | `P3-G0` |
| `P3-2` | Complete command, adjustment and successor-revision semantics | Task Core/Store plus Executor seam | Tier 3 | XL | `P3-1` |
| `P3-3` | Capability-driven Executor admission and Attempt lifecycle | Executor & Durability plus Task Core | Tier 3 | XL | `P3-1` |
| `P3-4` | Truthful D0, supported D1 and supported D2 recovery semantics | Executor & Durability plus Store | Tier 3 | XL | `P3-3` |
| `P3-5` | Result, event replay, unread and terminal-notification durability | Task Core/Store, Runtime and Web projection | Tier 3 | L | `P3-1`, `P3-G0` |
| `P3-6` | Generalized multi-Task Voice–Task Bridge and text/voice parity | Voice–Task Bridge plus Task Core | Tier 3 | XL | `P3-1`, `P3-2`, `P3-5` |
| `P3-7` | Formal Integrated Web P3 control and recovery experience | Web composition, Runtime and P3 owners | Tier 2/3 | L | `P3-2` through `P3-6` as applicable |
| `P3-8` | Observability, configuration, privacy and authority retirement | Shared composition/operations owners | Tier 2/3 | M | Starts with `P3-1`; retires after `P3-7` |
| `P3-9` | Cumulative complete-P3 verification, review and human acceptance | Integration Owner and independent reviewers | Tier 3 | XL | All applicable packages |

The provisional workload is therefore ten packages: including the composite
`P3-G0` prerequisite, seven are XL, two are L and one is M. No package is small
after current boundaries are applied. This is a substantial capability program
rather than a single defect batch. The packages overlap in calendar time after
their shared contracts are frozen, so the sizes must not be added as days.

## 6. Dependency graph and execution waves

```mermaid
flowchart TD
    G0["P3-G0: audited + source-verified P3 foundation"]
    M["P3-1: canonical multi-Task model"]
    C["P3-2: complete commands + revision"]
    E["P3-3: Executor capability + Attempt truth"]
    D["P3-4: D0/D1/D2 durability"]
    R["P3-5: result + replay + unread"]
    B["P3-6: Voice–Task Bridge"]
    W["P3-7: Integrated Web P3"]
    O["P3-8: observability + retirement"]
    A["P3-9: complete-P3 acceptance"]

    G0 --> M
    M --> C
    M --> E
    M --> R
    E --> D
    C --> B
    R --> B
    C --> W
    D --> W
    R --> W
    B --> W
    M --> O
    W --> O
    C --> A
    D --> A
    R --> A
    B --> A
    W --> A
    O --> A
```

Execution waves are:

1. **Foundation wave:** consume the synchronized D-085 findings, land and
   verify the authoritative P3 truth repairs, and record any deferred cumulative
   candidate condition without a false PASS (`P3-G0`).
2. **Shared-contract wave:** freeze multi-Task identity, state, migration and
   capability vocabulary, then implement `P3-1`.
3. **Core parallel wave:** execute `P3-2`, `P3-3` and the storage part of
   `P3-5` in non-overlapping ownership lanes after their common contract is
   stable.
4. **Recovery and carrier wave:** execute `P3-4`, `P3-6`, the presentation part
   of `P3-5` and `P3-7`; integrate each real seam before broadening the next.
5. **Closure wave:** finish `P3-8`, migrate/retire old authority and run
   `P3-9` on one exact clean source.

## 7. Package contracts

### 7.1 `P3-G0` — authoritative P3 foundation

#### Do

- Consume the D-085 P3 findings without copying subagent conclusions directly
  into product status.
- Confirm or correct the current Task/Attempt/Event/Command/Result owner map and
  actual formal/legacy/Demo composition.
- Close the confirmed terminalization, admission truth, Task-truth isolation,
  result-context and related recovery defects owned by the current packet.
- Ensure an accepted Task blocked by admission or project capacity is not
  represented as an authoritative running Attempt.
- Ensure Agent completion cannot leave application/result/terminal settlement
  disconnected while an owner or lease renews indefinitely.
- Record the exact controlled-candidate outcome. Under D-086, transfer the
  demonstrated P1/P2 post-TTS continuation defect and the uncompleted combined
  Journey to later cumulative acceptance without granting a false PASS.

#### How

- Convert each audit finding into an owner-scoped implementation packet rather
  than one cross-repository repair pile.
- Freeze the terminal path as one provenance-preserving chain:
  Agent/Executor observation → validation → application → legal TaskResult →
  Task/Attempt terminal event → outbox/lease settlement → presentation.
- Keep ACK, accepted, queued, running, result and terminal facts distinct.
- Reserve result-context capacity or use a bounded result-specific path so
  ordinary dialogue occupancy cannot invalidate a legal TaskResult.
- Use focused and affected tests from current discovery; historical exact-
  source PASS remains regression evidence only.

#### Done when

- D-085 is complete and STATUS matches the exact source.
- Every confirmed high-risk P3 truth defect has an authoritative source fix and
  applicable D-032 automated evidence.
- Leases/outbox work settle or enter bounded, truthful recovery states.
- The uncompleted real adjustment/result/terminal Journey and the P1/P2
  continuation defect are explicitly transferred to P3-9/cumulative product
  acceptance with no inherited physical credit.
- No known unresolved P3 authority defect is hidden by moving to expansion;
  any later finding returns to its owning P3 package.

### 7.2 `P3-1` — canonical multi-Task model, Store and migration

#### Do

- Support multiple non-terminal Tasks in one authorized project/scope without a
  single “current Task” pointer becoming mutation authority.
- Freeze canonical relationships among Task, Attempt, Command, Event,
  TaskResult, predecessor/successor revision and presentation cursor.
- Extend the Store and query surface for addressed Task list/status/events/
  result access, durable pagination/cursors where required and restart-safe
  reconstruction.
- Provide a versioned migration from the D-085-confirmed current schema and
  persisted records without silently discarding or relabelling historical
  truth.
- Freeze the full state vocabulary before UI or Bridge implementation. In
  particular, decide whether `queued` and `paused` are canonical states,
  capability-specific substates or strictly derived projections.

#### How

- Treat any UI/session “current Task” value only as a selection hint. Revalidate
  exact subject/project/scope/task identity against Task Core before every
  read or mutation.
- Require structured mutation commands to carry an exact `task_id`; natural-
  language commands may reach that identity only through the Bridge's bounded
  target resolution.
- Keep Task acceptance separate from Attempt execution. A persisted Task may be
  accepted/queued while no authoritative running Attempt exists.
- Define one legal transition table with terminal immutability and explicit
  unknown/interrupted handling. Store reducer, API projection, Executor mapping
  and Web vocabulary must derive from that table.
- Make migration atomic, idempotent and fail-closed on corrupt or unknown
  representations. Preserve enough version/provenance to diagnose and retry a
  failed migration safely.
- Keep read queries and event/result projection mutation-free.

#### Done when

- Two or more Tasks can be active, queried and controlled independently across
  foreground dialogue, refresh and restart.
- Wrong, stale, foreign or ambiguous task identity has zero Task/Attempt/
  Executor/file/presentation mutation.
- Duplicate or conflicting command identity cannot allocate another Task or
  Attempt.
- The Store reconstructs exactly the same canonical truth after restart, or
  reports a bounded corruption/migration error without partial promotion.
- “Current Task” convenience cannot redirect a command intended for another
  Task.
- Current persisted data migrates with explicit compatibility evidence and no
  historical status invention.

### 7.3 `P3-2` — complete command, adjustment and revision semantics

#### Do

Provide a coherent command model for:

| Operation | Required product semantics |
|---|---|
| `create` | Persist one Task intent and command result; admission/execution truth follows separately |
| `get/list/status/events/result` | Read canonical records with zero mutation and exact scope filtering |
| `update` | Change a queued goal/constraint atomically before dispatch, or a running one only at a supported and proven Executor checkpoint |
| `provide_input` | Answer the exact current blocking question/decision context without becoming a system instruction |
| `pause` | Request pause only when the selected Executor can reach and prove a paused boundary |
| `resume` | Resume only the exact paused/recoverable Task/Attempt according to the frozen recovery contract |
| `reprioritize` | Change scheduling priority without pretending that execution state changed |
| `cancel` | Idempotently request cancellation of the exact target; ACK is not terminal cancellation |
| successor revision | Explicitly create a new Task linked to an immutable terminal predecessor; never rewrite the old TaskResult |

#### How

- Use one versioned command envelope with stable command identity, immutable
  fingerprint, subject/project/scope, exact target, expected version or state,
  capability requirements, confirmation proof and bounded untrusted payload.
- Persist command admission and outbox work atomically with the canonical facts
  needed to replay the original result.
- Separate `accepted`, `applied`, `rejected`, `unsupported`, `conflict`,
  `timeout` and `unknown`. An accepted command cannot be announced as applied.
- Define operation-specific legal states and races before implementation. A
  concurrent terminal event may defeat update/pause/cancel without changing
  terminal truth.
- Reuse D119 adjustment oracles only where current code still owns the same
  contract; generalize away from the exact Demo checkpoint and grammar.
- Keep terminal Task and TaskResult immutable. Successor creation is explicit,
  authorized and idempotent, with a durable predecessor link and a new
  `task_id`.
- Do not invent a separate `approve` operation unless a new accepted product
  decision requires it. A current blocking answer should use the frozen
  `provide_input`/decision contract or return unsupported.

#### Done when

- Every declared operation has positive, invalid-state, wrong-target,
  duplicate/conflict, concurrent-terminal, restart and unsupported-capability
  evidence where applicable.
- Multiple ordered updates or inputs are applied once and in authoritative
  order, or rejected with no partial Executor/Store effect.
- Pause/resume and priority labels reflect actual Executor/scheduler capability;
  unsupported operations never appear successful.
- Terminal revisions preserve the predecessor and result byte-for-byte while a
  new Task receives the revised goal.
- Text and voice callers observe the same command result and TaskEvent truth.

### 7.4 `P3-3` — capability-driven Executor admission and Attempt lifecycle

#### Do

- Freeze versioned Executor and scheduling capability descriptions covering
  start, status, cancel, update/input, pause/resume, priority where applicable,
  checkpoint/recover and reconciliation.
- Select an Executor only when its declared capabilities satisfy the Task's
  requirements and authorized context.
- Separate Task acceptance, queue/admission state, Attempt allocation,
  authoritative running evidence and terminal outcome.
- Support multiple Task admissions without cross-project or cross-Task lease,
  target or working-tree collision.
- Bound lease ownership, heartbeat, timeout, orphan detection, outbox claim and
  retry so a stuck Adapter cannot remain “running” indefinitely.
- Normalize real Executor progress and terminal evidence without inferring
  success from stream end, Agent text, files or a successful transport ACK.

#### How

- Make capability negotiation a formal input to admission; missing capability
  returns stable `unsupported` before mutation that assumes the operation.
- Bind each Attempt to exact task, executor, project target, origin namespace,
  idempotency identity, owner token and contract version.
- Fence stale owners and late observations with lease/claim tokens. A retry of
  the same external dispatch reuses the contracted identity rather than
  creating duplicate work.
- Represent `EXECUTOR_PROJECT_BUSY` as accepted/queued or rejected according to
  the frozen admission contract, never as an observed running Attempt.
- Define bounded timeout and orphan outcomes. Unknown external outcome remains
  unknown or requires reconciliation; it never becomes “never dispatched” or
  completed.
- Preserve exact cancel targeting. Cancel acceptance does not release ownership
  or publish terminal until authoritative settlement.

#### Done when

- Capability selection, unsupported paths and fallback are externally
  observable and truthful.
- Two eligible Tasks can progress without sharing Attempt/lease/project
  authority, and capacity-limited Tasks queue or reject without false running.
- Timeout, Adapter crash, stale heartbeat, late result, duplicate dispatch and
  cancel/terminal races settle once with bounded ownership.
- No owner/lease/outbox claim renews forever without useful progress or a
  bounded recovery state.
- Every terminal Task maps to one legal immutable outcome with source
  provenance, and unknown evidence never maps to success.

### 7.5 `P3-4` — D0, D1 and D2 durability/recovery

#### Do

Implement and expose durability by declared Executor capability:

| Level | Required implementation and proof |
|---|---|
| D0 | A started Task survives voice/Session disconnect while the application and Executor remain alive; restart reconciles persisted records with actual execution and reports `interrupted/unknown` when continuation cannot be proved |
| D1 | A versioned, integrity-checked checkpoint restores work that is side-effect-free or safely retryable, with exact Task/Attempt/checkpoint/context binding and no duplicate work |
| D2 | External effects use stable operation identities and durable reconciliation so the final outcome is exactly-once-equivalent or explicitly enters bounded manual resolution |

#### How

- Record the selected durability level and capability version on Task/Attempt
  admission; presentation must not promise a stronger level.
- For D1, persist checkpoint producer, schema/version, integrity, Task/Attempt,
  source context versions, effect-safety classification and resume provenance.
- Freeze whether D1 resumes the same Attempt or creates a linked recovery
  Attempt before implementation. Either choice must preserve auditability and
  must not silently reset retry budgets or result ownership.
- For D2, use a durable effect ledger or equivalent Adapter-owned evidence with
  stable external operation keys, intended effect, observed effect, settlement
  and manual-resolution state.
- Treat process death between external effect and Store acknowledgement as an
  unknown/reconciliation case, never an automatic retry without effect
  evidence.
- Ensure restart reconciliation is idempotent across repeated starts and two
  coordinating processes.

#### Done when

- Every declared level has real Adapter and fault/restart evidence; undeclared
  levels return `unsupported` with zero assumed recovery.
- D0 disconnect and restart semantics match the documented boundary exactly.
- D1 resumes from the exact checkpoint without duplicated Agent/Tool/file or
  external effects and produces a traceable terminal result.
- D2 either proves the intended external outcome once or exposes an explicit
  unresolved/manual state; it never silently reports completed.
- Retry, restart and reconciliation cannot allocate an unauthorized replacement
  Task or lose the predecessor Attempt/effect provenance.

Before this package starts, a design checkpoint must settle which real
Executor adapters claim D1 or D2 and whether feature-complete requires one real
adapter at each level. The plan does not manufacture those capabilities from a
D0 carrier.

### 7.6 `P3-5` — TaskResult, event replay, unread and terminal notification

#### Do

- Persist one legal immutable `TaskResult` for each completed Task, bound to
  the exact Task, producing Attempt, outcome, bounded summary and authorized
  artifact references; other terminal outcomes must not fabricate a result.
- Expose durable Task events/result query with a bounded cursor and an unread or
  consumption model that survives reconnect and restart.
- Preserve the terminal TaskEvent as notification identity while keeping voice/
  text presentation ACK separate from canonical Task truth.
- Deliver blocking questions, decision requirements, progress and terminal
  results to the correct active interaction when one exists; retain unread
  facts when none exists.
- Prevent dialogue context capacity or unbounded project reread from rejecting,
  fabricating or replacing a legal TaskResult.

#### How

- Validate and persist application/result before terminal publication; release
  lease/outbox ownership only after the canonical settlement transaction or a
  truthful recoverable state.
- Store bounded result data and references, not credentials or uncontrolled
  artifact content as instructions. Artifact reads revalidate permission,
  version and scope.
- Define cursor monotonicity, replay bounds, ACK idempotency and unread
  semantics. Task event replay is at-least-once unless stronger evidence exists;
  playout followed by crash before ACK may replay.
- Allocate a new current response generation for voice notification. Never
  reuse the task-create generation or let TaskEvent call TTS directly.
- Map completed/failed/cancelled/interrupted/unknown to distinct truthful
  presentation. Completed requires a legal TaskResult.

#### Done when

- A legal result cannot be lost because foreground dialogue consumed an
  unrelated context budget.
- Reconnect, refresh and restart recover the same result/event truth without
  duplicate Task mutation.
- ACK suppresses later applicable presentation replay; missing ACK retains the
  unread fact without claiming exactly-once speech.
- Wrong activation/generation/session/task/attempt events cannot present or
  consume another Task's result.
- Query and replay have zero Task/Executor/TTS mutation except the separately
  authorized presentation-consumption record.

### 7.7 `P3-6` — generalized Voice–Task Bridge and text/voice parity

#### Do

- Route committed natural-language intents for create, query/status, update,
  provide-input, pause, resume, reprioritize, cancel and explicit successor
  revision.
- Resolve among multiple visible Tasks using explicit identifiers, stable user-
  facing references and bounded clarification.
- Generalize beyond the controlled Chinese “把/将” grammar and exact itinerary
  while keeping deterministic safety policy after any NLU/model proposal.
- Provide the same target, authorization, confirmation, command and result
  semantics for text and voice origin.
- Return Task events to Conversation Runtime for voice arbitration and to the
  existing text/UI adapter for text origin.

#### How

- Accept only committed input. Partial/interim speech, low confidence,
  ambiguity, negation and ordinary dialogue have zero Task effects.
- Separate intent classification from authority. A model or grammar may propose
  operation/target/arguments; a closed policy validates supported operation,
  exact target, scope, permission, confirmation, bounds and capability.
- Require explicit confirmation for destructive or materially redirecting
  operations according to the accepted policy. The confirmation binds one
  command fingerprint and cannot authorize a later changed command.
- End an ambiguous resolution with clarification; the user's answer becomes a
  new committed intent rather than mutating from partial speech.
- Prefer stable task identity in structured UI. Natural-language recency or
  names may narrow candidates but must not guess when more than one remains.
- Maintain a multilingual/golden corpus owned by this capability and separate
  Demo itinerary phrases from general product evidence.

#### Done when

- The declared intent corpus meets the accepted precision/recall target across
  supported languages and paraphrases, not only exact fixtures.
- Multi-Task target ambiguity, wrong scope, partial speech, negation and failed
  confirmation produce zero Agent/Tool/Task/Executor/file/audio/history effects.
- Every supported natural-language operation produces the same canonical
  command result as its structured equivalent.
- Task status/result speech is sourced from canonical events/results, not
  conversation text or project-file inference.
- Foreground dialogue remains usable while background Tasks run and while
  clarification occurs.

### 7.8 `P3-7` — formal Integrated Web P3 experience

#### Do

- Present a scoped Task list/selector, stable Task identity, state/outcome,
  progress, blocking question, available controls, unread result and revision
  relationship.
- Expose only controls supported by current Task state, authorization and
  selected Executor capability.
- Keep accepted/queued/running/paused/blocked/decision-required/terminal labels
  aligned with the frozen canonical/projection contract.
- Recover selection and unread presentation after refresh/reconnect by treating
  browser storage only as a hint and revalidating backend authority.
- Keep foreground dialogue, voice interruption and Task notification separate
  but coherently arbitrated by Conversation Runtime.
- Make the formal route the supported default for the declared product profile;
  preserve feature-off compatibility until the retirement Gate passes.

#### How

- Fetch/revalidate the exact Task before enabling a control. Local React state,
  project files, transcript text or stale progress cannot authorize mutation.
- Display command acceptance separately from application and terminal outcome.
- Bind UI actions to exact task/attempt/command identity and show stable errors
  for conflict, unsupported, stale, authorization failure and unknown outcome.
- Route blocking answers through `provide_input` and revisions through explicit
  successor creation; do not mutate Task truth in the UI.
- Reuse Runtime/TTS response ownership, generation fencing and PresentationAck.
  A Task event never bypasses the arbiter to speak directly.
- Remove legacy hooks/flags only after formal composition, flag-off regression
  and migrated oracles prove replacement.

#### Done when

- A real user can create and distinguish at least two Tasks, continue dialogue,
  query and control either exact Task, reconnect, consume unread results and
  create an explicit revision without false truth.
- All supported controls work through the real Task Core and Executor path;
  fake/Demo/legacy carriers receive no product credit.
- Refresh/reconnect never creates a duplicate Task or exposes a foreign/stale
  Task.
- Voice notification, text presentation and controls remain correct under
  barge-in, stale generation, concurrent terminal event and missing ACK.
- Feature-off preserves the supported old text path until its accepted
  retirement.

### 7.9 `P3-8` — observability, configuration, privacy and retirement

#### Do

- Correlate subject/project/session/interaction/response with
  task/attempt/command/event/outbox/executor/checkpoint/effect and presentation
  identities without collapsing their scopes.
- Add bounded diagnostics for admission, queue, lease, outbox, checkpoint,
  recovery, reconciliation, result and presentation latency/failure.
- Replace Demo-default production flags and exact itinerary/task policy with an
  explicit profile and general configuration owned by the applicable module.
- Redact command input, blocking answers, TaskResult content, artifact details
  and credentials from ordinary logs while preserving useful identifiers and
  error classification.
- Retire legacy scheduler/Bridge/UI authority, obsolete entrypoints, duplicate
  validators and old runners only after formal replacement and oracle migration.

#### How

- Use one correlation/causation model across EventEnvelope and telemetry; record
  source authority and state transition rather than free-text guesses.
- Bound metric labels and do not place raw prompt/result/audio or secrets in
  traces.
- Keep Provider/Executor-specific configuration behind adapters and declare
  capabilities from validated configuration, not environment-variable
  presence alone.
- Follow the existing code/document retirement audits. Consolidate duplicate
  code only when owner, failure, idempotency and zero-side-effect semantics are
  proven identical.
- Move applicable old test support under explicit capability-owned tests or
  `tests/support` before deleting the historical runner.

#### Done when

- A failed journey can identify the exact Task/Attempt/Command/activation/
  generation/ACK/Executor seam without exposing private content.
- No production capability depends on `.env.production` being implicitly
  enabled or on the controlled Demo itinerary/bypass.
- Formal composition is the only product authority; remaining compatibility
  paths are explicitly bounded and flag-off tested.
- Every removed entrypoint/runner has replacement-oracle evidence and current
  Markdown links remain valid.
- Configuration errors fail closed and never silently downgrade durability or
  authorization claims.

### 7.10 `P3-9` — cumulative verification and complete-P3 acceptance

#### Do

- Close every package with capability-owned focused tests and affected
  regressions, then verify all P3 seams cumulatively on one exact clean source.
- Apply the complete applicable D-032 matrix from [TESTING](../../TESTING.md)
  to Tier 3 Task authority, mutation, durability and product-candidate paths.
- Run cold complete-diff and independent module-boundary reviews at coherent
  closures, then one cumulative integration-seam review.
- Exercise real Web, voice, Agent/Tool, Store and Executor boundaries; fake and
  deterministic tests remain supporting evidence only.
- Record exact commands, source and environment labels without credentials or
  private Task/audio/result content.

#### Required product journeys

1. **Multi-Task control:** create Tasks A and B, continue foreground dialogue,
   query each, update A and cancel B without cross-effects.
2. **Blocking/input:** observe one real blocked or decision-required event,
   provide exact bounded input and prove ordered application before terminal.
3. **Capability controls:** pause/resume/reprioritize only on a supporting
   Executor/scheduler composition; prove stable unsupported behaviour on a
   non-supporting path.
4. **Result/replay:** disconnect or refresh, recover Task identities, consume an
   unread terminal result and prove ACK/replay semantics.
5. **Restart/durability:** prove D0 restart truth and every declared D1/D2 path
   under process failure at the dangerous persistence/effect boundaries.
6. **Races/isolation:** cover duplicate/conflicting commands, cancel/terminal,
   update/terminal, pause/complete, stale owner, wrong Task/project/session,
   reordered event and result/notification generation races.
7. **Compatibility:** feature-off and supported text APIs retain contracted
   behaviour until explicit retirement.

#### Done when

- Positive journeys succeed and exact authoritative Task/Attempt/Result truth is
  user-visible.
- Every invalid, ambiguous, stale, wrong-scope and unsupported path fails closed
  with explicitly asserted zero forbidden effects.
- Restart, retry, reconciliation and unknown outcomes never duplicate work or
  masquerade as success/running/terminal.
- All claimed Executor levels and Web/voice controls have real-path evidence.
- The cumulative source passes applicable backend/frontend/build/static checks,
  independent Tier 3 review and the complete human P3 journey.
- STATUS can mark the three P3 module boundaries complete on that exact source
  without relying on Demo, legacy, fake or historical acceptance credit.

## 8. Cross-module seam checklist

| Seam | Required invariant | Closure owner |
|---|---|---|
| committed input → Task command | Only committed and authorized intent can reach Task Core; partial/ambiguous input has zero effects | Voice–Task Bridge plus Task Core |
| Task acceptance → Executor admission | Accepted/queued is not running; running requires authoritative Attempt evidence | Task Core plus Executor |
| Executor completion → Task terminal | Validation, application, legal result, terminal event and lease/outbox settlement form one recoverable truth chain | Executor plus Task Core/Store |
| TaskEvent → WorkProgress | Projection preserves source ID/sequence/outcome and never invents progress | Task Core/Bridge projection owner |
| Task result → dialogue context | Result is reserved/bounded canonical input; conversation/project files cannot replace it | Task Core plus Agent Bridge/context selector |
| TaskEvent → voice/text presentation | Runtime owns voice response/generation/TTS; text adapter owns text presentation; ACK is separate from Task truth | Conversation Runtime plus Web |
| barge-in/disconnect → Task lifecycle | Stop/cancel at response or round scope never widens to Task cancellation | Runtime, Agent Bridge and Task Core |
| reconnect/restart → replay | Stored event/result truth replays by bounded cursor; local hints are revalidated | Store plus Web/Runtime |
| capability → UI/Bridge command | Unsupported operations are unavailable or return stable unsupported with zero implied success | Executor, Task Core, Bridge and Web |
| context/artifact → execution | Version, scope, permission, expiry and redaction remain exact; content stays untrusted | Context/permission owner plus Executor |

Any package that changes one of these seams is Tier 3 even if most edited code
looks like UI, mapping or plumbing.

## 9. Test and evidence ownership

This document does not duplicate the D-032 matrix. Each Tier 3 package must
record the applicability and evidence for every dimension defined in
[TESTING](../../TESTING.md), scope out only genuinely inapplicable dimensions
and assert every forbidden side effect as zero.

Minimum P3-owned oracle families are:

- canonical reducer/state transition and terminal immutability;
- command idempotency, conflict and replay;
- multi-Task identity, target selection and cross-scope isolation;
- outbox/lease/owner fencing and bounded timeout/orphan recovery;
- Store transaction failure at every boundary around external effects;
- Executor capability negotiation and truthful unsupported/fallback;
- cancel/update/pause/resume/terminal races;
- D0 restart reconciliation and every declared D1/D2 fault point;
- result legality, context capacity, replay/unread and ACK;
- committed/partial/ambiguous/negated voice and text intent;
- flag-off compatibility and formal-route composition;
- real Web/Agent/Tool/Executor product journeys.

Historical W2 or stage-named tests are inventoried before removal. An applicable
oracle moves to the current capability owner, is shown to detect the intended
defect/forbidden effect, passes on current behaviour and participates in current
test discovery before the historical entrypoint is deleted.

## 10. Parallel ownership and integration strategy

Parallel lanes are ownership boundaries, not a fixed worker count:

- **Core/Store lane:** canonical model, migration, commands, outbox, events,
  result and replay storage;
- **Executor/Durability lane:** capability, admission, Attempt execution,
  checkpoint, recovery and reconciliation;
- **Bridge/Product lane:** natural-language routing, target clarification,
  formal Web controls and Runtime presentation;
- **Shared semantic lane:** identity/state/cancel/result/capability schema,
  composition, compatibility and cumulative verification, owned only by the
  Integration Owner.

Before parallel implementation, the Integration Owner freezes the shared
contract and allocates non-overlapping files or worktrees. Workers may not
resolve cross-module semantic conflicts locally. Each return contains:

- exact baseline and owned scope;
- changed contract/behaviour and explicit exclusions;
- tests run with results and unrun requirements;
- risk-matrix coverage and zero-side-effect evidence;
- migration/compatibility consequences;
- unresolved questions and recommended Integration Owner decision.

Integration occurs in dependency order, followed by focused seam tests. A
coherent module or related-package closure receives the review cadence required
by TESTING; small checkpoints do not manufacture review or completion credit.

## 11. Required packet template

Before any package is implemented, its active packet in STATUS or linked
evidence must state:

1. capability/module and named owner;
2. exact D-085 findings and current code baseline it addresses;
3. D-046 risk tier and shared seams touched;
4. dependencies and activation Gate;
5. included behaviour;
6. explicit exclusions and unsupported capabilities;
7. state/authority/cancel/result/recovery contract;
8. migration and flag-off compatibility;
9. applicable D-032 scenarios and zero-forbidden-effect assertions;
10. focused, affected, real-path and human acceptance;
11. review boundary and evidence destination;
12. retirement Gate for any temporary flag, hardcode, duplicate or legacy
    entrypoint.

The packet describes a coherent product result, not a list of files or
functions. Exact files and commands are discovered from the current checkout
when the packet starts.

## 12. Design checkpoints still requiring settlement

The accepted design fixes the product boundary but does not fully choose every
implementation semantic below. D-085 evidence and the first affected package
must settle them before code diverges:

| Question | Recommended default for review | Blocks |
|---|---|---|
| Is `queued` canonical or a projection? | Keep Task accepted and Attempt non-running as source truth; expose queued only through one frozen projection unless a state-machine decision adds it | `P3-1`, `P3-3`, `P3-7` |
| How is `paused` represented? | Add it only with a proven Executor pause boundary; otherwise return unsupported and do not relabel blocked/accepted | `P3-1` through `P3-4` |
| Does D1 resume the same Attempt? | Preserve `task_id`; choose same or linked recovery `attempt_id` explicitly with checkpoint/retry accounting and provenance | `P3-4` |
| Which adapters must prove D1/D2? | Every declared capability needs a real path; do not claim a level from interface support alone | `P3-3`, `P3-4`, `P3-9` |
| What does reprioritize control? | Bind to a real scheduler/admission policy; if none exists, return unsupported | `P3-2`, `P3-3` |
| How are decision-required answers represented? | Use a bounded, exact `provide_input` contract unless a separately accepted command is required | `P3-2`, `P3-6` |
| What is unread/replay retention? | Define bounded cursor/retention and ACK semantics for the supported product profile without importing Production retention/SLO scope | `P3-5`, `P3-7` |
| How is a terminal revision created? | Explicit new Task with predecessor link, new command identity and no mutation of predecessor/result | `P3-1`, `P3-2`, `P3-7` |

These recommendations are not new accepted decisions. A material change to the
accepted authority, durability or product semantics is recorded through the
decision process before implementation.

## 13. Complete-P3 definition of done

Complete P3 can be reported only when all of the following hold on one exact
source:

1. Multiple Tasks are independently addressable and survive conversation/
   connection lifecycle as contracted.
2. Full supported control operations and explicit successor revision work with
   exact target, idempotency, authorization and truthful state transitions.
3. Task Core/Store is the only canonical Task authority; UI, conversation,
   project files, legacy scheduler and Demo state cannot fabricate truth.
4. Executor selection and every claimed D0/D1/D2 behaviour are capability-
   driven, bounded and proven on real fault/recovery paths.
5. Result, progress, blocking questions, decisions, replay/unread and terminal
   notification are durable, correctly correlated and user-observable.
6. Voice and structured/text operations have equivalent authority and result
   semantics; partial, ambiguity, negation and wrong target have zero effects.
7. Foreground conversation remains responsive and barge-in/disconnect never
   implicitly cancels a Task.
8. Formal Integrated Web composition is the supported product path for the
   declared profile; feature-off compatibility is proven until retirement.
9. Demo-only hardcodes and legacy authority are retired according to their
   gates; protocol/safety constants remain.
10. Capability-owned automated evidence, real-path evidence, cold review,
    independent Tier 3 review and cumulative human P3 acceptance pass.
11. All evidence is bound to the exact clean source; unavailable or unrun tests
    are not reported as PASS.
12. STATUS is updated once from that evidence without changing the historical
    exact-source Integrated Web Alpha result.

Only then may the three P3 module rows be considered for `COMPLETE`. D-084
feature-complete still additionally requires formal P1/P2, the complete
Integrated Web carrier, generalization, cleanup, competitor-gap review and
independent cross-module closure.

## 14. Explicit exclusions

This P3 plan does not include:

- Production authentication/multi-tenancy hardening, public deployment,
  SLO/retention operations or release/rollback;
- optional Native model-level duplex;
- unrelated P1 device/Speech quality work or P2 media/interaction quality,
  except their exact P3 seams;
- unconditional D1/D2 claims for an Executor that does not declare and prove
  them;
- a new Agent/Harness Task authority, a second Task Store or a second terminal
  notification protocol;
- automatic successor creation from an ambiguous or terminal update;
- resurrection of signed W2 Gate, fixed manifests, Replacement Ledger or
  retired rehearsal tooling;
- `develop` integration, remote-ref updates, credential movement, provider
  billing/account changes or public deployment;
- broad duplicate abstraction or legacy deletion before contract/oracle
  replacement.

If an affected-row re-audit or implementation evidence proves that current code
requires a material product/architecture choice outside the accepted boundary,
unaffected planning continues, the exact decision is isolated, and no
implementation silently chooses the product semantic.
