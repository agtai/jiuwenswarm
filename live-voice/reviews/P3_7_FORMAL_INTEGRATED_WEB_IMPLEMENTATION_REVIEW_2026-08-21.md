# P3-7 formal Integrated Web implementation review — 2026-08-21

> Status: **PASS — SCOPED P3-7 SOURCE, AUTOMATION AND TIER-3 REVIEW.** The
> integrated source `98e063f084c140cb6eb0042de32f3695c89c7279` closes the
> accepted P3-7 formal multi-Task Web experience. It does not grant complete
> P3, physical audio, controlled-product readiness, feature-complete,
> Production, `develop` integration or remote-ref credit.

## 1. Authority, source and scope

- Branch: `hx/0812_live_voice_w3`.
- Parallel-packet activation baseline:
  `29589734a0bb51a697bf7d594e3b1bb552ddcd34`.
- A-lane implementation baseline:
  `965fc827fb409b97d791f64febc7d32f0aaf71d3`.
- Reviewed worker commit:
  `4e3d4bf591c21c8ac843032e5fc5d919f09786b9`.
- Reviewed integrated source:
  `98e063f084c140cb6eb0042de32f3695c89c7279`.
- Risk: Tier 3. The package exposes authenticated multi-Task state and visible
  mutations, combines durable presentation ownership with React DOM adoption,
  and projects backend capability truth through the product Registry.

The implementation changes 13 files with 3,159 insertions and 14 deletions.
It adds one closed formal owner and its tests, composes it into the existing
visible product carrier, adds the narrow Registry projection and reuses the
accepted AgentServer, Registry, SQLite Core, confirmation and presentation
methods. It does not add a common request method, canonical Task state, Store
schema, authentication policy or new Executor primitive.

## 2. Accepted product facts

- The visible formal carrier lists and selects multiple authenticated Tasks.
  A selection hint is never authority: initial load, selection, refresh and
  reconnect reread list, status, complete bounded events and result before the
  formal route becomes ready.
- Task state/outcome, admission/queued truth, exact current Attempt progress,
  previous-Attempt history, immutable result and predecessor/successor lineage
  come from Task/Core projections. The UI does not invent another Task state,
  result, event ledger, unread watermark or retry policy.
- The product uses the existing five direct query methods and the accepted
  structured-intent/confirmation/mutation composition. It exposes
  `task.create`, `task.update`, `task.adjust`, `task.reprioritize`,
  `task.cancel`, `task.create_successor` and eligible `task.retry` only when
  current authenticated authority permits them. `provide_input`, `pause` and
  `resume` remain explicitly unavailable and allocate no transport.
- Command issuing, accepted/applied disposition and later terminal Task outcome
  are distinct. A successor never rewrites its predecessor or TaskResult.
- Text consumption still requires connected-DOM adoption and voice consumption
  still requires Runtime AUDIO `PresentationAck`. Task events never call TTS;
  foreground Stop/barge-in/response cancellation never implies Task cancel.
- Once the formal collection has validated a Session, a route is
  connection-local. Disconnect synchronously invalidates it, and reconnect or
  later refresh remains blocked until a fresh list/status/events/result chain
  succeeds. A rejected chain keeps progress activation and ACK at zero. Before
  the first successful formal collection read, the already accepted P3-5B
  durable progress owner remains independent.
- Ordinary production remains flag-off. Feature-off allocates no formal P3 Task
  owner transport and preserves the supported text path.

## 3. Frozen interface disposition for P3-8B

P3-8B composition must preserve these interfaces unless Main explicitly
re-scopes and re-tiers the affected owner:

1. Existing WebSocket methods and their closed parameters/results remain
   unchanged. The only new Web-only projection is
   `live_voice.task.list|status -> result.supported_operations: string[]`.
2. Status operations are the exact intersection of the existing authenticated
   `AuthenticatedTaskFact.supported_operations` and the current principal's
   authorized operations. `task.retry` is added only by the existing
   permission-aware `retry_admission`; pre-injected or mismatched projection
   fails closed.
3. Task/Attempt/Command/Event/Result, scope, revision, event-head, correlation
   and lineage truth remain owned by the existing Store/Core/authenticated
   reader. The browser may retain only a selection hint.
4. P3-5B `task.unread_events`/`task.ack_events`, connected-DOM text adoption and
   Runtime AUDIO ACK remain the sole durable presentation-consumption path.
5. Formal reconnect/refresh must finish the fresh four-read chain before a
   validated selection can reactivate progress. No command or Task is replayed
   merely because the connection returns.
6. Registry/AgentServer startup, shutdown, issuer, Runtime generation/response,
   feature-off zero-allocation and unsupported-operation semantics remain
   unchanged. P3-8B diagnostics may observe these seams but may not become
   their authority.

## 4. D-032 evidence and review closure

| Dimension | Closed evidence |
| --- | --- |
| Positive | Two Tasks, exact selection/detail/replay/result/lineage, supported query/control shapes, structured continuation through Registry and SQLite Core |
| Negative | Malformed/unknown/unsupported operations, forged projection, unauthorized principal, foreign scope/result/event/lineage and invalid target fail closed |
| Boundary/state | Bounded list/events pages, closed lifecycle/outcome enums, current-versus-prior Attempt, terminal immutability and eligible retry only |
| Timing/concurrency | Stale/late refresh fenced, selection race fenced, response-loss recovery content-free, reconnect waits through result, rejected result leaves activation/ACK at zero |
| Recovery/isolation | Browser hint reread, disconnect/reconnect without mutation replay, exact subject/project/session/Task/Attempt/correlation binding |
| Feature-off/compatibility | Zero formal transport when off; existing P3-5B owner, P1/P2 text/audio paths and unsupported operations remain unchanged |
| Real seam | AgentServer → Registry → authenticated reader/SQLite Core plus mounted React DOM/progress ACK composition |

The first independent review found six Important issues: a browser-local unread
ledger, unfiltered operation projection, missing automatic reread, stale UI
truth after failure, previous-Attempt progress leakage and insufficient real-
seam evidence. The repair removed or closed all six. The final review then found
one reconnect ordering issue in a stale effect closure; the route identity and
validated/pending Session fence plus delayed/rejected-result mounted evidence
closed it. Final independent verdict:
`0 Critical / 0 Important / 0 Minor`.

## 5. Verification and exclusions

| Gate | Result |
| --- | --- |
| Registry/authenticated composition plus AgentServer route | `184 passed`, one third-party deprecation warning |
| Formal P3 owner | `14/14` |
| Mounted affected Task/progress/reconnect/feature-off set | `10/10` |
| Full Formal Integrated Web | `439/440`; one reproduced baseline failure |
| Build profiles | `2/2` |
| Live Voice production build | PASS; 4,644 modules transformed |
| Strict TypeScript, Panel bundle and diff checks | PASS |
| Final independent Tier-3 review | PASS, `C0 / I0 / M0` |

The sole Formal Web failure is
`mounted Exit and immediate re-enable recover after old unified success or
rejection without replaying TTS`, a late P1/TTS presentation-ACK timeout also
reproduced on the clean A-lane baseline. Existing locale duplicate-key and
bundle-size warnings are likewise outside P3-7. No product policy was weakened
to make them green. See the sanitized
[P3-7 evidence](../evidence/P3_7_FORMAL_INTEGRATED_WEB_EVIDENCE_20260821.md).
