# Native recovery and presentation lifecycle repair

## Scope and acceptance

Baseline: `70aaa271a7f7896bc3a39b3f0ac2f7f69ac9021b`. The user requested diagnosis
of the 15:54–15:58 rehearsal, then explicitly directed root-cause repair without
hardcoded utterances, error suppression or timeout padding. Existing local Demo
redeployment authority applies after verification. Private incident evidence is
under `logs/native-incident-155432/` (current server log, browser export, Task
database facts). Preserve the registered project, model configuration and Task
state. No remote updates.

Intended behavior and owned boundaries:

- Native turns remain unique across recovery of an interaction. Generated and
  heard replies stay with their actual user turn, including late transcripts,
  delayed ACK, interrupted output and legacy histories with repeated counters.
- Generated text ends in an honest settled/interrupted state when its exact
  capture/activation closes. It never claims heard history or business success.
- Delayed delegate completion cannot fence an unrelated response whose media
  is still being delivered. Native foreground work and Task notification playback
  must share a consistent busy/settlement boundary. Bounded buffers and strict
  output fences remain; waiting must not hold locks needed by ACK/stop/close.
- The existing playback-stop contract is serialized identically over media and
  authenticated Web control. Invalid versions, fields and foreign cursors still
  reject with zero effects.
- Task notification display identifies a Task event independently of presentation
  retries or surface. Failed audio remains unacknowledged; recovery may retry only
  unconsumed voice. Text fallback and retry update one display entry, not append
  another copy. No invented voice ACK and no duplicate business command.
- Diagnostics identify the exact failed response, root reason and lifecycle
  boundary. Existing unrelated optional embedding/tool warnings are excluded.

Owners: Native Engine/Runtime and Gateway delivery, existing P2 notification
ownership, integrated Web chat/timeline/store, P1 stop serialization and passive
diagnostics. Tier 2 for lifecycle/concurrency/display; Tier 3 for existing control
and Task presentation identity seams. Any protocol/identity additions are confined
to these surfaces; no Task schema migration, new classifier or provider policy.

Verification: reproduce faults before fixes; affected Python and frontend module
checks, mounted integration and production build; real serialized stop boundary
and Native event/delivery integration. Apply P/N/B/S/T/C/R/I/F/K/X from TESTING.md,
with explicit zero forbidden Agent/Tool/Task/audio/history/scope effects on stale,
foreign and rejected paths. Cold scoped diff and independent boundary review at
closure. Real Provider/headset claims require their own evidence; automation alone
does not close physical acceptance. Deployment binds clean source, assets,
readiness and retained runtime state.

## Confirmed diagnosis

- R4's text reached the browser at 15:55:15.305; audio began 15:55:16.883 and
  canonical heard history was written at 15:55:28.335. Recovery reused
  `native-turn-00000001`; the frontend's `[interaction_id, turn_id]` join moved
  that answer below the later 15:55:58 question. Repeated turn 3 likewise moved
  interrupted R6 text below the 15:56:49 question.
  End of speech to first sound was 44.87 s; the real Agent occupied 38.12 s.
  This repair makes no latency improvement or SLO claim.
- R6 remained `generating` when delivery failed at 15:55:44.634 with
  `STALE_RESPONSE_OUTPUT`. Session closure then rejected microphone frames with
  `session_closed`, producing the generic UI uplink-consumer failure. R6 text was
  preserved across recovery without finalizing its state.
- The single travel Task terminal event is sequence 7. TTS R16 began at
  15:57:40.566; a pending Native delegate successor R17 then saturated its unconsumed
  downlink and failed at 15:57:47.926. Audio stopped with 11 scheduled frames left.
  Text fallback R18 and recovered audio R19 produced separate display identities.
  R19 began 15:57:53.905 and voice event consumption was recorded at 15:58:01.336.
  Both observed notification playbacks were TTS; this was not a Realtime echo.
- The 15:57:24 exact local stop succeeded, but Web RPC sent the internal control
  object without the wire `contract_version`, so strict decoding returned
  `MEDIA_MALFORMED_CONTROL`.
- Additional signals include one Task projection mismatch during an adjustment,
  recovery/old-route rejections, startup optional tool/embedding warnings and
  seven browser rebuffer events. These need classification, not a broad tuning
  exercise. The travel Task completed and the manager-note Task was cancelled.

## Follow-up scope checkpoint

Review exposed an existing Task TTS input gate that zeroed microphone PCM. The
owned P1/P2 lifecycle repair now retains actual continuous input, yields the exact
Task presentation on speech or a Native successor, and settles unplayed audio
without ACK, Task cancellation or uplink closure. Synthesis-in-flight and delayed
old settlement are included (Tier 2/3 existing audio/presentation seams).

The logged Task status projection race is included as a Tier 2 read-composition
repair inside the existing Registry owner: optimistic reads repeat only on an
observed monotonic event-head advance for the same authenticated scope/Task.
Same-version corruption or foreign identity still fails closed. No authority
relaxation, Task mutation, schema change or new policy is introduced. Read retries
are bounded; sustained advancement remains explicit STALE rather than fabricated
status. Pending history retains its metadata independently of bounded output
retention; chat and FileViewer share exact Task-event display coalescing.

## Verification and review

Design checkpoint: the existing Native delegate result seam becomes two-phase.
`prepared` retains the exact source response and canonical result; ordered SPEAK
with the retained Provider call identity allocates the successor. No response is
allocated merely because Agent work completed. Engine scheduling waits for exact
predecessor playback settlement and remains interruptible. Native pending work
and Task notification admission share a short Runtime admission lock, released
before Agent, network, TTS and presentation waits. This is the scoped Tier 3
control/concurrency repair; strict identity validation remains mandatory.

