# P3-G0 controlled product-readiness attempt: 2026-08-19

## Conclusion

- Product source: `f24dd17d336c8266954f2d7299ca13bd0314d424`
  (`hx/0812_live_voice_w3`), parent
  `7a8ba7e82042e188efe6adbac98d47363b0d5d8e`.
- Candidate entry: the product worktree was clean, the checked-out source was
  exactly the product SHA above, and the branch was one commit ahead of and
  zero commits behind its configured upstream. No source changed during the
  automated, deployment or physical run.
- Acceptance result: **FAIL — NOT A CONTROLLED PRODUCT-READINESS CANDIDATE**.
  The first foreground microphone/Agent/TTS turn reached presentation ACK, but
  automatic listening then failed visibly with
  `AUDIO_CAPTURE_DURATION_EXCEEDED`. A user-initiated `重新监听` admitted one
  further real utterance and response, after which the same failure recurred.
- The complete Task create/adjust/status/result/terminal journey was stopped at
  that first positive-path failure. No P3-1 work, `develop` integration, remote
  update, source repair or candidate rewrite was performed.
- Privacy: credentials, authentication secrets, raw audio, full runtime identities,
  browser profile/device details and the private Task database remain outside
  Git. This record uses only redacted outcomes and a runtime-log basename.

## Final-diff review

`HEAD^..HEAD` contains 40 files with 5,673 insertions and 536 deletions. The
review covered the six recorded product-truth blockers, their follow-up
physical-test repairs, the explicit Live Voice build profile and the
production-default flag-off path. The diff contains the intended bounded
Executor deadline/settlement work, truthful Task admission/progress/result
projection, bounded Chinese update/status routing, reserved authoritative
result context, paired identity eviction, recovery correlation, P1 capture and
playout repairs, P2/P3 composition wiring and the named build profile.

The static complete-diff review found no actionable P1/P2 code-review finding
before deployment. The physical run then found the blocking P1 audio/runtime
defect recorded below, so that earlier static result does not grant acceptance.
`git diff --check HEAD^..HEAD` passed.

## Automated and build evidence

All candidate-credit commands below ran on the same clean product SHA. The
authoritative affected backend command was:

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov -q `
  tests/unit_tests/agentserver/test_live_voice_p3_route.py `
  tests/unit_tests/gateway/test_dedicated_media_registration.py `
  tests/unit_tests/gateway/test_streaming_speech_route.py `
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py `
  tests/unit_tests/live_voice/test_p3_authenticated_composition.py `
  tests/unit_tests/live_voice/test_persistent_task_core.py `
  tests/unit_tests/live_voice/test_product_composition_registry.py `
  tests/unit_tests/live_voice/test_product_observability_adapter.py `
  tests/unit_tests/live_voice/test_product_p3_text_adapter.py `
  tests/unit_tests/live_voice/test_project_code_executor.py `
  tests/unit_tests/live_voice/test_streaming_speech.py `
  tests/unit_tests/live_voice/test_task_progress_return.py `
  tests/unit_tests/live_voice/test_voice_task_bridge.py
```

Result: **916 passed, 2 skipped, 1 warning in 236.73 s**. The two skips are
Windows symlink cases; the applicable junction/reparse-point equivalents
passed.

| Check | Exact result |
|---|---|
| Supplemental broad backend diagnostic over `tests/unit_tests/live_voice`, affected Gateway and AgentServer suites | `1 failed, 1952 passed, 2 skipped, 1 warning in 382.21 s` |
| `npm run test:live-voice-integrated-web` | `407 tests`, `407 pass`, `0 fail`, `0 skipped`; about 25 s |
| `npm run test:live-voice-build-profiles` | `2/2` pass |
| `npm run build` | production/default build succeeded; 4,643 modules; 31.90 s |
| `npm run build:live-voice` | explicit Live Voice profile build succeeded; 4,643 modules; 30.60 s |
| `uv build` | built `jiuwenswarm-0.2.4b4.tar.gz` and `jiuwenswarm-0.2.4b4-py3-none-any.whl` |
| changed-Python Ruff with the inherited E402 excluded | all 20 changed Python files passed |
| focused Ruff format | all 18 module-owned files passed |
| `git diff --check HEAD^..HEAD` and worktree `git diff --check` | pass |

The supplemental broad diagnostic's single failure is outside candidate
credit: the retired S8 readiness helper calls Python's newer
`shutil.rmtree(..., onexc=...)` while this repository environment uses Python
3.11. The S8 helper and its test are byte-identical between the parent and
candidate, and D-071/D-072 keep that Gate retired. It was not hidden or counted
as a pass.

Raw Ruff reported one inherited `E402` at
`jiuwenswarm/server/agent_ws_server.py:251`; blame predates this candidate.
Raw `ruff format --check` reported that the same legacy server file and
`tests/unit_tests/agentserver/test_live_voice_p3_route.py` would reformat, with
18 other files already formatted. Both parent blobs also fail the same raw
format check. No mechanical source reformat was made during candidate
acceptance. The frontend emitted existing duplicate-locale-key and Vite
dynamic-import/chunk warnings; `uv build` emitted existing setuptools licence
deprecation warnings. The launcher's `npm install` summary reported 5 moderate
and 11 high dependency advisories; no audit-fix mutation or security-closure
claim was made.

