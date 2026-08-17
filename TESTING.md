# JiuwenSwarm current testing and verification guide

This file is the stable repository-level testing entrypoint. Historical test
counts, coverage percentages and CI designs are available from Git history; they
are not current quality evidence.

## Test authority and discovery

Use the checked-out source, [`pytest.ini`](pytest.ini),
[`pyproject.toml`](pyproject.toml), [`tests/README.md`](tests/README.md) and the
actual `tests/` tree as the discovery authority. Do not infer current coverage,
pass counts or workflow availability from a dated review.

Install the test dependencies:

```bash
pip install -e ".[test]"
```

Common Python entrypoints:

```bash
# Complete discovered suite
pytest

# One directory or file
pytest tests/unit_tests/live_voice/
pytest tests/unit_tests/live_voice/test_product_composition_registry.py

# One exact test
pytest path/to/test_file.py::TestClass::test_case

# Coverage when it is useful for discovery, not as closure by itself
pytest --cov=jiuwenswarm --cov-report=term-missing
```

Frontend packages own their commands in the applicable `package.json`. Run the
focused Node/TypeScript test files first, then the affected package test/build/
typecheck commands required by the changed surface. A historical test count is
never a substitute for command output from the current worktree.

## General verification rules

- Start with the smallest command that proves the changed behaviour, then run
  affected regressions and broader checks in proportion to risk.
- Positive business scenarios must succeed. Negative scenarios must reject,
  fail closed or produce the explicitly contracted safe no-op.
- Any path that can mutate Agent, Tool, Task, audio/history authority, protected
  state or another scope must assert every forbidden side effect as zero.
- Test count and line coverage help discover gaps; neither proves semantic
  closure.
- Fake, mock and deterministic corpus evidence cannot replace a required real
  Provider, browser/device, Agent/Tool, Executor or human-perception journey.
- Record the exact tested source and relevant private-environment labels without
  credentials. A later source or behavioural-input change invalidates only the
  affected evidence and requires affected reruns.
- An unexplained required failure or flaky result leaves the affected scope
  `PARTIAL` or `BLOCKED`.

## Live Voice risk tiers

Live Voice uses the D-046 risk tiers, the D-032 safety invariants and the D-074
review cadence. This section is their stable operational authority; dated plans
and reviews preserve history only.

| Tier | Typical scope | Required verification | Review boundary |
|---|---|---|---|
| 0 | Documentation, mechanical moves/removals, formatting and behaviour-preserving refactors | Affected links, formatting, characterization and repository checks | Scoped diff review; no artificial scenario matrix |
| 1 | Ordinary feature, Port, Adapter and UI work | Positive journey, key negative and flag-off paths, affected integration and regressions | Complete scoped diff review at coherent module/group closure |
| 2 | State, concurrency, mutation, cancel/fence and recovery-sensitive work | Every applicable scenario dimension below, including explicit zero forbidden effects | Design checkpoint only for a new/changed high-risk contract; cold complete-diff review and one independent review at module/group closure |
| 3 | Shared protocol, authority, security, durability and release/product-candidate boundaries | Complete applicable scenario matrix, fault/recovery, real-path evidence and candidate-level cumulative verification | Independent module-boundary review plus cumulative candidate/integration-seam review and required human product acceptance |

### D-032 scenario dimensions

Tier 2 uses every applicable dimension; Tier 3 records the complete applicable
matrix. Inapplicable dimensions are briefly scoped out rather than filled with
ceremonial rows.

| Code | Dimension | Required question |
|---|---|---|
| `P` | Positive | Does the intended business journey succeed and produce exact authoritative truth? |
| `N` | Negative | Are invalid, unauthorized, ambiguous or incomplete inputs rejected/fail-closed with zero forbidden effects? |
| `B` | Boundary/bounds | Are limits, empty/max values, malformed structures and representation boundaries handled explicitly? |
| `S` | State | Are lifecycle transitions, terminal states and closed/tombstoned identities correct and non-revivable? |
| `T` | Time/order | Are stale, delayed, duplicate, reordered and timeout events fenced correctly? |
| `C` | Concurrency | Are races, simultaneous requests and exactly-once/at-most-once effects linearized as contracted? |
| `R` | Retry/recovery | Are retry, restart, partial failure and unknown-outcome semantics truthful and non-duplicating? |
| `I` | Identity/isolation | Are session, scope, project, task, attempt, response and generation bindings exact and cross-scope safe? |
| `F` | Feature/failure/fallback | Does feature-off preserve the old path, and do declared failure/fallback paths remain truthful and bounded? |
| `K` | Compatibility/regression | Do supported existing consumers and persisted/protocol formats retain their contracted behaviour? |
| `X` | Cross-module/real path | Does the actual integration seam work without a fake being credited as product evidence? |

The invariant set is constant across the matrix:

- tests derive from the intended contract, not merely the current implementation;
- ACK, queued/enqueued, timeout and unknown never masquerade as terminal,
  presented or successful;
- Provider/device/Executor/user-observed truth is reported only when that real
  boundary was exercised;
- wrong-target, rejected and stale paths have zero Agent/Tool/Task/audio/history/
  store/other-scope mutation.

## Live Voice review cadence

During implementation, inspect the affected diff and run focused checks. A
small save or intermediate local commit does not trigger a separate independent
review ceremony.

At a coherent module or related-package boundary:

1. review the complete scoped diff from its module baseline;
2. run the module's required focused and affected regression checks;
3. for Tier 2/3, run one independent `/review` or equivalent and record any
   unavailable-tool substitute and limitation;
4. fix findings and repeat only the materially affected verification/review.

At a product candidate:

1. review the cumulative candidate diff and cross-module seams;
2. run the applicable broad automated, build, static and real-path checks;
3. bind results to the exact clean tested source;
4. complete one full human product journey when physical audio, device,
   Provider, Executor or user-perceived behaviour is part of acceptance.

Related packages may share one design checkpoint, implementation batch, module
review and eventual commit when they change one coherent boundary. This does not
weaken their individual scenario coverage. Remote ref updates remain governed
by root [`AGENTS.md`](AGENTS.md).

## Live Voice test ownership during cleanup

Tests are owned by current capabilities/modules, not by numbered delivery
stages. Before deleting an old stage or rehearsal runner:

1. enumerate its unique product and safety scenarios;
2. move each still-applicable oracle to the owning backend/frontend module test
   or an explicit current E2E/support boundary;
3. prove the migrated test fails for the intended defect or forbidden effect,
   then passes on the current behaviour;
4. remove the old runner and stage-named test only after the new owner passes;
5. run affected discovery to ensure the move did not silently reduce coverage.

Do not move test-only fakes, fault injection or conformance recorders into an
apparent production package. Re-home them under an explicit `tests/support`,
fixture or validation-tool boundary.

## Documentation-only verification

For documentation, routing and mechanical deletion batches:

```bash
git diff --check
```

Also resolve every changed local Markdown link, confirm renamed/deleted files
have no surviving inbound route, and compare the authority map across root
`AGENTS.md`, this file, `live-voice/README.md`,
`live-voice/DOCUMENTATION_RULES.md` and `live-voice/STATUS.md`. Documentation
checks do not establish product behaviour or acceptance.
