# P3-8B formal observability and retirement implementation review — 2026-08-21

> Status: **PASS — SCOPED P3-8B GATE.** This verdict is limited to validated
> configuration/correlation, the formal Registry diagnostic consumer, a bounded
> in-process backend, the exact production projections listed below and three
> replacement-gated retirement items. The overall observability/configuration
> capability remains **PARTIAL**.

## Source and scope

- P3-8B B1 integrated source:
  `bd3fd0883e93dd73a55927296d4fe75ac0956132`.
- B2 activation/retirement baseline:
  `cc42098163bf6e9d7cec303f37551d3526997eb4`.
- Retirement commits integrated before B2:
  `4e207faa`, `ddde7b87`, `7b283898`, with manifest closure in `be2bd45f`.
- B2 worker commits reviewed together:
  `cde6633970f36458d87e97931da4598623348175` and
  `30442fd1efbd8566abaec4d3146c10caa284b9cb`.
- Integrated B2 source:
  `c0de16b5eba7004381f314ee97cbc98b35fe4e87`.
- Risk: Tier 3 for configuration capability truth, cross-scope telemetry
  isolation, privacy, lifecycle/backpressure and authoritative producer seams.

The implementation adds `product_observability_runtime.py` and composes it
through the existing AgentServer/Registry/P3 authenticated owners. It changes
no common wire, Task/Core/Store/Executor/Runtime/PresentationAck authority,
schema or authentication policy.

## Accepted behavior

### Configuration, identity and lifecycle

Mutation/Executor diagnostics become ready only when the current production
composition owns an exact prepared `_DirectP3RuntimeOwner`, that owner and Core
hold the same `DirectProjectCodeExecutorAdapter`, and a trusted confirmation
verifier is callable. Query-only, expired, missing, forged and unprepared
declarations fail closed.

Raw scope and high-cardinality identities remain process-local. The backend
receives only HMAC `lvpub:*` tokens whose receipts are checked by an independent
trusted verifier. Metric attributes are a closed low-cardinality dimension set;
trace tokens never become metric labels. Cross-scope correlation conflicts
poison the binding. Authority, diagnostic and delivery maps never evict an old
exact binding to accept a foreign reuse; capacity exhaustion fails closed.

The accepted `ProductObservabilityAdapter`/exporter remains the single bounded
FIFO and worker. The new runtime adds no second queue or worker. Its selected
backend is a bounded in-process callback owner, not an external collector.
Reaching exact capacity makes health non-ready; a rejected subsequent emit
enters failed state. Diagnostic failure, saturation or close never rewrites a
business response, and formal rejection never silently falls back to the legacy
collector or double-delivers.

### Authoritative production projections

After an exact unique OPEN subject/project/session/correlation route succeeds,
the Registry projects only after the corresponding authority or Store operation
succeeds:

| Business seam | Content-free diagnostic fact |
|---|---|
| Confirmed mutation | exact Command plus initial outbox identity |
| `task.status` | exact Executor/Attempt status projection |
| Store Task events | Event and closed `TASK_FAILURE` fact |
| Available `task.result` | Result identity/availability without result text or artifacts |
| Terminal progress reservation | Generation and exact delivery identity |
| Successful text/voice/P2 presentation consumption | ACK identity |

The same-instance Tier-3 test uses one Registry, runtime, backend and SQLite
Store for confirmed create, Store failed events, status/events/result,
generation and presentation ACK, and checks public Task/Attempt/Command token
continuity. Its Executor failure is a synthetic `ExecutorObservation` inserted
through the real Store interface; it is not a real Direct/Core dispatch and is
not credited as physical Executor execution.

### Retirement

Exactly three manifest items passed replacement, oracle, flag-on/flag-off,
rollback and affected-test review:

1. stale `scripts/live_voice_snapshot.ps1`;
2. W2-only dotenv compatibility tuples/branches/exports and their two isolated
   tests;
3. ticket-in-path dedicated-media compatibility symbols and frontend/backend
   branches.

Fixed media registration/handler/predicate/WebChannel, ordinary dotenv, the
formal P3 carrier, Direct Adapter, generic `schedule.*`, Task/Core/Store,
launchers, S7/S8, Wave evidence tooling and all other manifest rows remain.
The manifest test freezes an exact three-row retired set; the other 18 rows must
remain `inventory` with deletion unauthorized.

## D-032 review disposition

- Positive: validated ready lifecycle and the same-instance failed Registry /
  SQLite journey reach the accepted backend.
- Negative/isolation: forged/unprepared/expired configuration, raw or private
  payload, absent/ambiguous/closing routes, foreign scope and conflicting
  identity fail closed before backend effects.
- Boundary/state/concurrency/recovery: exact map/backend capacity, start/open/
  non-ready/failed/close, exporter saturation, replay/ACK idempotence and
  reconnect route freshness are covered.
- Failure/compatibility: backend/verifier/diagnostic exceptions preserve the
  exact business result; B1/P3-8A, AgentServer, P3-7, media, feature-off and
  build regressions retain their prior meaning.
- Real seam: Registry and Store producers feed the accepted adapter FIFO,
  runtime, codec and backend. The synthetic Executor input limitation remains
  explicit.

The first foundation review found three Important issues and one Minor issue:
configuration overclaim, LRU scope forgetting, self-certified producer evidence
and ready health after permanent saturation. The second B2 commit closed all
four. Final independent review of `cc420981..30442fd1` returned
**0 Critical / 0 Important / 0 Minor**.

## Verification summary

| Gate | Result |
|---|---|
| B1 plus accepted P3-8A combined regression | `267 passed` |
| Runtime, authenticated composition and AgentServer | `204 passed`, one existing Authlib deprecation warning |
| Independent combined focused review | `29 passed`; `C0 / I0 / M0` |
| Full Registry | `165 passed, 6 failed`; the same six nodeids/function digests fail on `cc420981` before the new projection |
| Dedicated-media frontend | `27/27` |
| Build profiles | `2/2` |
| Full Formal Integrated Web | `439/440`; sole failure is the reproduced baseline P1/TTS Exit/re-enable late ACK |
| Production Live Voice build | PASS, 4,644 modules |
| Ruff, Python compile and diff checks | PASS; `agent_ws_server.py` retains identical baseline whole-file format debt |

Exact commands and nonclaims are bound in the
[evidence record](../evidence/P3_8B_FORMAL_OBSERVABILITY_RETIREMENT_EVIDENCE_20260821.md).

## Nonclaims and remaining work

- No external OTLP/OTel SDK, collector, persistent exporter, SLO, retention or
  production operations owner exists in this package.
- Checkpoint/effect have codec/token-map expressibility only, with no formal
  producer. Recovery/reconcile/current outbox state, claim/lease and independent
  reconciliation truth are not projected.
- Initial outbox identity is not current outbox state.
- The test-injected Store `ExecutorObservation` is not actual Direct dispatch.
- P3-9, a physical complete-P3 journey, P1/P2 latency/Exit/generation-time
  interruption, feature complete, controlled-product readiness and Production
  remain open. No remote ref was updated.
