# P3alpha formal replacement implementation review — 2026-08-05

> Dated review record for source candidate `40021d71` and its reviewed integration onto `hx/0803_live_voice`. `STATUS.md` remains the authority for mutable progress. Any later semantic change requires affected verification and the D-053 review rule to be applied again.

## Outcome

The integrated batch is **PARTIAL** and acceptable as a backend foundation. It implements the formal TC-B/ED-B/VB-B authority chain behind a disabled product boundary, but it is not a complete ED-B clean-workspace slice, a product route, an Integrated Demo route, an immutable candidate, or an accepted replacement.

The deliberate stop is security-relevant: the current Web `AgentRequest` can supply request-derived consistency scope but not an authenticated principal. The formal mutation route therefore remains unreachable instead of promoting asserted request fields into authorization.

## Candidate identity and scope

- Source candidate: `40021d717014a06cd7dd9a3c7774c2ce670df3a0` on `codex/p3alpha-replacement-a77516a0`, based on `a77516a078ed62f2870583158a4f83919fceb54e`
- Integration branch: `hx/0803_live_voice`; reviewed code base before this batch: `250ffa6da90cda4a6357c7d083e9d1e11dd056ca`
- Integration method: restore the candidate's ten P3alpha source/test/review files without applying its stale `STATUS.md`, then reconcile them against the integrated AIO-B/CR-B/AB-B contracts
- Git state during this record: reviewed P3alpha batch remains uncommitted pending the repository approval Gate
- Production files changed outside the formal P3alpha package: none
- Legacy scheduler role: carrier behind ED only; no new command, event, attempt, reconciliation, or Store authority was added to it

The integration branch contains later work, including `f4535302` resource-closure changes and the AIO-B/CR-B/AB-B foundations. This batch does not edit the resource-closure overlap files:

- `tests/unit_tests/agentserver/test_agentserver_modes.py`
- `tests/unit_tests/conftest.py`

## Implemented boundary

| Stage / module | Implemented function | Authority limit |
|---|---|---|
| Formal models | Closed task, attempt, event, outbox, authorization, resolved-context, Executor-observation, and reconciliation records | Does not create authentication or infer product scope |
| TC-B Store | SQLite WAL command ledger, task/attempt/event snapshots, durable outbox, scoped idempotency, atomic create/cancel, event acceptance, claim lease/fencing, and corruption failure | Does not read or promote legacy scheduler JSON |
| TC-B Core | Exact v2 command/query authorization, create/cancel/get/list/status/events, outbox delivery, restart reconciliation, and pure TaskEvent-to-WorkProgress projection | Does not own Web routing, TTS, UI state, or legacy polling |
| ED-B | Exact project Code Agent binding, formal-attempt idempotency key, persisted provenance proof, explicit status mapping, cancel/status of the original reference, monotonic dispatch/status evidence, and scoped-resource release | Legacy AutoHarness is execution carrier only |
| VB-B policy | Committed voice or structured intent to a formal v2 invocation with ambiguity, confirmation, context, and closed-field gates | Does not persist, execute, authenticate, or speak; VB-C product composition is open |

### Preserved invariants

- One scoped command identity maps to one stored result and one formal attempt; conflicting reuse has zero new effects.
- Create and cancel logical units are atomic across snapshot, append-only event, outbox, and command result boundaries.
- Executor evidence must bind the exact executor, formal task, formal attempt, legacy reference, owner scope, origin namespace, idempotency key, target, and contract before the Core accepts it.
- A dispatch retry reuses the formal attempt. Restart reconciliation never allocates a replacement attempt.
- Active cross-process outbox claims are not stolen. Only claims older than the five-minute acceptance lease are reclaimed, and a new claim token fences stale worker results.
- Cancel before dispatch suppresses dispatch with zero Executor calls. Active cancel targets only the bound original reference. Terminal Executor truth wins a cancel race.
- Unknown, unavailable, rejected, or conflicting external evidence never becomes terminal success.
- A dispatch whose external result is unknown is never reclassified as “never dispatched”; cancellation first recovers the exact binding and then targets that attempt.
- Releasing one failed outbox delivery moves it behind already pending work, so one transient failure cannot monopolize the drain loop.
- Read queries and TaskEvent-to-WorkProgress projection have zero mutation and zero TTS effects.
- Task Core projections are parsed through the integrated strict `WorkProgressEventV2` contract and leave urgency/speakability unknown or non-speakable for Conversation Runtime to arbitrate.

## D-032 scenario matrix

