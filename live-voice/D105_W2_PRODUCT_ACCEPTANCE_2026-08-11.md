# D105 W2 product acceptance

> Date: 2026-08-11
> Status: `PASS — W2 PRODUCT-ACCEPTED`
> Tested source: `23686c5f87af4698ff350db19b28740a54d39713`
> Authority: [D-071](decisions/DECISIONS.md) and the [W2 acceptance contract](validation/INTEGRATED_DEMO_ACCEPTANCE.md)

## Decision

The cumulative P1/P2/P3alpha Integrated Demo satisfies the W2 product
acceptance contract. Applicable automated verification passed, the user
completed the required physical-input and audible product journey, the same
task completed the bounded A→B→C lifecycle, and final cleanup found no
unsettled product effect. This is a W2 product decision only; it is not an
Integrated Web Alpha, Production, audit-grade evidence, browser-matrix or full
P3 claim.

The isolated runtime started from clean handoff source `031ce406d` and remained
on the same persistent Session, project, database, fixture and browser profile
while narrowly scoped product defects were repaired. The final P3 recovery
observation used a full F5 load of tested source `23686c5f8`. Earlier P1/P2
observations are reusable under the acceptance contract because subsequent
final changes were confined to P3 inspection, terminal reconciliation and
task-target recovery; each affected source batch received its own automated
rerun.

## Automated and review boundary

- Final Integrated Web verification passed `257/257`, including historical P3
  query bootstrap, backend status/full-history validation, terminal
  reconciliation, cross-correlation fail-closed behavior, persisted refresh
  recovery and zero recovery mutation.
- The frontend production build and `git diff --check` passed. The source
  worktree was clean after the final source commit.
- Every defect found during the journey received implementation self-review,
  a cold complete-diff review, affected tests and an affected human rerun. A
  literal independent `/review` did not run because no independent review tool
  was available and active instructions prohibited subagent delegation; this
  record does not claim otherwise. The complete human product rerun and the
  final cold review are the recorded substitute and limitation.
- Two pre-existing stale `COMMITTED_ORIGIN_REQUIRED` expectations in
  `tests/integration/live_voice/test_d90_formal_task_vertical.py` are not
  claimed as passing and were not part of the affected frontend closure.

## Human product result

The user operated one localhost product page in desktop Google Chrome 151 on
Windows with a working physical microphone/output path, a real
OpenAI-compatible batch Speech provider, the real JiuwenSwarm Agent/Tool route,
model label `deepseek-v4-flash`, persistent Session
`sess_w2_accept_20260811_195814`, registered project `proj_3a4a1f5d`, and a
disposable Git fixture. No credential or private Provider value is recorded.

- **P1:** speech was recognized, the user corrected/confirmed the committed
  text, heard the complete real Agent response, observed automatic successor
  capture and stopped it. Empty successor capture returned
  `SPEECH_PROVIDER_EMPTY_TRANSCRIPT` without a second Agent/Tool submission.
- **P2:** the real read-only Terminal Tool returned `main`; the user heard its
  response. Stop playback ended the old audio. The exact correction
  `分支用于隔离开发工作。` was acknowledged and heard completely. During P3 A,
  `P2与任务并行正常。` remained independently acknowledged and audible.
- **P3alpha:** the product used separate confirmation and execution actions.
  One task, `task-8b06cffe54554e598c9f296a62167f28`, produced exactly three
  attempts: A `attempt-4b8bcad7c2e7461391276ae8922a01fc` was cancelled, B
  `attempt-66d57cb78b5b4b88b83c86c90d5857ac` completed the expected fixture
  change, and C `attempt-83ffc1024fae45cd90a8ec3094325f6d` became
  `interrupted` across the controlled AgentServer restart. No attempt D or
  duplicate mutation appeared.
- **Recovery/degradation:** F5 recovered the same task after A and again after
  C. The final page showed `interrupted / ineligible` without issuing a new
  confirmation or mutation. A natural `MEDIA_DOWNLINK_LIMIT_EXCEEDED` event
  remained visibly truthful with usable text fallback; a later turn recovered
  normal complete playout.

## Authoritative settlement and cleanup

The final database contained one terminal/interrupted task, three terminal
attempts, command counts `task.create=1`, `task.cancel=1`, `task.retry=2`, task
events `0..18`, and four delivered outbox rows. All outbox claims, project
attempt owners and leases were empty. The disposable fixture was clean at
checkpoint `ea4860c525e8e2b935e062c0b468c3843bfd7b3c`, containing only the
expected accepted change.

Gateway, AgentServer and Vite stopped cooperatively; the isolated Chrome
profile was closed. Dedicated ports `5173`, `9223`, `18092`, `19000` and
`19001` had no listener, no runtime process remained, and both source and
fixture worktrees were clean. W2 therefore closes as **PRODUCT-ACCEPTED**. The
next milestone is Integrated Web Alpha, whose stricter contract requires its
own tested source and complete Alpha journey.
