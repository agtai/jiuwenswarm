# Integrated Web Alpha seam-contract preflight review

> Review date: 2026-08-11
> Reviewed code: `694533115d5c046718dba16df7b2c1eae3a38f6e` (branch `codex/integrated-web-alpha-20260808`)
> Fork point from the W2 line: `5ac969af8244094973ae1b7f1ced9d761199b921`
> Method: read-only pinned detached worktree; no edit, commit, integration, or remote ref update
> Acceptance authority: [Integrated Web Alpha acceptance](validation/ALPHA_ACCEPTANCE.md)
> Mutable state: [STATUS.md](STATUS.md)

This is an immutable engineering record of a **preflight analysis** performed before entering
second-stage Alpha execution. It is deliberately **not** a D-053 third independent review pass,
produces **no** `PASS`/`NOT PASS` verdict, and grants **no** Gate or Replacement Ledger credit.
Its purpose was to find foreseeable seam-contract defects early. The batch's own engineering
record remains [INTEGRATED_WEB_ALPHA_EXECUTION_REVIEW_2026-08-08.md](INTEGRATED_WEB_ALPHA_EXECUTION_REVIEW_2026-08-08.md).

## 1. Scope reviewed

Eleven commits, `5ac969af..694533115`, 26 files, +9041/-289. Grouped by theme:

| Theme | Commits | Nature |
|---|---|---|
| Deterministic conformance skeleton | `49430bca` Cascade fake, `42124669` streaming Speech (1612 new lines), `9ee149e6` Alpha benchmark (430 new lines), `f525109c` D90 voice-origin binding | New modules, **zero product wiring** |
| P1 exact barge-in fencing | `05187943`, `abc4d5b9` | `stopAgentPlayoutExact` local-stop receipt; media authority revocation moved off the critical path into retained cleanup |
| P3 Web six-operation control surface | `a367c236`, `950ae8f1` | Largest change: query owner, event identity/sequence ledgers, lifecycle provenance, reconnect/replay monotonicity |
| D0 executor byte preservation | `73a21d05`, `11ff0f48` | Git-visible content mirroring across worktrees; attempt-root Agent creation and retirement |
| Documentation | `69453311` | Execution review, STATUS/README routing |

Baseline verification observed on the reviewed SHA: `ruff check` PASS on all six changed Python
files; `ruff format --check` **not clean for four of six** (pre-existing); five focused backend
suites `243 passed`; frontend `test:live-voice-integrated-web` `174/174` with strict TypeScript.

## 2. Module boundary and W2 seam

Three new modules (`streaming_speech.py`, `alpha_benchmark.py`,
`ScriptedCascadeInteractionEngine`) have no importer anywhere in the tree. They are conformance
and summarization boundaries only; passing tests on them are not product-route evidence.

The wired surface is:

```
LiveVoiceIntegratedRoutePanel.tsx
  -> productWebActivation.ts (ProductWebP3TaskQueryOwner)
       -> Gateway live_voice.task.{get,list,status,events}   (pre-existing routes, unchanged here)
  -> formalTaskControlLeaf.ts (client-side authoritative replica)
p3_authenticated_composition.py (_AttemptScopedProjectExecutor)
  -> agent_manager.cleanup_live_voice_formal_task_agent()    (new seam)
  -> project_code_executor._project_content_fingerprint()    (cross-module private import)
```

**Seam with the W2 line.** At analysis time the W2 branch head was `b4abff6cf`. Comparing both
branches against the shared fork point, **18 of the 26 files** changed by this batch were also
changed on the W2 line, including all four core frontend modules and all three core backend
modules. The most significant overlap is not textual but semantic: the two lines independently
built **two incompatible implementations of the same seam**.

| Seam | This batch (`11ff0f48`) | W2 line (D-095 repair) |
|---|---|---|
| `agent_manager` | `cleanup_live_voice_formal_task_agent()` | `acquire_live_voice_formal_task_attempt_agent()` / `release_...()` / `_strictly_quiesce_...()` |
| P3 resolver | `_AttemptScopedProjectExecutor` (async-generator wrapper) | `acquire_attempt_executor()` / `release_attempt_agent()` (explicit acquire/release) |

