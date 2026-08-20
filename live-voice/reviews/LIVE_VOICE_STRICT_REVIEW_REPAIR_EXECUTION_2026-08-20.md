# Live Voice strict-review repair execution — 2026-08-20

> Status: **ACTIVE — 4/88 unique defects closed.** This is a user-routed,
> bounded D-060/D-062 parallel repair packet on the isolated strict-review
> branch. It grants no product-readiness, capability-completion or physical
> acceptance credit.

## 1. Authority, baseline and counting

- Integration worktree:
  `D:\XGG AI\openjiuwen\jiuwenswarm-review-20260819`.
- Activation baseline: `4661ed6d7db11048dad9d070cb9120fe35b049c4`.
- Canonical finding evidence:
  [strict-review revalidation](LIVE_VOICE_STRICT_REVIEW_REVALIDATION_2026-08-19.md).
- Queue size: 88 unique current defects. The audit has 89 active IDs because
  C3 aliases B42; B17 is an inactive duplicate alias of B13.
- Progress advances only when a unique defect meets the closure rule below.
  A code change, passing focused test or worker commit alone does not increment
  the numerator.
- Main is the only Integration Owner and integration-branch history writer.
  Each implementation worker owns one non-overlapping branch/worktree and may
  commit only its assigned files. Workers never push or integrate themselves.

## 2. Required repair and closure sequence

Every finding follows this exact sequence:

1. reproduce the current defect deterministically on the activation baseline;
2. freeze intended behavior, owned source/tests, exclusions and risk tier;
3. add a regression that fails for the original mechanism;
4. implement the minimum root-cause repair;
5. run applicable D-032 positive, negative, boundary, state, time/order,
   concurrency, retry/recovery, identity/isolation, failure/fallback,
   compatibility and real-seam evidence;
6. assert zero forbidden Agent, Tool, Task, audio/history, store and other-scope
   effects on every rejection/failure path;
7. independently review the complete module diff and repair findings;
8. integrate on the exact reviewed commit, rerun affected integration checks
   and only then mark the unique finding `FIXED`.

Deterministic barriers/events are required for races; timing-only sleeps do not
prove closure. Capacity repairs must separate releasable heavy state from the
anti-replay fence; unqualified LRU eviction is excluded. Cleanup timeout may
remain truthfully pending/retained but must never be reported as successful
close.

## 3. Active Wave 1 ownership

### SRR-01 — C5 Task Store observation binding

- Capability/owner: Task Control Core/Store.
- Risk: Tier 3 authority and durability.
- Worker-owned source/tests:
  `jiuwenswarm/server/live_voice/task_store.py` and
  `tests/unit_tests/live_voice/test_persistent_task_core.py` only.
- Intended behavior: before any mutation, every Executor observation returned
  for an outbox item must match its exact task, attempt, executor identity and
  executor reference. A mismatch rejects the entire completion transaction.
- Acceptance: reproduce A-outbox/B-observation cross-binding; return one stable
  binding error; prove A, B, command/event/outbox/attempt and Executor effects
  are all unchanged; preserve valid completion, exact replay, transaction
  rollback and reopen behavior.
- Exclusions: no schema change, new Executor policy, outbox operation or
  reconciliation model.

### SRR-02 — A21 Agent-client payload privacy

- Capability/owner: Gateway Agent client/logging boundary.
- Risk: Tier 3 privacy/security.
- Worker-owned source/tests:
  `jiuwenswarm/gateway/routing/agent_client.py`, the directly invoked
  `jiuwenswarm/common/e2a/wire_codec.py`, and their existing focused tests.
- Intended behavior: INFO/DEBUG logs expose only an allowlisted, content-free
  request/response summary; transcript/text/audio/credential/private markers
  never appear at any nesting, casing or separator variant. URI, address,
  object identity, exception/close reason and untrusted scalar values are also
  content-hidden across the real unary/stream codec seam; any correlation ref
  must use a process-temporary secret and never appear in task names as raw
  content.
- Acceptance: first demonstrate current transcript leakage with sentinel
  payloads; verify unary and streaming success/error logs, nested list/dict and
  malformed/private values; cover connect/send/receive/close diagnostics,
  low-entropy ref enumeration, untrusted integers and common E2A success,
  fallback and inverse-error logs; prove the original payload is not mutated
  and non-Live-Voice supported logging remains compatible.
- Exclusions: no global logging framework replacement, retention policy or
  transport payload change.

### SRR-03 — B41 frontend development WebSocket privacy

- Capability/owner: Integrated Web development traffic privacy.
- Risk: Tier 3 privacy/security.
- Worker-owned source/tests:
  `jiuwenswarm/channels/web/frontend/devWsTrafficPrivacy.ts` and
  `jiuwenswarm/channels/web/frontend/tests/devWsTrafficPrivacy.test.mjs` only.
