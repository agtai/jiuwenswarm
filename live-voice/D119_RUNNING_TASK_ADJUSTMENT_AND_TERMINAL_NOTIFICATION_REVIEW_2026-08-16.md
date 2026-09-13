# D119 — Running Task adjustment and terminal notification review

Date: 2026-08-16

> **Candidate-specific frozen review.** The S7/A2 automation and review PASS in
> this record remains valid only for exact source `3bc7f9345f5b3832367e0a34b0dee8853d3d2c02`.
> Later product source, including `f118f51b`, is not covered by that PASS. Read
> [STATUS](STATUS.md) for the current candidate, blockers and next action. Under
> D-081, this record's historical S7/A2 and S8/A3 wording does not reopen the
> already accepted Integrated Web Alpha milestone.

Stage / target nodes: renewed S7/A2 candidate verification, then one S8/A3
product acceptance on the exact tested source

Tracks / modules: Shared-X, P1, P2, P3alpha; unified semantic owner, Task
Core/Store, Direct Executor, progress/presentation owner and Integrated Web UI

Risk tier: Tier 3 — shared protocol, authority, durability, mutation and
concurrency

Status: **DESIGN + IMPLEMENTATION + S7/A2 AUTOMATION/REVIEW PASSED / S8/A3
PHYSICAL ACCEPTANCE PENDING**

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

The implementation and verification results are recorded below. D-071/D-072
retired signed Gate, fixed manifest, Replacement Ledger and Gate-only tools are
not restored.

## Exact candidate and verification

The exact tested implementation source is
`3bc7f9345f5b3832367e0a34b0dee8853d3d2c02` on
`hx/0812_live_voice_w3`. It consists of four coherent local commits after
upstream `e014d1bffb204300064ac77eebaee89e1d64d7fc`; no remote ref was updated.
A later documentation-only status commit does not change the tested product
source.

- Serial cumulative backend matrix: `1,776 passed, 2 skipped, 1 warning` in
  383.74 seconds. The skips are the existing Windows symlink cases and the
  warning is the existing Authlib deprecation.
- Integrated Web: `374 / 374` passed, including Session switch while old TTS is
  unresolved and successor capture after the stale playout settles.
- Post-format affected backend set: `324 passed, 2 skipped, 1 warning`.
- Production frontend build: passed with `4,642` modules. Existing chunk-size,
  dynamic-import and duplicate i18n `empty` notices are non-blocking.
- Ruff check/format check, Python compilation and `git diff --check`: passed.

One cumulative backend run performed concurrently with the frontend exposed a
single `ROLLBACK_FAILED` result in an existing P2 adapter test. All four exact
parameters and the complete 46-test owner file immediately passed serially;
the final serial cumulative run above also passed. No source change was made to
hide or relabel that load-sensitive observation.

## Coherent-batch review result

Main completed the full-diff self/cold review. A fresh read-only Tier-3 review,
also serving as scoped Sol post-review, found three material issues before
closure:

1. the isolated product fixture lacked a deterministic real checkpoint for an
   update submitted after intervening dialogue;
2. late settlement of an old Session's TTS could reinstall a stale ACK owner
   and block successor capture; and
3. a malformed custom Executor rejection reason could poison or repeatedly
   lease the durable adjustment outbox path.

The exact candidate closes all three: the Demo-only checkpoint is event-driven
and doubly flag-gated, deferred ACK retention is fenced to the exact current
activation/Session/generation, and malformed returned or raised Executor
reasons are canonically rejected before durable publication. Focused negative,
flag-off, cancellation/close, zero-mutation and mounted rollover tests cover
the repairs. The independent reviewer reported no remaining P0-P3 source
finding.

## S8/A3 product acceptance

> **Frozen candidate wording.** This section records what remained for the D119
> candidate on 2026-08-16. D-081 keeps the already accepted Alpha closed; the
> seven-step journey is now reused as Post-Alpha Demo validation, not as another
> S8/A3 run. Current blockers and results belong only in [STATUS](STATUS.md).

Physical acceptance is still **PENDING**. The host has a protected Speech key
binding, but the private product/provider runtime is not currently listening
and provider/model readiness has not been established. No automated or mounted
test is substituted for the real microphone/TTS Journey.

The single required run is the seven-step D119 itinerary Journey in
[E2E_RUNBOOK.md](runbooks/E2E_RUNBOOK.md): dialogue, background create,
intervening dialogue, update while the Task is truly non-terminal, adjustment
status, authoritative applied-before-terminal/current-generation announcement,
and result-backed artifact query. It must also verify ACK refresh suppression,
ASR/TTS mutual exclusion, artifact contents/SHA and bounded fixture cleanup.

## Exclusions

Performance optimization, concurrent background Tasks, running drafts, speaker
echo cancellation, automatic successor revisions, public deployment, remote
ref updates and credential relocation are outside this batch.
