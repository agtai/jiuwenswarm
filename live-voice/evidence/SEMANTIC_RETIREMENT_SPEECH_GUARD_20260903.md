# D-108 speech admission correction — 2026-09-03

## Scope and source

Module baseline: `7a6ea64a328af654aa7183adc8e77ff990883ba0`, on the
user-confirmed `hx/0812_live_voice_w3` branch. This record belongs to the
`fix(live-voice): remove lexical speech confirmation blocking` commit containing
it. No unrelated user changes were present. No service or remote ref was changed.

This is the Tier-3 receipt/Guard correction accepted in D-108, with Tier-1
dependent launcher/probe assertions and Tier-0 active documentation. It is not
the whole D-107 production semantic cutover or an accepted product candidate.
The previous model-boundary evidence remains an immutable record of the earlier
proposal; the user subsequently rejected extra per-sentence readback confirmation.

## Changed boundary

- `batch_speech.py` no longer imports/scans CriticalTokenPolicy to redeem a
  receipt, reads a speech Demo bypass flag, or accepts a bypass constructor
  switch. Exact text/session/correlation/interaction/turn/commit binding, expiry
  and same-binding replay remain. A client `critical_confirmation` value is
  wire-compatible but grants nothing; normal claims say `eligible`.
- `critical_token_safety.py` no longer treats absent confidence as uncertainty.
  Existing actual low confidence, conflicting hypotheses, explicit uncertainty,
  bounds, finality and generation/dispatch fences remain. No new parser or
  readback workflow was added. Its diagnostic categories and unused legacy
  error enum are not evidence of full semantic retirement.
- Registry keeps both normal and legacy `confirmed` speech as SPEECH; retired
  bypass claims reject even when the old business Demo flag is enabled. Formal
  Task operation/target/specification confirmation was not weakened.
- The existing startup probe and launcher now expect `eligible`, preserving
  real Provider, identity-mismatch, forgery, zero-business-effect and failure-exit
  assertions. Gateway and AgentServer must be updated together. The old business
  bypass/itinerary paths still exist and are explicitly outside this repair's
  retirement claim, not silently considered removed.

## Automated attempts and review

Commands use `.venv/Scripts/python.exe -m pytest` from the repository. The final
combined command is:

```powershell
.venv/Scripts/python.exe -m pytest `
  tests/unit_tests/live_voice/test_critical_token_safety.py `
  tests/unit_tests/live_voice/test_batch_speech.py `
  tests/unit_tests/live_voice/test_product_composition_registry.py `
  tests/unit_tests/live_voice/test_p3_authenticated_composition.py `
  tests/unit_tests/gateway/test_app_gateway_acp.py `
  scripts/live_voice/w2_rehearsal/tests/test_portable_launchers.py `
  -q -o addopts= -o console_output_style=count -o log_cli=false --tb=short
```

- New normal amount/date/negative-language and receipt cases: **9/9 RED** before
  the product change. They then pass without bypass, including unchanged exact
  replay and rejection of receipt rebinding.
- Initial two-file regression: **119 passed**. Initial Registry focused set:
  **4 passed**.
- First five-file regression: **586 passed / 1 failed**. The durable rejection
  replay test used missing confidence to create rejection. Its input now injects
  explicit recognition uncertainty at a test-owned seam; the durable result,
  replay, zero Agent/Task effects and added single-evaluation oracles remain.
  Focused rerun passes; the five-file rerun reports **587 passed**.
- Independent review found one M1: the earlier P2-origin rejection maps/ledger
  oracles had not been migrated with its positive replacement. Two new tests
  restore them for `eligible` and `confirmed`. Their initial run (and a concurrent
  independent run) failed with `AttributeError` from using the wrong stub call
  counter; correcting the test to its actual query/production authority/reader
  counters yields **2 passed**. No product failure was hidden or skipped.
- Final six-file regression: **595 passed**, no skips, 113.89 seconds. The only
  warning is the imported Authlib deprecation from model-builder coverage.
- Independent review: **C0/I0/M0** after M1 correction. The reviewer independently
  ran 21 focused receipt/Guard/formal-confirmation tests, two launcher/probe tests
  and the two new P2 tests. A separate process-only mutation prematurely reserved
  Task origin before a real Guard rejection: both new tests went RED at their
  pending-origin assertion. No file, real Task or service was changed by mutation.
- Ruff check/format, Python compilation and diff checks are part of the local
  closure. No Web source/schema changed; TypeScript/build and complete-candidate
  regression remain owned by the subsequent cumulative semantic cutover.

Applicable dimensions: P/N/B/S/T/C/R/I/F/K/X cover the real in-process
Gateway/service/Registry/confirmation seams, replay/expiry, lifecycle and failure
boundaries in these suites. No new Store migration, checkpoint, scheduling,
device configuration or business tool was introduced. Mocked Agent/Executor tests
are not real execution or audio evidence.

## Real Provider component probe

Entry: `scripts/live_voice/formal_web_runtime_probe.py`. The controlled launcher
normally supplies its environment. This run loaded the existing saved runtime's
private `.env` in the test process only, set the existing batch-enable/provider
selection and the launcher's `marin` voice, without copying credentials or
altering the saved config. Models were the existing
`gpt-4o-mini-tts-2025-12-15` and `gpt-4o-mini-transcribe-2025-12-15`.

Attempts are not collapsed into an apparent first-run success:

1. Direct probe: exit 1. The manual invocation omitted the launcher's voice.
2. Diagnostic wrapper: FAIL at TTS with BatchSpeechError. Read-only inspection
   confirmed the missing voice; synthesis rejects before making a Provider HTTP
   request. This was test preparation, not a Provider outage or policy rejection.
3. With the same voice as the actual launcher: **PASS**. Real TTS bytes went
   directly to real STT, then the Gateway receipt seam. Observed result: 19
   recognized characters, one fixture token, policy `eligible`, identity mismatch
   rejected, client-forged claim rejected, zero business effects. Audio and
   transcript remained in memory and were not retained. All attempts used bounded
   calls; the diagnostic wrapper passed requests/results through unchanged.

This probe is **not browser microphone input**, not output playback, not the new
model parser/Agent/Task/Tool journey and not human physical acceptance. It grants
only the actual Provider-to-receipt component evidence stated above.

## Remaining claims

The receipt/Guard source, regression and independent review close this repair.
Full production hardcode retirement, sole semantic Registry integration,
presented-Agent proposal recovery, generic Executor/launcher cleanup, mandatory
browser audio E2E and final human journey are not completed by it. Those current
Gates remain in [STATUS](../STATUS.md). No Production-ready claim or remote push.