- Intended behavior: real `display_text` and `spoken_text`, including compact
  key variants and malformed JSON fallback text, are never persisted/logged.
- Acceptance: reproduce both leaks; validate structured and malformed paths,
  nested arrays/objects, casing/separator variants and non-sensitive metadata;
  run focused TypeScript/test commands and applicable build/static checks.
- Exclusions: no product telemetry schema, UI rendering or WebSocket protocol
  change.

### SRR-04 — B9 Voice–Task resolver field binding

- Capability/owner: Voice–Task Bridge.
- Risk: Tier 3 authority.
- Main-owned source/tests:
  `jiuwenswarm/server/live_voice/voice_task_bridge.py`, its focused tests and
  the existing product-composition registry integration test only.
- Intended behavior: every populated instruction, confirmation token and task
  ID is independently exact-span validated; conflicting/mutually exclusive
  fields fail closed before confirmation or Task/Tool effects.
- Acceptance: reproduce the mixed-field bypass, add malicious resolver
  combinations, preserve valid committed intent, and assert every forbidden
  effect is zero both at the Bridge and the real product-registry entry.
- Exclusions: no new natural-language classifier, vocabulary or Task operation.

### SRR-05 — B10 static bearer non-ASCII fail-closed behavior

- Capability/owner: P3 authenticated composition.
- Risk: Tier 3 authentication/security.
- Main-owned source/tests:
  `jiuwenswarm/server/live_voice/p3_authenticated_composition.py` and its
  focused tests.
- Intended behavior: invalid non-ASCII configured credentials fail at
  construction; non-ASCII candidates produce the existing typed
  unauthenticated result, never an uncaught `TypeError`.
- Acceptance: reproduce both cases, preserve constant-time comparison for
  supported credentials, and prove zero Store, Executor, authority and Task
  effects.
- Exclusions: no production authentication provider, token format expansion or
  credential migration.

Wave 1 files do not overlap. SRR-01/02/03 implementation workers cannot serve as
their own independent reviewers. Main implements SRR-04/05 and assigns their
independent review after the first worker wave returns.

## 4. Queued repair programs

These groups route work after Wave 1; they are not yet worker write authority.
Each activation will freeze smaller owner-specific packets before editing.

- Generation/successor/authority cleanup: B7, B12, B13, B14, B16, B18, B32,
  B36, B37, B38, B39, D2, L19, L20 and L21. B17 remains an alias of B13.
- Cancellation/teardown/retained cleanup: A2, A7, A8, A16, A19, A20, A22,
  B2, B6, B21, B23, B24, D1, D3 and L7.
- Capacity/lifetime/replay: A1, A5, A6, A9, A13, A15, A17, A25, B4, B11,
  B42, L5 and L18. C3 remains an alias of B42.
- Event-loop, lock and filesystem responsiveness: A4, A11, A14, B15, B25 and
  B27.
- Protocol/state/compatibility: A3, A12, A18, A23, B1, B3, B5, B8, B19,
  B20, B22, B28, B29, B30, B33, B34, B35, B40, L1, L2, L3, L4, L6, L8,
  L9, L10, L11, L12, L13, L14, L15, L16, L17 and L22.

The queue excludes the already fixed A10, A24, B31 and L23; superseded B26;
and rejected C1, C2, C4 and C6–C13. New product policy, classifier, shared
schema/migration or another unrecorded module owner requires an explicit scope
and risk checkpoint before implementation.

## 5. Wave progress ledger

| Checkpoint | Closed unique defects | State |
|---|---:|---|
| Activation | 0/88 | Wave 1 packets frozen; no implementation credit yet |
| SRR-04 / B9 | 1/88 | `6b219bd39` + `d47ef7e58`; mixed-field and wrong-span regressions, real pending-token attack with zero confirmation/Task/Tool/ledger effects; 80 Bridge + 150 registry tests; independently signed |
| SRR-05 / B10 | 2/88 | `9b5b9286e` + `5a0d04917`; typed candidate/config failure, environment-factory zero construction and supported ASCII `compare_digest`; 101 module tests; independently signed |
| SRR-03 / B41 | 3/88 | `b200feff7` + `64236924a`; structured, malformed and separator-variant speech fields fail closed before development WebSocket persistence; focused/strict TypeScript 33/33, Prettier, `tsc` and Live Voice Vite build pass; independently signed |
| SRR-01 / C5 | 4/88 | `ec2f7224b` + `c8f858dad`; exact four-field Executor-observation binding before first Store write, real Core mixed-observation failure with zero cross-task effects, reopen retry and replay; 219 module tests; independently signed |

## 6. Global exclusions

No remote update, `develop` integration, production authentication/tenancy,
public deployment, provider/device configuration, physical product acceptance,
new product policy, new classifier, schema migration or broad unrelated cleanup
is included. P3-2 remains frozen under D-087 and resumes only after this
user-routed repair packet closes or is explicitly re-routed; no P3-2
implementation credit is claimed here.
