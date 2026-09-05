# Formal generation-interruption default — 2026-09-05

Baseline: `e517bcac35b0bf3cafd4ddd07ce3d8e79776f36a`.
The user requested making generation interruption the default and redeploying
the local rehearsal environment.

## Scope and acceptance

Owner: controlled launcher/configuration; Tier 2 for feature selection and its
deployment boundary. Formal Web defaults generation interruption on; an explicit
disable turns it off even with an inherited environment flag. Existing explicit
enable remains supported. The hands-free profile remains off and rejects enable;
contradictory switches fail before setup or process mutation.

Owned files: controlled PowerShell launcher, its existing launcher regression
tests, current startup/showcase/status guidance and this evidence. Existing
runtime response fencing, Task authority, Speech/Media protocols and production
build defaults are unchanged. VAD silence 800 ms, startup lead 250 ms and the saved
headset profile are preserved. No new classifier, wire schema, migration, Provider
configuration or remote-ref update is authorized by this change.

Review scope clarification: the existing private L0 build-cache contract must
also bind the resolved generation flag. Missing, non-boolean or mismatched values
reject reuse and require rebuilding; no persisted Task/Speech protocol migration
is introduced. This remains the same Tier-2 feature-selection/build boundary.

Verification: real launcher argument/feature-selection regressions with an early
wrong-branch guard and unchanged service/contract records; affected build-profile
and generation-interruption tests; independent diff review; clean-source local
deployment through the controlled launcher and inspection of the runtime contract
and served assets. Preserve the existing project/data/Session and any Tasks;
inspect for nonterminal work before restart. No test result here grants physical
microphone/speaker or complete A/B/A2 acceptance.

## Results

- Red/green: the new real-CLI Formal-default case first failed against the old
  default (`false` instead of `true`); the cache case first failed because the
  production predicate was missing. Final launcher file: **12 passed** using
  `.venv/Scripts/python.exe -m pytest scripts/live_voice/w2_rehearsal/tests/test_portable_launchers.py --no-cov -q --disable-warnings --maxfail=1`.
  Tests cover profile/default/override/inherited environment, conflicting
  switches, wrong profile, cache boolean compatibility and early rejection.
  Early wrong-branch cases leave service and runtime-contract records unchanged.
- `npm run test:live-voice-build-profiles`: **3 passed**. Integrated-web package
  TypeScript/esbuild preparation passed. Selected mounted tests use
  `node --test --test-name-pattern='generation interruption|generation-time|in-flight interruption|unsettled interruption|already-settled interruption|stale voice-loop interruption' tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`:
  **12 passed, 1 existing failure**. The already-settled answer has
  `text_reason=null` instead of `PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER`; a separate
  single-case run reproduces it. The frontend and its tests are unchanged from
  baseline. This exact case and an earlier baseline reproduction are already in
  [the September 4 evidence](../evidence/SPOKEN_FALLBACK_AND_AUDIO_DIAGNOSTICS_20260904.md).
  It remains a Conversation Runtime/UI gap, not waived or credited as PASS.
  The failed reason assertion prevents the later `closures() === 0` assertion
  from executing; this run therefore does not prove zero forged ACKs for that
  case. Independent follow-up agreed this pre-existing gap does not block the
  bounded controlled deployment; it is not classified as merely wording.
- Ruff formatting/check and `git diff --check` passed. Independent read-only
  review by Halley first identified the L0 cache mismatch; final complete-diff
  re-review found no remaining actionable launcher/documentation issue. Main
  inspected the production predicate's use in both reuse and new-cache paths.
- Applicable launcher dimensions: positive/default and explicit override;
  negative/profile/conflict; boolean/cache bounds and compatibility; inherited
  environment isolation; feature-off; actual CLI/build integration. This change
  introduces no concurrent execution owner, Task lifecycle or persisted business
  protocol. Those broader dimensions remain with their existing owners and
  cannot be closed by these launcher tests.
- Before deployment, all **56 Tasks and 56 Attempts are terminal**; the Store
  contains 34 results and 35 event-consumption rows. Read-only hashes of Tasks,
  Attempts, results, consumption and selected private configuration were saved
  privately for a post-deployment preservation check. The four target ports were
  not listening. No frontend Session or completion notification was opened.

## Local deployment verification

- Deployed source: `5ac3ea29ca1d37fec7b6a4ab8c5b192c6947dd3a`, clean at build
  and after deployment. This later evidence update changes no runtime source.
  Preflight passed without an explicit enable switch. The first attempt through
  Windows PowerShell from a Python child failed to resolve `Get-FileHash` before
  build/service startup. The available PowerShell 7 ran the unchanged launcher
  successfully, matching the previously recorded machine-specific workaround.
- Successful command: `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/live_voice/start_hands_free_demo.ps1 -RuntimeProfile formal-web-validation -RestartExisting -NoBrowser`.
  No explicit generation switch, saved-configuration write or browser launch.
  Existing registered project/data/headset selection was reused. TypeScript/Vite
  `build:live-voice` and the controlled launcher exited zero. Four listeners are
  ready: frontend 5173, AgentServer 18092, WebSocket 19000 and Gateway 19001.
- Actual HTTP index serves `/assets/index-CpghO1Bj.js`; its bytes equal the local
  built asset, SHA-256
  `e90961407d26bf314d65e5a35ac1ba33add9aec41c81cefb6e09a7bcc2c87f72`.
  Inspection of compiled control flow confirms the generation-listening scheduler
  is active and the generation-interrupt handler is bound; the feature was not
  left behind a constant-off guard. The verified-headset local-pause path is
  also present. These static served-asset checks do not simulate microphone use.
- Runtime contract reports source `5ac3ea29ca`, zero dirty files, Formal/Cascade,
  generation interruption `true`, local pause `true`, profile
  `verified_headset_aec_v1`, validated bundle/routes and D2 v2 Executor. Real
  Provider TTS→STT passed; receipt policy is `eligible`, identity mismatch and
  forged claims are rejected, business effects are zero, and probe audio/text
  are not retained. This probe does not exercise physical generation interruption.
- Running AgentServer/Gateway/frontend process environments have no VAD-silence
  or startup-lead override. Source retains VAD silence 800 ms / threshold 0.5;
  the served bundle retains startup lead 250 ms. Post-deployment hashes of Tasks,
  Attempts, result rows, notification-consumption rows and the selected private
  configurations exactly match the pre-deployment snapshot. No notification was
  opened/acknowledged and no Task was created, cancelled or retried by this work.
- Private execution records remain under ignored `logs/`; no secrets, raw audio,
  transcript, private configuration or project output were committed. Existing
  tabs need a refresh and Cascade reactivation to load this bundle. Physical
  generation/playback interruption and the full A/B/A2 rehearsal remain open,
  including the existing already-settled boundary regression above.
