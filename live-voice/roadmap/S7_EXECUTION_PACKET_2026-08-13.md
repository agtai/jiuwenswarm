# S7/A2 Integrated Candidate execution packet

> Prepared on 2026-08-13; not yet activated. Current activation state remains
> authoritative in [STATUS.md](../STATUS.md). This packet refines, but does not
> replace, §1–2 and §5 of the
> [S5–S8 execution plan](ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md).

## 1. Boundary and ownership

- Stage/node: `S7 - Alpha Integrated Candidate` / `A2`.
- Tasks: `S7-01` through `S7-04`, executed sequentially at one candidate owner.
- Tracks/modules: complete Shared-X, P1, P2, P3alpha and X-E2E integration.
- Risk: Tier 3 because this is the candidate-wide protocol, authority, privacy,
  durability and release boundary.
- Dependencies: all six S6 rows are `SATISFIED`; the post-rebaseline commit audit
  is [D117](../D117_POST_9B8_COMMIT_AUDIT_2026-08-13.md).
- Semantic and integration owner: Main. Historical branches/workers have no
  current ownership.
- Comparison base for the cumulative Alpha diff:
  `2a69c2b87d0ee080a4a30421cbcbcdf93183f340`.
- Entry: only after an explicit instruction to start S7. Preparation of this
  packet is not S7 execution.

Included work is candidate assembly, deterministic automation, selected real
Speech/Media/Agent/Executor/deployment/privacy probes, cumulative review and A3
handoff freeze. Excluded work is new product scope, full P3, D1/D2, Production,
public deployment, mobile/PWA, wider browser promises, credential/account changes
and remote-ref updates.

## 2. S7-01 — candidate assembly and identity

### 2.1 Selective automation port

Use `codex/s7-automation` commit `d2727f20` only as a source of bounded S7
automation. Port onto current HEAD:

- `scripts/live_voice/s7_alpha_verification.py`;
- the five `s7_probe_*.py` entrypoints and `s7_real_probe_support.py`;
- `scripts/live_voice/S7_AUTOMATION.md`;
- `tests/unit_tests/live_voice/test_s7_alpha_verification.py` and
  `test_s7_real_probes.py`;
- the missing frontend Live Voice package-script registrations.

Do not import its broad Python formatting rewrites, stale D113 text or old copies
of Streaming Speech tests/source. Reconcile the automation's expected source
inventory with the later `70dcc563`, `adb55f30` and `e6ccb3e9` changes, then rerun
the two owned automation suites. A direct merge/cherry-pick is forbidden by the
D117 decision.

### 2.2 Candidate freeze

Freeze one clean commit containing all S6 returns and the reviewed automation.
Record:

- exact HEAD, branch, upstream relation and comparison base;
- clean worktree and absence of unintegrated S6 worktrees/patches;
- Python/Node dependency-lock hashes and frontend generated-artifact state;
- exact flags and D-078 Provider/model/voice labels;
- sanitized OS, actual Chrome version, origin, input/output device class,
  network profile, private runtime and disposable project labels;
- zero committed credential, raw audio or private runtime artifact.

Chrome currently reports `151.0.7922.137`; it must be measured again at freeze
time rather than copied from D112. S7-01 exits only when the identity is
reproducible and the worktree is clean.

## 3. S7-02 — complete candidate verification

Run every item against the exact S7-01 identity; historical S6 counts are context
only.

1. Run the automation runner's candidate identity, source hygiene and dependency
   checks.
2. Run the cumulative backend Shared/P1/P2/P3alpha/X matrix, affected Gateway,
   AgentServer, WebChannel, Store/Executor and integration regressions with the
   repository's `--asyncio-mode=auto` intact.
3. Discover and execute every tracked frontend Live Voice/compatibility test,
   TypeScript/static checks and the Vite production build.
4. Run the real Speech/Media probe with fixed corpus, Provider-time EOT,
   streaming downlink, playout completion and p50/p95/failure/sample output.
5. Run the real Agent/Direct Executor probe against isolated no-remote disposable
   projects, including exact task completion/cancel and zero cross-project effect.
6. Run benchmark/fault profiles, secure private HTTPS/WSS deployment preflight
   and the whole-stack privacy/raw-audio-zero-persistence probe.
7. Record sanitized commands, outcomes, sample counts and failure reasons outside
   the source worktree, bound to both the candidate and runtime declaration.

Any failed positive journey, accepted negative side effect, stale media/UI/history
effect, wrong-scope mutation, credential exposure or raw-audio persistence blocks
S7-02. A source repair creates a new candidate identity and requires affected
runs again.

## 4. S7-03 — cumulative cold review

Review `2a69c2b8..candidate` against the original Alpha request, repository rules,
the complete [Alpha acceptance contract](../validation/ALPHA_ACCEPTANCE.md) and
actual S7-02 output. The review must cover:

- P1 capture/recognition/synthesis/playout ↔ P2 realtime media ownership;
- P2 response/progress/cancel ↔ P3alpha Task/attempt authority;
- frontend ↔ Gateway ↔ AgentServer identity, fallback and presentation seams;
- Store ↔ Executor restart, outbox, cleanup and exact-cancel truth;
- observability ↔ privacy, including malformed/error/timeout paths;
- flag-off and every applicable D-032 zero-forbidden-effect dimension.

Obtain one independent review. If no independent entry is available, record the
exact substitute and limitation without claiming independence. Fix findings and
rerun affected plus cumulative checks; repeat the final review only if a fix
materially changes integration semantics.

## 5. S7-04 — A3 handoff freeze

Bind the successful candidate, runtime declaration, Provider/Executor,
disposable project, flags, known warnings/deviations and S7 reports to the
[Alpha showcase](../demo/ALPHA_SHOWCASE.md). Confirm the script requires no source
repair or hidden route switch and is executable end to end by the user.

S7/A2 closes only when S7-01 through S7-04 refer to the same clean source and no
critical finding remains. It does not produce final Alpha PASS; only S8/A3 can do
that after the complete human journey.
