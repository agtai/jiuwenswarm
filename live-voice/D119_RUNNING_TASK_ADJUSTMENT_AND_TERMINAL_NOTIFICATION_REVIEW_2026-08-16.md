# D119 — Running Task adjustment and terminal notification review

Date: 2026-08-16

Stage / target nodes: renewed S7/A2 candidate verification, then one S8/A3
product acceptance on the exact tested source

Tracks / modules: Shared-X, P1, P2, P3alpha; unified semantic owner, Task
Core/Store, Direct Executor, progress/presentation owner and Integrated Web UI

Risk tier: Tier 3 — shared protocol, authority, durability, mutation and
concurrency

Status: **DESIGN CHECKPOINT PASSED / IMPLEMENTATION IN PROGRESS**

## Frozen minimal design

1. Store stays at schema v3. Its canonical command ledger, generic outbox
   payload, ordered TaskEvent stream and current background pointer already
   supply the required transaction, replay and ordering primitives. The batch
   adds `task.adjust`, an adjustment outbox kind and
   `task.adjust_requested/applied/rejected`; it does not add a Store table or
   schema migration unless implementation testing exposes a concrete gap.
2. Adjustment admission binds the exact authenticated subject/project/Session,
   current non-terminal Task, current attempt and committed-input identity.
   One command ID is the stable adjustment identity. The bounded instruction is
   untrusted content and is never authority, a system instruction or ordinary
   log material. Duplicate/replayed commands cannot create a second adjustment.
3. Direct Executor owns a real pre-terminal adjustment checkpoint. Ordered
   adjustment outbox deliveries are durably queued there; each is either
   applied to the isolated worktree through the real Executor path or rejected
   after the checkpoint closes. The Executor holds terminal/result publication
   until Core has persisted the matching applied/rejected event. Tests may
   inject an explicit checkpoint barrier; production code does not sleep to
   simulate a running Task.
4. Terminal Tasks and immutable TaskResults reject adjustment with zero file,
   Executor and Task lifecycle side effects. The product tells the user to
   explicitly create a revision; this batch never auto-creates a successor.
5. The terminal TaskEvent remains the durable notification identity. Existing
   subscription/progress/arbiter/P2 presentation and ACK owners are reused.
   The product notification owner selects the current valid P2 activation and
   allocates a new response generation; the task-create response generation is
   never reused. With no activation, the unconsumed TaskEvent remains the
   recovery fact for the next valid activation. No completion-notification
   table or second notification protocol is introduced.
6. A completed announcement additionally requires a legal immutable
   TaskResult. Failed, cancelled and interrupted outcomes use distinct truthful
   text. Presentation ACK suppresses later replay; playout followed by a crash
   before ACK keeps the existing P2 replay behavior and is not unconditional
   exactly-once.
7. Semantic routing is the closed six-route set `dialogue`,
   `background.create`, `background.update`, `background.query`,
   `background.status`, `background.cancel`. Create and update use separate
   high-confidence full-utterance grammars. Questions about current result,
   progress or adjustment status remain query/status; ordinary non-task
   questions, ambiguity, negation and low confidence have zero Task effects.
8. Speech first fixes shared bounded cleanup ownership. A simple retry-listening
   action is required; one bounded automatic recovery is added only if focused
   stress tests still prove a safe transient failure after the root fix.

## Applicable D-032 matrix

- Positive: dialogue → create → intervening dialogue → non-terminal update →
  adjustment status → applied before terminal/result → current-generation
  terminal announcement → real result query.
- Authority/flag negative: feature off, unauthenticated, wrong subject/project/
  Session, stale activation and wrong current Task all fail closed with zero
  Agent/Tool/Task/file/presentation mutation.
- Semantic negative: partial/interim, ordinary questions, ambiguous create,
  cancel/update negation and low confidence have zero Task side effects.
- Durability/idempotency: same command/final replay, conflicting identity,
  restart recovery, two SQLite connections, multiple ordered adjustments and
  ACK/replay are covered.
- Lifecycle/concurrency: update while truly non-terminal, checkpoint closure,
  terminal immutability, applied event before terminal/result, old response
  generation rejection, active ASR/TTS serialization, one capture and Speech/
  barge-in zero Task mutation are covered.
- Privacy: adjustment/result content and credentials do not enter ordinary
  logs; artifacts remain bounded untrusted reference data.

## Execution and review cadence

After this checkpoint, two non-overlapping workers may implement Speech and
Task Store/Core/Executor in independent worktrees. Main remains the only shared
protocol/composition/UI owner and Integration Owner. Each lane runs focused
checks. The integrated coherent batch receives one self-review, one full-diff
cold review and one new independent read-only review; that independent review
also satisfies scoped Sol post-review. A material shared-semantic fix repeats
only the affected final cold-review scope.

Verification results, exact tested source, review findings and the single real
product Journey will be appended only after they actually run. D-071/D-072
retired signed Gate, fixed manifest, Replacement Ledger and Gate-only tools are
not restored.

## Exclusions

Performance optimization, concurrent background Tasks, running drafts, speaker
echo cancellation, automatic successor revisions, public deployment, remote
ref updates and credential relocation are outside this batch.