This requires an ownership decision before merging; it cannot be resolved textually. The
explicit acquire/release shape is structurally preferable because it does not place teardown
inside an async generator's `finally` — see finding **A-1**. The W2 side of this seam is recorded
in `D95_P3_D0_ATTEMPT_BINDING_REPAIR_2026-08-08.md`, which exists only on the W2 line: it was
created after the fork point, so it is deliberately not linked from this branch.

## 3. Seam-contract pattern sweep

Eleven defect patterns previously observed and fixed on the W2 line were used as a checklist.
Line numbers refer to the reviewed SHA.

### Confirmed findings

**A-1 — teardown shadows the authoritative error, and async-generator finalization is unordered.**
`p3_authenticated_composition.py:615-633`. Attempt Agent retirement ran in the stream's
`finally` and raised on failure, replacing whatever exception was already propagating; the
upstream classifier at `project_code_executor.py:1917-1944` keys on the raised reason, so any
Executor failure could surface as `PROJECT_EXECUTOR_AGENT_CLEANUP_FAILED`. The author was
partly aware — the third raise site carried `from stream_error` — but `raise X from Y` still
replaces the propagating exception. Separately, the consumer used a bare `async for`, which
does not close an abandoned async generator; on cancel or early exit, retirement was deferred
to event-loop finalization, unordered against attempt worktree cleanup and with its outcome
swallowed. **Impact: high** — breaks stable error classification and the "attempt Agent is
always retired" invariant on the cancel path, which is a specified route.

**A-2 — rollback leaves directories no fingerprint can see.**
`project_code_executor.py:712` materialized parent directories before checking whether the
source path was being removed, so a rolled-back attempt left empty directories in the real
project. Git cannot represent an empty directory, so the residue was invisible to both
`_project_content_fingerprint` and `_project_tree_fingerprint` — the zero-side-effect oracle
itself. **Impact: medium-low**, but it is a literal violation of "forbidden side effects equal
zero" on a rejected path.

**A-3 — task correlation inferred rather than confirmed.**
`formalTaskControlLeaf.ts:966-977` stored `correlation_id` from the local control binding when
adopting a `task.create` result. Task Core owns that value and its mutation result does not echo
one (`task_store.py:445-452` returns only `task_id`/`attempt_id`/`state`/`outbox_id`). Every read
path enforces the field by equality (`:454`, `:1008`, `:1101`). The two values happen to agree
today because both derive from the client-supplied `correlation_id`, so this was latent — but a
single divergence would fail permanently, and because `task.list` is all-or-nothing it would take
the entire scope's list view down. **Impact: medium** (latent, unrecoverable when triggered).

**A-4 — validator name and message promise more than the implementation delivers.**
`product_composition_registry.py:149-158`. `_require_exact_params` checked only `keys - allowed`
while its message read "fields are incomplete or unknown", and the P3 confirmation call site at
`:2809` passed `frozenset(required | optional)`, making the carefully constructed required set at
`:2805-2823` dead code. Inherited, not introduced by this batch. Downstream
`_validate_params` (`p3_authenticated_composition.py:1748`) does check both directions, so no
`KeyError` escaped — the defect was misleading code, not a live crash.

**A-5 — zero-side-effect test oracles were unreliable in two distinct ways.**
`test_p3_authenticated_composition.py:416-421`. `_store_counts` counted rows in five tables. It
cannot see an in-place mutation, and it excludes `p3_confirmations` and lease state entirely.
Separately, several baselines were captured **before** authorized setup writes, attributing setup
to the rejected path under test. Both weaknesses masked each other: the tests passed only because
the oracle did not observe the table the setup wrote to. Additionally,
`test_attempt_agent_lifecycle_changes_never_become_authority_output:2425-2526` asserted the
authority root was unchanged across all three mutation phases, but nothing in that test can ever
write to the authority root, making that assertion vacuous.

**A-6 — bare dict subscript in a fail-closed path.**
`interaction_engine.py:492`, `_CASCADE_ACTION_BY_OBSERVATION[observation.kind]`. All ten enum
members are currently mapped, so this is latent; a newly added `CascadeObservationKind` would
escape as an uncaught `KeyError` rather than a fail-closed violation.

**A-7 — retained-identity reporting undercounts.**
`streaming_speech.py:845-849` omitted `_response_generations` from
`retained_identity_tombstones`. That ledger is capacity-bounded and never evicted, so a capacity
monitor under-reports retention and can reach `RESPONSE_IDENTITY_CAPACITY_EXHAUSTED` unwarned.

