# D105 W2 signed Gate code removal review

> Date: 2026-08-11
>
> Status: implementation complete; independent-review ceremony unavailable
>
> Base: `031ce406da474b75ecb657295356f0b170b4a730` on `hx/0803_live_voice`
>
> Authority: D-071/D-072 and the user's explicit three-round, single-final-commit instruction

## Outcome and boundary

The retired W2 signed-evidence Gate is removed from the current implementation.
The deletion covers evaluator/scoring/CLI, signing and trust-policy machinery,
manifest/Replacement Ledger handling, evidence exporters/owners, rehearsal
orchestration, fault runners and only those P1/P2/P3 injection seams created to
drive the Gate.

This batch does **not** remove or redesign:

- real P1 capture, Speech provider, TTS or media authority;
- real P2 Agent/Tool submission, presentation, acknowledgement, history or barge-in;
- real P3 confirmation, mutation, same-task A→B→C retry, replay or recovery;
- Task Core/Store/Executor/outbox/lease ownership and zero-side-effect safety;
- bounded X-OBS product diagnostics, the Architecture Contract Gate, Product
  Composition Gate 0 or D-046/D-053 risk policy;
- frozen historical records D90–D102.

The evidence-free D-069 real-runtime P3/restart diagnostic and P2 smoke, plus the
deterministic WAV Speech preflight, remain as optional product-validation aids.
They do not sign, score or create Gate credit.

## Three required removal rounds

### Round 1 — standalone Gate and rehearsal machinery

Analysis located the dependency island formed by `w2_demo_gate`, its CLI and
automated report, key/trust/signature/manifest evaluation, 38-slot scaffold and
the rehearsal controller/choreography scripts. Their importers were Gate tests
and rehearsal entry points rather than product dispatch owners.

The round deleted that island and its exclusive tests. The portable WAV
preflight test was retained. A post-removal import/name scan found no production
consumer of the deleted evaluator/CLI/report modules; remaining hits were the
runtime evidence and injected-fault layer assigned to Round 2.

Confirmation: product modules were not edited in this round, and the baseline
product suite had passed `242/242` before deletion. The retained WAV and product
diagnostic checks remained independently addressable.

### Round 2 — runtime evidence wiring and Gate-only fault seams

Analysis separated non-authoritative evidence callbacks from authoritative
product work. The evidence owner observed results only after normal product
owners had decided them. The injected P1/P2/P3 faults were selected by exact W2
environment variables and existed only for the signed rehearsal runner.

The round deleted the W2 evidence owner/exporter/fault-plan modules, removed
their registration and observer callbacks from Gateway/AgentServer/media/Speech,
removed the exact W2 fault environment variables and branches, and deleted only
their dedicated tests. Real request parsing, authentication, confirmation,
mutation, replay, media completion and cleanup branches remain.

Confirmation: `compileall` passed. The focused Speech file passed `49/49` after
self-review restored an accidentally over-broad test-helper deletion. A wider
run passed `284`, skipped `2`, and reported two unchanged
`test_project_code_executor.py` timing failures. One passed immediately in
isolation; `test_cancelled_attempt_acquire_retains_lease_and_bounds_close`
repeatedly exceeded its fixed two-second Windows wait. Neither that test nor
`project_code_executor.py` is changed by this batch. The exact retained D-069
cancel/stop barrier passes in the final suite below.

### Round 3 — residual entry points, current docs and availability claims

Analysis scanned current source, tests, scripts and mutable documentation for
deleted imports, W2 Gate environment variables, launchers and commands. It also
distinguished the retired signed Gate from architecture/safety gates and normal
X-OBS diagnostics.

The round removed remaining Gate-only launch/configuration files, reduced the
rehearsal README and E2E section to the two retained evidence-free diagnostics,
recorded D-072 and updated the router, roadmap, repository guidance and STATUS.
Cold review found and corrected one stale STATUS sentence claiming the removed
tools still remained available.

Confirmation: current non-historical code has zero matches for the deleted
module names, Gate-only environment variables, controller, fault runner and
product-fault binding. Current operating docs contain no executable signed-Gate
procedure. Frozen historical documents remain intentionally unchanged.

## Final verification

- Affected product and retained-diagnostic suite: `261 passed in 24.74s`.
  It covers P1 Speech, P2/P3 product composition, Gateway media authority,
  AgentServer routes, Web registration, retained WAV assets/preflight and the
  real D-069 cancel/stop barrier.
- Python compilation: all changed retained Python files compile successfully.
- Ruff: all changed retained Python files pass with the repository's existing
  `agent_ws_server.py:E402` excluded. Running Ruff against the base revision
  reproduces that same E402 at line 195, so this batch did not introduce it.
- Whitespace and dependency checks: `git diff --check` passes; current code scan
  has zero deleted-name/Gate-environment references.
- Documentation: changed-document local links pass after this review record is
  present.
- Git invariant: no temporary commit was created. The final task history must be
  exactly one commit above the recorded base; no remote update is authorized.

## Review record and limitation

1. Implementation self-review inspected each mixed source/test diff and fixed
   the over-broad test-helper deletion before the focused suite passed.
2. Cold complete-diff review re-read the original request, repository rules,
   all retained additions, dependency scans and affected tests. It found the
   stale STATUS availability claim and corrected it. No product-path deletion
   finding remains.
3. A literal independent `/review` did not run: no `/review` facility is
   available, and the active developer instruction prohibits spawning a
   subagent unless the user explicitly requests delegation. The substitute is
   the separate cold complete-diff pass plus the focused positive/negative
   regression suite. This record does not claim an independent-review PASS.

## Acceptance impact

This invisible implementation cleanup neither grants nor resets human product
acceptance. W2 remains `MANUAL-ACCEPTANCE-PARTIAL`; the final visible journey in
STATUS is still required. Because this batch removes only retired diagnostic and
fault-injection paths, previously passed visible product steps do not need a
ceremonial repeat solely because of this deletion.