| Category | Applied scenarios and oracle | Result |
|---|---|---|
| P — positive | Authorized create, durable dispatch, real carrier acceptance, active/undispatched cancel, scoped reads, projection, and known restart status succeed with stable identities | PASS for backend boundary |
| N — negative | Missing/wrong authorization, uncommitted or ambiguous voice, confirmation mismatch, foreign scope, hidden payload fields, unsafe context, wrong Executor evidence, malformed JSON, and structurally invalid persisted records reject before forbidden effects | PASS |
| B — boundary | Closed field sets, canonical sorting/fingerprints, empty event suffix, authoritative head, allowed `model_intent`, Unicode/scalar event details, and invalid cursors/types are bounded | PASS |
| S — state | Accepted/running/terminal attempt reduction, task terminal immutability, cancel-request audit state, reconciliation pending/resolved, and non-projectable control events are explicit | PASS for implemented vocabulary; no D0 mapping is invented for `blocked` or `decision_required` |
| T — timing/transaction | Failure injection covers every create and active-cancel persistence boundary; duplicate/conflicting/gapped observations fail closed; external side effect followed by Store rejection becomes `RESULT_UNKNOWN`; later cancel cannot erase that uncertainty | PASS |
| C — concurrency | Cross-instance same-command create, outbox single-claim, live-lease preservation, expired-lease recovery, stale-token fencing, cancel/terminal races, same-attempt retry, and failed-item drain fairness are covered | PASS |
| R — recovery | Undelivered outbox, delivery unavailable, unchanged attempt, confirmed lost attempt, unavailable status, pending cancel suppression, and same-attempt restart reconciliation are covered | PASS for callable reconciliation; runtime startup/periodic composition remains absent |
| I — identity/security | Exact principal/scope/operation/command/target/capability/confirmation/context checks plus persisted legacy attempt provenance and existence hiding are enforced | PASS internally; external authenticated principal source is missing |
| F — failure/capability | Missing authorization, unavailable Store/Executor, unsupported status, redacted/expired/unversioned context, and absent projection capability fail closed or remain explicitly pending | PASS; formal product route stays disabled |
| K — compatibility | Legacy statuses are explicitly mapped; `sch_*` is only an Executor reference; schedule JSON and D-031 monitor never become formal authority; existing carrier regressions stay green | PASS |
| X — cross-module | Policy → Core → SQLite outbox → real project-bound AutoHarness carrier → persisted provenance → formal observations is exercised; TaskEvent projection is validated against the integrated WorkProgress v2 schema | Backend PASS; product/Web/Integrated Demo route and real-service acceptance are NOT RUN |

## D-053 review record

### 1. Source-candidate implementation self-review

The implementation was reviewed against the original P3alpha request, repository rules, TC-A/ACG contracts, D-031 carrier constraints, and tests. Corrections made before independent closure included exact TaskEvent scope, append-only cancel request evidence, authoritative event heads, strict Store JSON failure, immutable origin/context, exact session/revision/model binding, result-unknown separation, and no control-event progress projection.

### 2. Source-candidate cold complete-diff review

Repeated complete-diff review was required because fixes changed resource, identity, concurrency, and lifecycle semantics. Findings were fixed and affected tests rerun:

1. A pinned dispatch binding leaked when validation or carrier handoff failed. Dispatch now uses an idempotent release wrapper and transfers cleanup ownership only after a real carrier reference exists.
2. Dispatch accepted a legacy reference without proving the persisted formal attempt provenance. It now queries the exact reference with the trusted owner/target and validates owner scope, namespace, idempotency key, access, target, and contract before acceptance.
3. Restart reset every claimed outbox row. It now reclaims only expired leases, assigns a new claim token, and rejects stale worker completion.
4. Dispatch discarded a newer persisted lifecycle state. It now selects the furthest forward fact from the validated immediate and persisted responses without regressing a temporarily lagging persisted `pending` state.
5. Cancel and status resolver bindings leaked after use. Both paths now release scoped resources once on success and failure.

One reported integration gap was not changed: no production module constructs this stack. On this base, wiring it would require inventing an authenticated principal from request-derived scope, violating D-033/D-034 and fail-closed authorization. It remains an explicit blocker below.

### 3. Source-candidate independent review equivalent

The in-app `/review` entry was not available. The recorded equivalent was the official current CLI:

```powershell
npx.cmd --yes '@openai/codex@latest' -c 'service_tier="fast"' -c 'model_reasoning_effort="low"' review --uncommitted
```

It ran as Codex `0.146.1`, model `gpt-5.6-sol`, against the complete uncommitted worktree. Earlier attempts using the installed old CLI failed before review, and one initial successful process output was lost during session compaction; neither is counted as closure evidence. Subsequent official reviews produced the five actionable findings above. After all fixes, the final review reported: **“No actionable correctness defects were identified in the current changes.”** Its focused unit/integration run reported 62 passing tests.

### 4. Current-branch integration self-review and cold complete-diff review

The complete source candidate was re-read against the current branch, repository rules, the integrated AB-B `WorkProgressEventV2` schema and the actual tests. Four actionable integration findings were fixed:

1. A previously attempted dispatch released after unknown/rejected evidence returned to `pending`; cancel then mistook it for never dispatched and invented local cancellation while external work could still run. Only a zero-delivery pending dispatch is now locally cancellable. An uncertain dispatch is retried with the same attempt to recover its binding before exact Executor cancellation.
2. Outbox selection always chose the oldest creation time, so one released transient failure could monopolize every drain cycle and starve unrelated pending tasks. Release time now moves that item behind already pending work, with a deterministic two-task regression.
3. The candidate projected Task Core authority with an attempt source ref and invented urgency/terminal speakability. The integrated strict schema requires a task source ref for Task Core authority; projection now validates through `WorkProgressEventV2`, reports unknown urgency, stays non-speakable and leaves notification policy to CR.
4. Store row decoding converted malformed JSON but could leak raw contract/enum/type exceptions for structurally invalid persisted records. All task/attempt/event/outbox row decoders now return stable `TASK_STORE_CORRUPT` failure at the Core boundary; valid-JSON invalid-scope regression proves zero Executor effects.