The module repair is verified. The regression that retired an admitted delegate
while its transcript was buffered initially failed; retirement now discards the
exact response's transcript together with audio/done, and the Engine module passes.
No timeout enlargement, utterance matching, synthetic ACK or model switch was used.

Private command outputs are retained under `logs/native-incident-155432/`:

| Owned checks | Result and evidence |
|---|---|
| Python Engine, Native Runtime, Gateway media, Agent Runtime, P2 adapter and Task notification ownership | The six-module run `final-backend.txt` passed 422 with the new buffered-transcript regression failing. After the fix, the complete Engine module passed 102 (`final-engine.txt`); the other 321 passed checks are unaffected. |
| Registry Native, Task notification and coherent status read | 31 passed, 204 deselected (`final-registry.txt`), with the three established baseline fixture failures excluded below. |
| Frontend Native/P1 | 133 passed (`final-native-frontend.txt`). |
| Integrated panel unit and affected mounted journeys | 68 and 21 passed (`final-panel-unit2.txt`, `final-mounted2.txt`), with the two established baseline cases excluded below. |
| Chat store, real history-to-timeline and Task event identity | 8, 17 and 1 passed (`final-store.txt`, `timeline5.txt`, `identity-check.txt`). |
| TypeScript and production build | `tsc -b` and `npm run build:live-voice` passed (`tsc8.txt`, `build-final.txt`). |

Python checks use `.venv/Scripts/python.exe -m pytest -o addopts=''`, an isolated
`JIUWENSWARM_DATA_DIR`, and an isolated `--basetemp`. The six modules are
`test_openai_realtime_native_engine`, `test_native_interaction_runtime`,
`test_agent_conversation_runtime`, `test_product_p2_interaction_adapter`,
`test_task_notification_ownership` under `tests/unit_tests/live_voice`, and
`tests/unit_tests/gateway/test_dedicated_media_registration.py`. Registry selection
is `(native or p3_status or task_notification) and not
native_available_result_uses_toolless_agent_delegate and not
native_background_delegate_clarifies_or_rejects_without_task_effect`.
Frontend checks use the package-owned compilation/bundling followed by Node tests;
the final mounted selection covers Native, Task AUDIO, presentation, interruption,
terminal notification and ACK cases, excluding the proven baseline Exit case.

Applicable scenario evidence:

- P/X: ordered reservation through Gateway/Registry and prepared-to-admitted Native
  output; mounted notification polling to actual P1 audio delivery and media ACK;
  serialized Web STOP through the strict decoder; canonical history to timeline.
- N/B/I: malformed proposal/control/version and foreign call/turn/response/scope/
  Task/attempt reject without Agent/Tool/Task/audio/history effects. Same-version
  projection corruption and invalid event heads do not qualify for read retry.
- S/T/C: pending Agent work keeps foreground ownership after preface ACK; actual
  playback settlement precedes successor admission. Late TTS success/failure and
  old Task failure RPC settlement cannot close input, unfreeze a new Native ACK or
  overwrite its UI. Retirement drains already-buffered output of the exact response.
- R/F/K: reconnect uses distinct turn identity; legacy repeated counters keep their
  original answer association. Closed display text settles without heard-history
  claims. Task preview/fallback/retry coalesces one exact event; missing legacy
  identity is not guessed. Text fallback stages during Native playback and drains
  once afterward. Pending history survives output eviction. Cascade paths remain
  outside the Native admission/transport branch; existing failures stay explicit.

Real-path checks ran against this worktree on the authorized host:

- Real synthetic Speech through real `gpt-realtime-2` and the actual Native Engine
  produced 5 text updates, 80 audio frames, final transcript and response completion
  in 11.422 s (`real-engine-output.json`). Runtime admission was a fixture; this is
  Provider/Engine evidence, not a physical microphone or business Task journey.
- Native Runtime through the real configured Agent and file tools completed six
  `read_file` calls, verified the expected result and unchanged input files in
  15.312 s. Interruption during a real file-tool call settled one cancellation in
  0.031 s with no audio/history effects (`real-agent-171250/result.json`). Provider
  input facts were synthetic; no Demo Task or project was modified.
- Initial sandbox network failures are retained separately; these successful
  authorized-host runs establish the real-path results above.

Independent read-only reviews covered scheduling/admission, audio/control/Task
status, and timeline/history. Findings were repaired and the affected checks rerun:
retained history metadata, Task identity coalescing in FileViewer, Native delivery
during Task playback, stale synthesis/settlement isolation, and exact same-attempt
monotonic status retry including the refreshed observation timestamp. Main reviewed
the scoped diff; `git diff --check` passed.

Five pre-existing tests remain excluded, with baseline evidence on `70aaa271`:

- Registry `test_native_available_result_uses_toolless_agent_delegate` and two
  `test_native_background_delegate_clarifies_or_rejects_without_task_effect` cases
  (`confirmation-required`, `task-unsupported`) have semantic fixtures defaulting
  to dialogue while expecting the retired lexical background route
  (`baseline-registry.txt`). No lexical routing was restored.
- Panel unit `actual Live Voice product entry selects the formal P1 owner while
  compatibility fallback remains flag-off only` expects old Task callback props
  already absent from the baseline entry component.
- Mounted `mounted Exit retires a deferred stale Task AUDIO owner before
  same-Session successor capture` fails in the baseline Cascade fixture with
  `FORMAL_P3_REQUEST_REJECTED` and no hands-free resume; reproduced using baseline
  panel and P1 source (`baseline-mounted.txt`).

These exclusions prevent a full-suite claim. Full physical headset, complete
A/B/A2 business acceptance and broad latency optimization remain open. Controlled
deployment must bind a clean commit, served bundle and live readiness; its private
`deployment-verification.json` and before/after Task/project fingerprints own the
actual deployment result rather than this pre-deployment review record.
