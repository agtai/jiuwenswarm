# P3-9 final independent Tier-3 review — 2026-09-02

## Decision

**Critical 0 / Important 0 — Assessment: Ready.**

The bounded controlled product-readiness candidate passes on exact product
source `83fde562284e96df12f2e2546797c4703a75132b`. The review was run in a
separate Session after the 8+2 human Gate. It reviewed the twelve-commit product
overlay `aa9d92d42d90a0aaa105328a140c436436ca4b9b..83fde562284e96df12f2e2546797c4703a75132b`
and the docs-only closeout
`83fde562284e96df12f2e2546797c4703a75132b..cfd90bdf9ece9ed4f1bfe22cde69568938685685`.

No product, test or evidence repair was required. The accepted human source and
route therefore did not change, and no additional human revalidation was
triggered. The immutable [human evidence](../evidence/P3_9_CUMULATIVE_PRODUCT_ACCEPTANCE_20260902.md)
continues to own the physical observations.

## Scope and Tier-3 coverage

The review inspected the changed production, test and documentation boundaries:

- canonical Gateway progress envelopes, exact scope/correlation/subject/
  causation parsing and DOM-bound presentation ACK;
- P2 notification subscription, exact replay and activation-generation fencing;
- Task AUDIO capture arbitration, finite playout settlement, requeue and
  post-ACK fresh listening;
- Registry terminal owner-loss retention, deferred presentation drain,
  bounded capacity/reconnect retry and text/audio class isolation;
- distinct accepted/running/terminal/result projection through the production
  Task bar and ChatPanel carrier;
- human evidence, controlled-candidate acceptance and strict non-claims.

The applicable D-032 dimensions were covered as follows: positive lifecycle and
the real 8+2 journey (`P/S/I`); malformed/wrong-scope envelopes, incomplete
presentation binding and zero protected effect (`N/F/X`); sequence, watermark,
capacity and finite timeout boundaries (`B/T`); current/stale owner rotation,
foreground-versus-Task arbitration and capture contention (`C/K`); and exact
notification, terminal and ACK replay (`R`). ACK or delivery was never credited
as Task completion, and wrong-task/stale paths retain zero Task mutation.

One apparent mismatch was investigated rather than reported: an old terminal
announcement retry body omits the newer `capture_during_playout` argument.
Exhaustive branch tracing showed that current Task presentation surfaces are the
closed `text | audio` union: Task TEXT returns through visible ACK before TTS,
while Task AUDIO failure or missing ownership settles through the server TEXT
fallback. The old retry body is unreachable under the current contract. An
experimental mounted fixture also failed at its obsolete TEXT-to-TTS
precondition before the proposed assertion. The hypothesis was rejected and all
test edits were restored; normalized file and HEAD blob hashes matched.

## Fresh verification

All valid Gate commands ran from the exact candidate worktree.

```text
npx tsc src/features/live-voice/formal/integratedWebRouteShell.ts src/features/live-voice/formal/browserLiveVoiceOwnership.ts src/features/live-voice/formal/productTextProgress.ts src/features/live-voice/formal/productWebActivation.ts src/features/live-voice/formal/productP2ActivationJournal.ts src/features/live-voice/formal/productP3TaskTargetJournal.ts src/features/live-voice/formal/productP3ProgressGenerationJournal.ts src/features/live-voice/formal/productP1VoiceRoute.ts src/features/live-voice/formal/formalTaskControlLeaf.ts src/features/live-voice/formal/formalTaskIntentRoute.ts src/features/live-voice/formal/formalTaskResultRoute.ts src/features/live-voice/formal/formalP3TaskExperience.ts src/features/live-voice/formal/unifiedCommittedInputOwner.ts src/features/live-voice/formal/webPlatformDiagnostics.ts --target ES2020 --module ES2020 --moduleResolution Bundler --rootDir src --outDir node_modules/.cache/live-voice-integrated-web --lib ES2020,DOM --skipLibCheck --noEmitOnError --strict --noUnusedLocals --noUnusedParameters
# exit 0

.\node_modules\.bin\esbuild.cmd src/features/live-voice/formal/adapters/browserDedicatedMediaRoute.ts --bundle --platform=node --format=esm --outfile=node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs
.\node_modules\.bin\esbuild.cmd src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx --bundle --platform=node --format=esm --packages=external --loader:.css=empty --outfile=node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs --define:import.meta.env={}
# both exit 0

node --test tests/liveVoiceIntegratedRoutePanel.test.mjs
# exit 0; 65 passed, 0 failed

node --test --test-name-pattern="accepts the complete canonical v2 envelopes emitted through the Gateway|formal P1 Task announcement playout suppresses self-capturing overlap before a fresh resume|mounted nonterminal Task AUDIO ACK drains one follow-up then resumes listening|mounted Task AUDIO failure adopts server TEXT fallback through visible running and terminal ACKs|mounted production task adapter renders distinct lifecycle states and terminal outcomes" tests/productTextProgress.test.mjs tests/productP1VoiceRoute.test.mjs tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
# exit 0; 5 passed, 0 failed

.\.venv\Scripts\python.exe -m pytest --no-cov -q tests/integration/live_voice/test_d90_formal_task_vertical.py::test_s6_joint_slow_conversation_detached_task_and_exact_cancel_domains tests/unit_tests/channel/test_web_channel_symphony_status.py::test_web_channel_preserves_live_voice_task_progress_delivery_binding tests/unit_tests/live_voice/test_product_composition_registry.py::test_unified_create_ack_releases_accepted_then_running_progress tests/unit_tests/live_voice/test_product_composition_registry.py::test_terminal_after_voice_playout_failure_replays_on_successor_p2 tests/unit_tests/live_voice/test_product_composition_registry.py::test_agent_ack_drains_deferred_voice_task_presentation tests/unit_tests/live_voice/test_product_composition_registry.py::test_later_audio_failure_replays_the_class_isolated_text_prefix
# exit 0; 13 passed

npm run build:live-voice
# exit 0; TypeScript and Vite production build passed, 4651 modules transformed
```

The focused frontend cache was rebuilt with the same repository esbuild inputs
before Node tests. Esbuild reported the existing duplicate `empty` locale keys;
both duplicates are present on comparison source `aa9d92d4`. The production
build also reported existing chunk-size and mixed static/dynamic-import
warnings. None is introduced by the P3-9 overlay or blocks this bounded Gate.

Final repository checks:

```text
git status --short --branch
# clean hx/0812_live_voice_w3 tracking origin/hx/0812_live_voice_w3

git rev-parse HEAD
# cfd90bdf9ece9ed4f1bfe22cde69568938685685 before this review closeout

git rev-list --left-right --count 'HEAD...@{u}'
# 0  0 before this review closeout

git diff --check
git diff --exit-code
git diff --cached --exit-code
# all exit 0 before documentation synchronization
```

The broad 499-case frontend diagnostic was not rerun. Its disclosed
`493 passed / 5 failed / 1 skipped` result remains an accepted deviation: the
five mounted timing failures are outside this repair overlay, and the human
evidence records a representative comparison-source reproduction. They are not
counted as passes or hidden by the focused result.

## Result boundary

This review closes P3-9 and the controlled product-readiness candidate only.
It does not trigger `develop` integration and does not claim feature complete,
Productized, RC or Production readiness. Generation-time interruption,
fixed-corpus latency/generalization, long Provider degradation, D1, production
authentication/tenancy/deployment/SLOs and broader platform evidence remain
outside this Gate, as defined by [STATUS](../STATUS.md) and the
[acceptance contract](../validation/PRODUCT_READINESS_ACCEPTANCE.md).