**A-8 — release cursor behaves differently for the same no-op.**
`interaction_engine.py:503-512`. `release_through(0)` raised `RELEASE_CURSOR_AHEAD` on a fresh
engine but returned `0` for the identical call after any observation.

**A-9 — design tension: run-time artifacts must be predeclared before the run.**
`alpha_benchmark.py:142` and `:300`. `expected_correlations` must be frozen before collection and
is compared by **exact set equality** per target. Correlation IDs are run-time products, so the
plan can only be frozen after a rehearsal export — structurally identical to the W2 trust-policy
`proven_subjects` tension. Stricter than it first appears: every target must observe *every*
declared correlation, so a legitimate run in which one turn exercises P1 but not P3 will always
report `CORRELATION_COVERAGE_INCOMPLETE` for the P3 target. This is a contract property to plan
around, not a code defect.

**A-10 — cross-module private import.**
`p3_authenticated_composition.py:63` imported `_project_content_fingerprint` from
`project_code_executor`, turning that module's internal fingerprint algorithm into an implicit
cross-module contract.

### Checked and not present

**Transport identity promoted to business identity.** Verified clean. `request_id` from
`allocateProductRequestId` is used only for transport-level response matching in
`requireP3TaskQueryResult`; `connection_generation` is used only as a staleness fence;
`deriveFormalTaskQueryBinding` (`formalTaskControlLeaf.ts:527`) derives `correlation_id` from the
**server task result**. The only adjacent issue is A-3, recorded separately.

**Type-semantic misuse of validators.** Checked `streaming_speech._required_text`,
`formalTaskControlLeaf.text()`, and `alpha_benchmark._safe_label`. The strict label regex is
applied only to genuine labels, never to a path, URL, or free-text field. One input constraint
worth documenting operationally: `declared_environment_id` uses the label regex and therefore
rejects spaces.

**Event generation ordering.** Verified against both sides. The frontend requires an attempt
lifecycle event to be immediately followed by its exact consecutive task lifecycle event with
matching `source_event_id`/`causation_id`/`outcome`
(`formalTaskControlLeaf.ts:272-282`, `:358-376`). The server appends in exactly that order and
assigns both events the same `observation.source_event_id`
(`task_store.py:1218-1273`). Producer allowlists also match. No mismatch.

**Binding validation too loose.** Not present. Identity checks use equality, not `isinstance`:
`streaming_speech.py:1023`, `:1051`; `formalTaskControlLeaf.ts` `sameBinding`, `requireScope`,
`:943`. `isinstance` appears only as a type gate followed by an equality check.

**Error classification overridden by structural validation — initially reported, then
withdrawn.** The `required` sets in `_validate_params`
(`p3_authenticated_composition.py:1691-1753`) do contain `auth_token`, which resembles the W2
defect. It is **not** a defect here: `authenticate()` is called *before* `_validate_params()` at
`:1368`, `:1481`, and `:1546`, and `StaticBearerAuthenticator.authenticate` correctly raises
`FORMAL_TASK_AUTHENTICATION_REQUIRED` / `UNAUTHENTICATED` for `None` (`:207-216`). The initial
report was produced by inspecting the required set without following call order, and is recorded
here so the same analysis error is not repeated. A related trap exists for anyone fixing A-4:
adding a genuine required-key check must exclude `auth_token`, or it will introduce exactly the
downgrade this pattern describes.

**State-space blind spots.** No new instance found in this batch beyond A-2. The known
`retry_readiness` / `ATTEMPT_JOURNAL_MISSING` case does not exist on this branch at all, because
the fork predates the W2 retry work.

## 4. Findings outside the pattern checklist

**B-1 — client hard caps against an unbounded server, with no pagination.**
The frontend rejects above 256 (`formalTaskControlLeaf.ts:888`, `:1034`). The server is
unbounded: `task_store.py:1481-1487` (`list_tasks`) and `:1502-1520` (`events`) carry no `LIMIT`,
and `persistent_task_core.py:399-400` explicitly declares `"truncated": False,
"cursor_replay_supported": False`. The two contracts are irreconcilable and degrade
monotonically: the 257th task makes `task.list` permanently unusable for that scope, and a task
that reaches 257 events can never be inspected at all, because establishing a cursor requires an
initial `after_seq = -1` full read (`:1061-1070`). **Impact: high** for any long-running real
session. Resolving it is a product contract decision (truncation semantics, cursor recovery
rules), not a defect fix: the server would need `limit` plus an honest `truncated`, and the
frontend would need to retain its lifecycle checkpoint across pages.