## Clean-SHA deployment

The launcher was run from the candidate worktree:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\live_voice\start_hands_free_demo.ps1 -RestartExisting
```

It independently rechecked the branch, clean product SHA and registered clean
no-remote Demo project; kept the ordinary production build flag-off; rebuilt
the explicit Live Voice profile flag-on; and started the managed service whose
log basename is `swarm-20260819-143200.log`.

| Runtime fact | Verified outcome |
|---|---|
| frontend | port `6173`; actual asset `/assets/index-VcnrY85l.js`; Live Voice marker present |
| AgentServer | port `18092` ready |
| Web WebSocket | port `19000` ready |
| Gateway/media | port `19001` ready |
| P3 route | `[LiveVoiceP3] authenticated formal route ready` |
| composition | `[LiveVoiceProduct] central composition registered; p2=True p3_text=True` |

## Real microphone/TTS observations

The user enabled Live Voice in Chrome and supplied real microphone speech. The
first turn was a greeting; after the first failure the user clicked
`重新监听` and supplied a one-sentence Hangzhou-introduction request. Both
committed inputs reached the real JiuwenSwarm Agent and produced final text.

| Local time | Authoritative or visible fact |
|---|---|
| 14:53:07 | first microphone final committed |
| 14:53:16 | real Agent final became visible and entered TTS presentation |
| 14:53:44.542–14:53:44.661 | presentation ACK completed |
| 14:53:49.145 | streaming recognition fell back with `STREAMING_SPEECH_ROUTE_ABORTED`, visible `true` |
| 14:53:49.217–14:53:49.220 | speech transport cleanup timed out and cancel reported `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` |
| after 14:53:49 | UI showed recovery failure at activation with `AUDIO_CAPTURE_DURATION_EXCEEDED` and required `重新监听` |
| 14:54:23 | second real microphone final committed after the user's manual retry |
| 14:54:33 | real Agent returned a one-sentence Hangzhou description and entered TTS presentation |
| 14:54:49.878–14:54:49.973 | second presentation ACK completed |
| 14:55:05.137 | the same streaming-route abort recurred |
| 14:55:05.208–14:55:05.211 | the same cleanup timeout and unacknowledged cancel recurred |
| after 14:55:05 | UI again showed `AUDIO_CAPTURE_DURATION_EXCEEDED` plus `重新监听` |

Browser playout state and both presentation ACKs were observed; a separate
human audible-TTS confirmation was not obtained before the gate failed. The
second failure occurred about 31 seconds after the second Agent final, not
after a fresh 30-second post-TTS listening interval.

The candidate declares `PRODUCT_P1_CAPTURE_MAX_DURATION_MS = 30_000` and adds
overlap/idle capture rotation intended to keep long TTS from consuming that
bound. When the current media lease has observed provider speech-start, the
rotation deliberately fails closed with the same reason. The repeated physical
timing proves that manual retry is not durable continuation. Available service
logs do not distinguish whether the provider speech-start was caused by echo,
a late signal or another rotation race, so this record does not invent a more
specific root cause. Raising the limit may be considered in the repair packet,
but a threshold change alone has not been accepted or tested.

## Task, project and cleanup facts

The failure happened before `background.create`, so the Task journey was not
started. Read-only counts from the authoritative SQLite store were identical
before and after the attempt:

```text
attempts=17
commands=23
current_background_tasks=13
executor_events=45
live_voice_formal_project_adjustments_v1=3
live_voice_formal_project_attempts_v1=15
metadata=1
outbox=23
task_events=106
task_results=7
tasks=17
```

The disposable project remained on
`9ad8fc196eb4495b26e806dd3947b3f3f3b5aff8`, stayed clean and had no candidate
Task effect; the planned `itinerary.md` target remained absent. This proves zero
Task/file effect for the aborted attempt; it does
not substitute for the unexecuted positive Task journey.

At 14:58 the UI Exit action removed the Live Voice region and returned the
control to `开启 Live Voice`; the P2 close RPC completed. At 15:10 the managed
service PID was stopped with:

```powershell
.\.venv\Scripts\jiuwenswarm-stop.exe --timeout 15
```

Ports `6173`, `18092`, `19000` and `19001` then each had zero listeners. The
product worktree still matched the exact clean product SHA.

## Disposition

- P3-G0 is **not complete** and `f24dd17d` is **FAIL**, not
  `PASS — CONTROLLED PRODUCT-READINESS CANDIDATE`.
- The six source repair groups and explicit profile retain their automated
  evidence, but none receives complete candidate acceptance from this aborted
  journey.
- The next executable work is a bounded P3-G0 repair of the recurrent P1
  capture-duration/rotation and speech-cancel recovery seam, followed by all
  affected automation, build, clean deployment and the complete real Journey.
- P3-1 may not start until that rerun passes. No `develop` merge or push is
  authorized by this record.
