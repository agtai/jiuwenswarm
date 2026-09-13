# P3-9 W3 migration evidence — 2026-08-25

## Result

**PASS for the bounded local migration and automated regression boundary.** The
nine P3-9 product/test commits from `codex/p3-9-final-543350c9` are integrated
patch-for-patch onto `hx/0812_live_voice_w3`. The tested product/test source is
`edcc55d4351dac0fbd909c279fb5443faf2a062b`; the tested documentation source is
`1742c1b4e5fa5e7a25a7b41dad9c8eef8453e3cc`.

This result closes the transplant, conflict-resolution and automated
verification work only. P3-9 remains **ACTIVE / PARTIAL** until the required
human acceptance and final independent Tier-3 review both complete. It grants
no P3-9, controlled-candidate, physical-product or production PASS.

## Source and scope

- Source branch/head: `codex/p3-9-final-543350c9` at
  `6bcb74cb7322c15ed9970d8600958252e3dbb890`.
- Target branch/baseline: `hx/0812_live_voice_w3` at
  `510f616d18a315bfe7f2ec702dba4419541de44a`.
- Owned boundary: the P3-9 cumulative one-product Registry/current-projection,
  presentation-ownership, frozen release-create and source-event-result
  product/test changes plus their current-status documentation.
- Explicit exclusion: source commit `5415a3d3` is an older sibling L0 baseline
  and was not migrated. W3 already contains the later accepted D-097 L0 line;
  replaying `5415a3d3` would regress current authority rather than preserve P3-9.

## Commit mapping and patch identity

| Original | W3 commit | Stable patch ID | Disposition |
|---|---|---|---|
| `cd93abff` | `ba35c34c` | `c3e68c664550f16006508286e245b3437756bdab` | Product/test patch identical |
| `7e70ba45` | `1dd68551` | `009d70a9c5a6133f9c29e0d187f64ea8e2bd6011` | Product/test patch identical |
| `215910d1` | `2b2e8199` | `0bf97c575b4357b32856a2537179e5923d533565` | Product/test patch identical |
| `543350c9` | `41360bc1` | `43cceb3a00ec0039a29de807f3cb3d2ec598675e` | Product/test patch identical |
| `007e9e2e` | `a84ac124` | `6660c642b5be254ea6b4304222f5fc87112d6192` | Product/test patch identical |
| `c2302222` | `7f1973c9` | `0f0ee709ccdf11eba8378b0445ff1e30c1ca16a7` | Product/test patch identical |
| `15bef847` | `4d208e17` | `ae73a7c6ba06220b520180b20edaade307f6b6e6` | Product/test patch identical |
| `3fe7fb77` | `aab8259f` | `1b5df2568d714ac281277b07fd7372ff37fa35ad` | Product/test patch identical |
| `e462abda` | `edcc55d4` | `95a60cb8d8e7bf33f5b9606bdd96a404772a006b` | Product/test patch identical |
| `6bcb74cb` | `1742c1b4` | Not applicable | STATUS was resolved semantically against newer W3 authority |

## Conflict and documentation disposition

All nine code/test cherry-picks applied without textual conflict. The source
documentation commit conflicted only in `live-voice/STATUS.md` and was resolved
by preserving the target's newer D-097 L0 closure, current P1/P2 facts and
existing decision sequence while adding the P3-9 migration map and remaining
Gate truth.

The current authority documents were checked for duplicate Markdown headings
and duplicate `D-###` identifiers; none were found. The accepted decision tail
remains unique through D-097. Historical statements that an earlier packet did
not execute P3-9 remain in their time-scoped history and were not rewritten as
current status. Acceptance instructions remain owned by the product acceptance,
showcase and runbook documents; only current progress is synchronized here and
in `STATUS.md`.

## Verification

The following checks ran on a clean worktree at documentation source
`1742c1b4e5fa5e7a25a7b41dad9c8eef8453e3cc` unless noted otherwise.

1. Formal Integrated Web regression:

   ```powershell
   npm run test:live-voice-integrated-web
   ```

   Working directory: `jiuwenswarm/channels/web/frontend`.

   Result: **483 passed, 0 failed**.

2. P3-9 affected Python set:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q tests/integration/live_voice/test_d90_formal_task_vertical.py tests/unit_tests/live_voice/test_p3_wave2_real_evidence_producer.py tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/live_voice/test_task_progress_return.py tests/unit_tests/live_voice/test_task_result_event_consumption.py tests/unit_tests/live_voice/test_voice_task_bridge.py
   ```

   Result: **488 passed, 3 skipped**.

3. Complete Python Live Voice unit/integration regression, retaining the
   repository's required automatic asyncio mode while omitting only coverage
   report generation:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q -o "addopts=--asyncio-mode=auto --strict-markers --tb=short" -o "log_cli=false" tests/unit_tests/live_voice tests/integration/live_voice
   ```

   Result: **2936 passed, 5 skipped**, one existing third-party Authlib
   deprecation warning.

4. Frontend typecheck and production build:

   ```powershell
   npx tsc --noEmit
   npm run build:live-voice
   ```

   Working directory: `jiuwenswarm/channels/web/frontend`.

   Result: **PASS**; Vite transformed 4,650 modules. Existing non-failing
   duplicate-locale, dynamic-import and large-chunk warnings remain outside
   this migration boundary.

5. Changed Python static and repository checks:

   ```powershell
   .\.venv\Scripts\python.exe -m ruff check jiuwenswarm/server/live_voice/voice_task_bridge.py tests/integration/live_voice/test_d90_formal_task_vertical.py tests/unit_tests/live_voice/test_p3_wave2_real_evidence_producer.py tests/unit_tests/live_voice/test_product_composition_registry.py tests/unit_tests/live_voice/test_task_progress_return.py tests/unit_tests/live_voice/test_task_result_event_consumption.py tests/unit_tests/live_voice/test_voice_task_bridge.py
   .\.venv\Scripts\python.exe -m compileall -q jiuwenswarm/server/live_voice/voice_task_bridge.py
   git diff --check
   ```

   Result: **PASS**.

An initial diagnostic command incorrectly replaced all `pytest.ini` addopts,
including `--asyncio-mode=auto`; its 31 unhandled-async errors and one strict-mode
joint-scenario symptom are invalid as regression evidence. The joint D90 test
passed under the unmodified repository configuration, and the corrected full
Live Voice command above passed all 2,936 executed tests. No product-code change
was made for that command error.

## Remaining Gate and non-claims

The remaining required work is:

1. run the human acceptance on the exact integrated candidate, including the
   visible formal P3 panel and the separate user-confirmed real voice journey;
2. obtain final independent Tier-3 review on that candidate and resolve any
   actionable finding before recording a scoped PASS.

Credentials, model/provider configuration, project registration, browser
permissions, audio-device selection, runtime data and network availability are
machine-private prerequisites and are not restored by Git. Generation-time
interruption, fixed-corpus latency/generalization, long Provider degradation,
production auth/tenancy/deployment/SLO, D1 and host-crash/real-production-failure
credit remain outside P3-9. At evidence creation time no remote ref was updated.
