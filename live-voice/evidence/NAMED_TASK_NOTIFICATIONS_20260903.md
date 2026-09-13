# Named Task notifications — 2026-09-03

## Scope recorded before implementation

Baseline: `2ab12a08889cb72dabcd41ce5e9d8aaaa0f80ae8`.
The user requested recording the cumulative capture-capacity defect, adding Task
names to notifications, and redeploying the existing local formal runtime.

- Notification wording is Tier 1: use the exact scoped Task's `spec.name` in
  running, blocked/decision and terminal presentation text, including voice and
  its existing text fallback. Names are presentation data, never target selectors.
- Own `product_composition_registry.py`, the integrated panel's existing per-Task
  notification metadata/text fallback, and their focused tests. Preserve existing
  language selection, accepted suppression, source/result validation, timestamps,
  presentation identity, ACK and replay behavior; no protocol/Store migration.
- Verify two distinct Task names, Chinese/English, terminal result validity,
  text/voice consistency, affected recovery/isolation and frontend build. Review
  the complete scoped diff. Physical playback and full Demo acceptance remain open.
- The 64-identity defect is recorded only in this batch. Its lifecycle repair,
  other speech degradation, semantic cancel/adjust/A2 and artifact quality are
  excluded. Redeploy on the same ports, private configuration and registered
  project after checking live Task state; do not clean the user's project or push.

## Verification

Source under test: the product/test diff from the baseline in this document's
own commit. Checks ran locally on 2026-09-03/04; raw logs stay in private `logs/`.

Backend commands used `.venv/Scripts/python.exe -X utf8 -m pytest --no-cov -q
--tb=short --show-capture=no -o log_cli=false
tests/unit_tests/live_voice/test_product_composition_registry.py` with these
selections:

| `-k` selection | Observed result |
|---|---|
| `terminal_notification_claims_completion or terminal_notification_waits_for_activation or real_store_audio_resumes_nonzero or terminal_after_voice_playout_failure_replays` | 11 passed |
| `real_store_audio_resumes_nonzero or audio_playout_failure_falls_back_to_text_without_voice_consumption or text_progress_reaches_web_sink_and_preserves_generation_cleanup` | 6 passed; one overlaps the preceding run |
| `task_intent_flag_off_has_zero_authority_or_commit_effect or p3_mutation_flag_off_has_zero_composition_effect` | 2 passed |

These are 18 distinct tests, including exact Task names, unrelated current Task
isolation, result validation, running/terminal presentation across a fresh
Registry, replay, fallback and flag-off zero effects. The final running-name
assertion was checked in the second run.

Frontend commands ran in `jiuwenswarm/channels/web/frontend`, after bundling the
panel with local esbuild (`--bundle --platform=node --format=esm
--packages=external --loader:.css=empty
--outfile=node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs
--define:import.meta.env={}`).

- `node --test --test-name-pattern='terminal TEXT fallback|terminal.*fallback'
  tests/liveVoiceIntegratedRoutePanel.test.mjs`: 2 passed. Distinct Chinese and
  English names share backend wording/content hashes; replay retains identity and
  a foreign Task is rejected.
- `node --test --test-name-pattern='mounted Task AUDIO failure adopts server TEXT
  fallback|mounted nonterminal Task AUDIO ACK drains|mounted Task AUDIO failure retry
  clears' tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`: 2 passed, 1 failed.
  The fallback adoption test sees three progress ACKs where it expects two after
  a duplicate terminal. Rebuilding the panel from baseline HEAD and running the
  failing test reproduces the same `3 !== 2` assertion at line 5753. The current
  bundle was restored afterward. This existing failure is not repaired or waived.
- `node --test --test-name-pattern='actual Live Voice product entry selects'
  tests/liveVoiceIntegratedRoutePanel.test.mjs`: 1 failed on the source assertion
  `/onTaskRefresh=/`. Its target `src/components/ChatPanel/index.tsx` is identical
  to baseline HEAD; the removed manual-panel callback is absent in both. The
  existing stale assertion is recorded, not altered in this wording batch.
- `npm.cmd run build:live-voice`: passed (`tsc` and Vite). Existing duplicate
  locale-key, mixed import and bundle-size warnings remain.

Scoped self-review covered the complete diff: names are read from the existing
validated Task/status lookup and keyed by exact Task/scope/attempt, never inferred
from foreground selection or used to choose a mutation target. No travel, customer,
price, filename or fixed-answer policy was added. Existing event validity,
accepted suppression, timestamps, ACK and persistence logic are unchanged.
No complete suite, complete Demo, physical microphone or actual speaker playback
acceptance ran. The wider product remains PARTIAL.

## Deployment boundary

Deploy after the coherent local commit, using the existing formal-web launcher
on ports 6175/18092/19000/19001, Cascade with generation interruption enabled,
the same private data/configuration directory and the user's fixed registered
project. Verify no live Task/Attempt before restart. Do not clean project files,
change Provider/account settings or update a remote ref. The private
`logs/live_voice_runtime_contract.json` records the actual deployed source and
bounded probe results; this source evidence alone does not assert deployment.
Restart temporarily releases the cumulative capture budget; its defect remains
OPEN as recorded in [capture identity capacity](CAPTURE_IDENTITY_CAPACITY_20260903.md).