**B-2 — `adoptProgress` is not wired into any product path.**
`formalTaskControlLeaf.ts:985-1030`, along with `FormalTaskProgressOrigin`, the
`#progressReceipts` ledger and `max_progress_receipts`, is called only from
`tests/formalTaskControlLeaf.test.mjs`. The panel's progress route uses
`ProductWebP3ProgressOwner` and does not pass through this leaf. The batch's execution record
describes `950ae8f1` as "query/mutation/**progress** authority closure"; that holds at the
source/conformance level but not at the product level, and the distinction matters for
acceptance planning.

**B-3 — pre-existing failure unrelated to this batch.**
`tests/unit_tests/agentserver/test_agent_manager_session_cleanup.py::test_same_key_creation_waits_for_old_root_cleanup`
fails on the reviewed SHA. Reverting `agent_manager.py` to its fork-point version does not fix
it, so it predates this batch. Full `tests/unit_tests/agentserver` on the reviewed SHA:
`1 failed, 1586 passed, 2 skipped`.

**B-4 — pre-existing flaky test.**
`test_project_code_executor.py::test_direct_cancel_flag_crosses_process_lease_without_widening`
fails intermittently only under a full cumulative run. Measured on the reviewed SHA: one failure
in seven cumulative runs. It passes 5/5 in isolation and 3/3 for its whole file.

## 5. Verification performed for this review

All commands ran against the reviewed SHA in the read-only pinned worktree, using the repository
virtual environment with `--no-cov`, repository `addopts` disabled, automatic asyncio mode, and
the third-party `pysbd` `SyntaxWarning` ignored.

| Check | Result |
|---|---|
| `ruff check` on the six changed Python files | PASS |
| `ruff format --check` on the same files | 4 of 6 would reformat (pre-existing baseline, not a finding) |
| Five focused backend suites | `243 passed` |
| Cumulative `tests/unit_tests/live_voice` + `tests/integration/live_voice` | `1232 passed`, plus the B-4 flake in one of seven runs |
| `tests/unit_tests/agentserver` | `1 failed, 1586 passed, 2 skipped` (B-3) |
| Frontend `test:live-voice-integrated-web` | `174/174`, strict TypeScript and bundle PASS |

## 6. Limitations

1. No runtime verification of any kind: no Chrome, no Speech Provider, no real P3 Executor, no
   deployed origin. Every finding is from static reading plus automated suites.
2. The real DeepSeek/`write_file` probe described in the batch's execution record could be
   neither reproduced nor falsified; its fixture is outside the repository.
3. X-OBS and the observability backend were not reviewed; this batch does not touch them.
4. Rename detection in `_apply_attempt_patch` was reasoned about but not exercised with a
   constructed rename case. `git diff --binary` may emit rename hunks under `diff.renames=true`
   while `changed_paths` uses `--no-renames`; the `--no-renames` path list appears to be a
   superset and therefore safe, but this was not proven by test.
5. Merge conflict analysis stopped at file-overlap and semantic-duplication level; the 18
   overlapping files were not analyzed hunk by hunk. That work belongs after the ownership
   decision in section 2.
6. No Gate, acceptance, or Replacement Ledger credit is claimed or implied by this record.

## 7. Disposition

Findings A-1 through A-8 and A-10, plus B-2, were addressed on a local branch built on the
reviewed SHA; that branch has no upstream and was not pushed. Its three commits are scoped so
they can be adopted independently, which matters because A-1's file set is entangled with the
unresolved ownership decision in section 2.

A-9 and B-1 were deliberately **not** changed. A-9 is a contract property that must be planned
around (freeze the benchmark plan from a rehearsal export). B-1 is a product contract decision
whose frontend half would require editing the authoritative event-validation path without any
runtime environment to verify against; the risk exceeds the benefit until truncation semantics
are accepted.

B-3 and B-4 are pre-existing and were left untouched.