After the fixes, the implementation pass and a second cold complete-diff pass found no remaining actionable defect inside the bounded backend scope. The authenticated product route, runtime composition and ED clean-workspace Gate remain explicit exclusions rather than inferred completion.

### 5. Current-branch independent review equivalent

The official Codex `0.146.1` CLI independently reviewed the complete current working-tree diff twice after the semantic fixes. It found no additional P3alpha code defect, but it did find two actionable synchronization defects in the adjacent fast-resume documentation/tool scope included with this integration:

1. `STATUS.md` renamed `Verified code base` while the snapshot parser still required that stable label. The label was restored with `250ffa6` identified as the pre-P3alpha reviewed code base; Local Orientation now reports `valid=True` and zero committed files since that base in the current uncommitted state.
2. PowerShell `Get-Content` lines retained ETS metadata in JSON mode. Casting capsule entries to plain strings reduced JSON output to six string entries and preserves the parsed verified base.

Both findings were fixed and their affected Local Orientation/JSON checks passed. The full independent-review logs are machine-local temporary artifacts; this record does not treat them as immutable release evidence or expand the P3alpha acceptance scope.

## Verification

The source candidate's final distinct regression groups were run from its isolated worktree with the neighboring development worktree's Python 3.12 virtual environment:

```powershell
python -m pytest --no-cov -q tests/unit_tests/live_voice
# 114 passed

python -m pytest --no-cov -q tests/unit_tests/common/test_live_voice_contract_v2.py tests/integration/live_voice/test_fake_verticals.py tests/integration/live_voice/test_formal_task_executor_adapter.py
# 43 passed

python -m pytest --no-cov -q tests/unit_tests/auto_harness/test_schedule_task_service.py tests/unit_tests/agentserver/test_schedule_request.py
# 127 passed
```

Historical source-candidate total: **284 distinct tests passed**.

The reconciled current-branch batch was then verified with the current repository environment:

```powershell
python -m pytest --no-cov -q tests/unit_tests/live_voice
# 170 passed

python -m pytest --no-cov -q tests/unit_tests/common/test_live_voice_contract_v2.py tests/integration/live_voice/test_fake_verticals.py tests/integration/live_voice/test_formal_task_executor_adapter.py
# 50 passed

python -m pytest --no-cov -q tests/unit_tests/auto_harness/test_schedule_task_service.py tests/unit_tests/agentserver/test_schedule_request.py
# 127 passed
```

Current-branch affected total: **347 distinct tests passed**. The focused P3alpha subset is 65/65; after final formatting, the modified Task Core file is 38/38.

Additional checks:

- Ruff format/check: all nine implementation and test files pass on the current branch.
- Scoped Mypy with `--follow-imports=skip --ignore-missing-imports`: all five new source files pass. This is not a claim that repository-wide Mypy is clean.
- Fast-resume Local Orientation parses `250ffa6` as a valid verified base; JSON mode emits six plain-string capsule entries rather than PowerShell metadata objects.
- The real-carrier integration constructs the actual `AutoHarnessService`, persists `origin_namespace=live_voice` and the exact formal attempt idempotency key, and verifies the project-bound contract. It is an in-process integration test, not a real external service run.

## Exclusions and blockers

- No authenticated product principal/authorization authority is available on the current product path. Formal external mutation remains disabled.
- No Web/AgentServer composition, feature flag, startup drain, periodic reconciliation loop, route telemetry, UI, speech notification, or Integrated Demo routing is added.
- The ED Adapter reuses the project-bound D-031 carrier but does not relocate or govern `.gitignore`, `coding_memory/`, `prompt_attachment/` or `.agent_history/`; the formal clean-workspace Gate remains open.
- No real external Agent service, browser, audio device, provider, restart process, or immutable service candidate was exercised.
- No `blocked`/`decision_required` legacy status mapping is claimed without a reviewed authoritative D0 source.
- No D-031, TaskBridge, frontend JSON, or legacy scheduler authority was expanded.
- No replacement-ledger credit, Web Alpha credit, or production authorization claim is earned.
- The two `f4535302` overlap files are excluded, so this branch does not claim that commit's AgentServer async-resource closure.

## Next acceptance slice

1. Provide a real authenticated principal and server-resolved authorization/context source; keep the formal route disabled until that exists.
2. Add one product composition owner that constructs policy/Core/Store/ED, performs startup and periodic reconciliation, and exposes route telemetry and flag-off behavior.
3. Close the ED clean-workspace Gate by relocating runtime support files or enforcing an explicit ownership/cleanup contract.
4. Add the reviewed WorkProgress/CR return wiring, route the real P3alpha option through the cumulative Integrated Demo, and run real-service, restart, negative, fallback and immutable evidence gates before assigning replacement credit.
