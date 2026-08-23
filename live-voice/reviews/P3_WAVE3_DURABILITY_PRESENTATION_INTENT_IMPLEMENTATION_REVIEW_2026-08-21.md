# P3 Wave-3 durability, presentation and intent implementation review — 2026-08-21

> Status: **PASS — SCOPED WAVE-3 SOURCE, AUTOMATION, REVIEW AND BOUNDED
> PRIVATE EVIDENCE.** The integrated source through
> `17e929650203525dd3cb41d1878908ffd2c1978b` closes P3-4, P3-5B and P3-6
> within their accepted packets. This record does not grant complete P3,
> controlled-product readiness, feature-complete, Production, `develop`
> integration or remote-ref credit.

## 1. Authority, source and scope

- Branch: `hx/0812_live_voice_w3`.
- Activation baseline: `cfff0c43aa599c009ab9517397566fec5c1bdd95`.
- Reviewed integrated source:
  `17e929650203525dd3cb41d1878908ffd2c1978b`.
- Governing decisions: D-089 bounded Wave 3 and D-090 Task-wide consumer
  cursor re-scope.
- Child records:
  [P3-4 durability/recovery](P3_4_DURABILITY_RECOVERY_IMPLEMENTATION_REVIEW_2026-08-21.md)
  and
  [P3-5B presentation consumption](P3_5B_PRESENTATION_CONSUMPTION_IMPLEMENTATION_REVIEW_2026-08-21.md).
- Risk: Tier 3. The integrated package changes SQLite durability authority,
  Direct effect recovery, Runtime/Web presentation ownership, durable Task
  event consumption, natural/structured intent resolution, authenticated
  confirmation and Task mutation CAS.

The final P3-6 composition/fix sequence is `81fd8a41`, `36e6bc64`,
`dbffbab2`, `58a04f86` and `17e92965`. The independent final reviews of the
last authority fix both returned `0 Critical / 0 Important / 0 Minor`.

## 2. Accepted integrated facts

### P3-4 — durability and recovery

- Direct exposes closed cumulative D0/D1/D2 capability truth; D2 is an
  explicit same-Store-backed candidate and persisted selection cannot drift.
- Schema v6 is the sole checkpoint/effect/recovery/lease/fence authority. Its
  v1-v5 migrations and the exact released candidate-v6 normalization are
  atomic, reopen-safe and fail closed for non-exact schema shapes.
- Store, Runtime and OS-lock facts jointly fence linked recovery. Effect intent
  precedes apply; `APPLIED`, `NO_EFFECT` and `UNKNOWN` remain distinct, and an
  ambiguous effect becomes `manual_required` without a blind second call.

### P3-5B — presentation-gated consumption

- Text consumption requires exact connected-DOM adoption; voice consumption
  requires the Runtime-owned AUDIO presentation ACK. Audio failure creates a
  separately fenced text fallback and does not consume voice.
- Only fresh `task.ack_events` authority and the retained presentation owner
  advance the class-isolated durable watermark. New Session/process restart,
  Attempt rollover, non-presentable gaps, delayed ACK and large prefixes retain
  Task-wide unread truth without a second ledger.
- Presentation reservations, response replay and tombstones are bounded.
  ACK-versus-close, publish/playout/Core/cleanup failures consume once or fail
  closed with the applicable Agent/Task/Executor/history effects at zero.

### P3-6 — production multi-Task intent

- The product classifier consumes committed natural text/voice or strict
  structured input and binds trusted origin fields. The 68-case corpus and 14
  parity groups exercise classifier semantics without reading expected output.
- The authenticated Store reader projects exact Task state/outcome, Attempt,
  event head, result, lineage, capability and admission facts, then rereads the
  Store snapshot before a resolution can be used.
- Production composition supports five queries and six mutations through the
  real Registry/classifier/Bridge/Store/Core path. `provide_input`, `pause` and
  `resume` remain truthful unsupported/conflict paths where no real primitive
  exists.
- Clarification is bounded, single-use and restart-fenced. Confirmation uses
  the existing durable owner, exact context/model/task-set/capability binding,
  call-local consume receipt, fresh authorization and a final Store reread
  immediately before one Core invocation.
- Cancel and adjust carry an exact typed Task/Attempt/event-head precondition.
  Store checks it inside the write transaction. Repeated preconditioned cancel
  persists a sanitized `TASK_CANCEL_ALREADY_REQUESTED` conflict with exact
  replay; legacy raw repeat cancel retains its compatible positive no-op.

## 3. Final automation and review evidence

| Gate | Result and source relationship |
| --- | --- |
| Final P3 affected Python after the last authority fix | `477 passed` |
| Fresh broad Live Voice Python | `2721 passed, 5 skipped, 1 known failure` |
| Formal Integrated Web | `414 passed, 1 known failure` |
| Strict Live Voice and product-composition contracts | `45/45` and `14/14` |
| Formal Web production build | PASS; 4,643 modules transformed |
| Final S8 unit and CLI readiness | `67 passed` |
| Static checks | scoped Ruff, format, compile and `git diff --check` PASS |
| Final P3-6 independent reviews | two verdicts, both `C0 / I0 / M0` |

The packet's broad Gate ran once before the final narrow Task-precondition and
repeat-cancel authority fixes. Those backend-only fixes were then covered by
the `477 passed` affected set, final independent reviews and the post-fix S8
run; a second broad run was intentionally not substituted for that scoped
evidence. The Web/contracts/build surfaces were unchanged by the final fixes.

The sole broad Python failure is the existing retry projection test that expects
a completed predecessor although D-087 permits retry only from cancelled. The
sole Formal Web failure is the independently reproducible P1/P2 mounted
Exit/immediate-re-enable presentation-ACK timing case. Neither product policy
was weakened to turn those baselines green, and both remain outside the scoped
Wave-3 package.

## 4. Physical evidence and honest boundary

The final exact source ran once under a fresh ACL-private root with existing
machine-private configuration. The production factory/registration, real
Agent, real file Tool, Direct concurrency/admission/control, Store reopen and
cleanup checks all passed. The private artifact independently validated with
22 observations, 11 exact Tool call/result pairs, five write/edit pairs and
zero drops, observer failures, unknowns, sequence gaps or unpaired events. See
the sanitized [Wave-3 evidence](../evidence/P3_WAVE3_DURABILITY_PRESENTATION_INTENT_EVIDENCE_20260821.md).

That private run is a current-source Agent/Tool and production-factory
regression, not a physical browser/audio-device proof and not a single Registry
E2E covering all 11 supported plus three unsupported operations. P3-4 real
Store/Direct/OS seams, P3-5B connected React DOM and Runtime AUDIO authority,
and P3-6 real Registry-to-Core composition are instead closed by the exact
product-path automation above. No physical perception or complete-P3 claim is
made.

## 5. Verdict and exclusions

P3-4, P3-5B and P3-6 are locally integrated and review-clean on the identified
source, so the bounded D-089 Wave-3 package is scoped PASS. Remaining work
includes the deferred P1/P2 capture/Exit repair, P3-7 product UI, later P3
packages and cumulative product acceptance. Every remote update remains
unapproved and excluded.
