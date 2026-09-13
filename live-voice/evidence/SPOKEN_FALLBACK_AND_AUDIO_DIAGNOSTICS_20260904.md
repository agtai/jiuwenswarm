# Spoken fallback and audio diagnosis — 2026-09-04

## Scope recorded before implementation

Baseline: `e4dfab7ff40bdfe7f5dc490479863c58288fe6c0`.
User request: repair spoken-revision failure fallback, add diagnostics for the
roughly ten-second endpoint delay and ineffective playback-time voice interruption,
then redeploy the existing local rehearsal service.

- Agent Bridge / speech presentation (Tier 2): retain the existing bounded,
  tool-free revision and fact-check instructions. A revision timeout, invalid
  result, provider failure or unavailable revision model must not promote the
  unverified/overlong draft into the authoritative spoken final. Return a short,
  truthful localized failure notice, not a truncated factual conclusion. Do not
  retry Agent/tools, claim that a draft was saved/displayed, or swallow cancellation.
- Audio / Realtime Media / observability (Tier 2): add bounded content-free
  diagnostics at existing capture, upload/ACK, provider send, speech start/EOT,
  playback scheduling and interruption/cancel boundaries. Use existing identities,
  clocks, counters and energy observations. Energy is a diagnostic hint, never a
  replacement VAD or interruption authority. Diagnostic failures must not alter
  capture, media, Agent, Tool, Task, history or cancellation behavior.
- Owned surfaces: formal Agent adapter and its caller/tests; browser audio,
  dedicated-media and P1/interrupt owners and their focused tests; streaming
  recognition / media delivery logs and tests; scoped evidence and STATUS.
- Dependencies: existing formal Cascade, revision model, media authority, browser
  microphone/speaker and private deployment configuration. Keep the imported
  800 ms VAD / 250 ms startup settings; verify runtime rather than assuming Git
  changed running processes.
- Exclusions: sentence-level Agent-to-TTS pipeline; new VAD/classifier or barge-in
  policy; shared wire/schema changes; arithmetic algorithm changes; Task business
  semantics; saved credentials/provider settings; remote pushes; full-product PASS.

## Acceptance

Positive revision and skip paths remain valid. Timeout/invalid/tool-bearing
revision/provider failure cannot leak the original draft or dispatch extra work;
cancellation propagates. Diagnostics are bounded, correlate exact existing scopes,
contain no transcript, raw audio, credential, ticket or device ID, and remain
passive under throwing observers. Exercise affected positive, failure, stale,
cancel and cross-owner tests. Record independent-review limitations honestly.

Local deployment must preserve project/data/configuration and existing results,
check active work before restart, rebuild the served frontend, pass the controlled
launcher probes and record the actual new process/source. Microphone/speaker
acceptance and root causes unsupported by historical logs remain explicitly open.

## Results

Source repair and focused automated checks completed on the baseline plus this
batch. Controlled local deployment completed at approximately 13:08 local time
(Europe/Paris). This is not full-product or physical acceptance.

### Verification and limitations

- Backend: 336 passed, one existing Authlib deprecation warning. Command:
  `.venv\Scripts\python.exe -X utf8 -m pytest --no-cov -q --tb=short --show-capture=no -o log_cli=false`
  with `tests/unit_tests/gateway/test_audio_diagnostics.py`,
  `test_streaming_speech_route.py`, `test_dedicated_media_registration.py` in the
  same directory; `tests/unit_tests/live_voice/test_rehearsal_context_audio_repair.py`,
  `test_generation_time_interruption.py`, `test_agent_conversation_runtime.py` in
  that directory; and `tests/unit_tests/agentserver/test_formal_live_voice_adapter.py`.
- Frontend package: `npm run test:live-voice-audio-diagnostics` (2 passed),
  `npm run test:live-voice-browser-audio-io` (106 passed), and compiled
  `node --test tests/productP1VoiceRoute.test.mjs tests/liveVoiceBrowserDedicatedMediaRoute.test.mjs`
  (145 passed). Compilation uses the package's integrated-web TypeScript options
  and dedicated-media esbuild entrypoint. Whole-package `tsc --noEmit` passed;
  controlled deployment also passed `build:live-voice` (TypeScript and Vite).
- Selected UI regression: current and exact `e4dfab7ff40bdfe7f5dc490479863c58288fe6c0`
  baseline each run 37 tests, 32 passed and the same 5 failed. Selection:
  `node --test --test-name-pattern='barge|interrupt|stop|cancel|stale|foreign|generation'`
  over `tests/liveVoiceIntegratedRoutePanel.test.mjs` and
  `tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`. The baseline bundle
  substitutes the four changed UI/P1/browser modules from Git; current test
  bundle was restored afterward. Existing failures remain owned by Registry/UI:
  stale-disconnect natural Task barrier; same-Session foreign project/correlation
  create; P3 create/cancel A/B/C reconciliation; Exit stale Task AUDIO ownership;
  already-settled interruption retained answer. They are not silently waived or
  credited as PASS and this batch makes no Task semantics repair.
- Complete scoped diff manually reviewed, including new files. Independent
  `codex review --uncommitted` could not start due to unsupported `service_tier`
  configuration; a process-only `-c service_tier=fast` retry still failed with the
  old CLI's model/cache/state compatibility errors. No configuration/credential
  repair attempted. Manual review is not independent-review PASS; boundary
  remains PARTIAL for that missing proof.
- Scenario coverage: successful/skip revision; 14 reason-by-failure cases;
  cancellation propagation and no tool re-dispatch at the real adapter seam;
  metadata allowlisting, bounded retention/queue overflow, observer failure;
  current-owner capture/ACK, stale/cancel/replay/foreign-owner media and stop
  regression paths. No new durable state or shared protocol: Store migration
  and restart-durability dimensions are out of scope. Synthetic audio tests
  prove scheduling/cleanup, not what a human heard.

### What the old recording and logs do and do not establish

Private recording: `2026-09-04 11-58-43.mp4`; Session
`web_1a06bdb15e3_0c5859d4ffb7`; service log
`swarm-20260904-113145.log`. User marks speech ending at 17 s, listening until
roughly 26 s, ineffective spoken interruptions at 72 s and 80 s.

- Log wall clock 11:59:10.806 first reports server-VAD EOT. P2 activation follows
  at 11:59:11.741–11.755. The roughly ten-second listening wait therefore precedes
  Agent processing; these logs cannot separate delayed capture/upload/provider
  feeding from Provider/acoustic endpoint decisions. A 1.2 s silence setting
  alone is not evidence explaining a ten-second wait.
- Spoken revision reports `TimeoutError` at 11:59:42.793; downlink attaches at
  11:59:44.030. The old fallback promotes the draft after the failed revision.
  The repair removes that unsafe/overlong fallback, not all upstream waiting.
- No barge-in RPC appears at the two spoken interruption markers. The first
  gateway/Agent barge-in request is 12:00:09.436–09.466, corresponding to the later
  manual stop. Failure is upstream of that RPC; absence is not proof that the
  backend stop is broken, nor enough to blame a particular VAD/UI condition.

New trace discriminators (hypotheses until a fresh physical reproduction):

| Observation | Boundary to investigate |
|---|---|
| Large capture frame age / heartbeat tick delay | Microphone callback or browser scheduling starvation |
| Growing socket/pending/pre-open/provider queue; slow send completion | Upload/backpressure/provider-feed delay |
| Capture and send continue, local energy subsides, Provider stop/EOT arrives late | Provider/acoustic endpoint decision; energy does not prove human speech or silence |
| Energy during playout but no Provider speech-start | Capture/acoustics/provider detection; echo vs human still requires recording |
| Gateway speech-start ready but browser receipt missing | Control delivery |
| Browser receipt, blocked P1/UI gate | Current-owner/handler/presentation state |
| Stop requested, source cleanup failed or delayed | Local playout stop; physical residual sound still requires listening |
| Stop succeeds but RPC waits on presentation | Presentation settlement/ACK boundary |

Browser prefix is `live_voice_audio_diagnostic`; its memory-only ring holds the
latest 2048 records. Export before refresh/tab close with browser-console
`copy(JSON.stringify(window.__liveVoiceDiagnostics.snapshot(), null, 2))`.
Backend uses the same prefix, a 256-record nonblocking sink queue and reports
dropped records. Correlate with existing Chat/media/capture/response identities;
cross-process monotonic clocks are not interchangeable. RMS is only an energy
hint, send completion/ACK is not speech understanding, and scheduled/stopped
sources are not proof of physical audibility/silence. No PCM, transcript, ticket,
credential or audio-device identifier is added by these diagnostics.

### Actual local deployment

- Deployed code: `40c93893404f92b3e7dc53312cc7402af2e4481a`,
  `fix(live-voice): fail closed on spoken revision and trace audio boundaries`.
  Source worktree was clean at build and service startup. A subsequent evidence/
  STATUS-only commit does not change deployed runtime code.
- Existing managed service was stopped only after preflight and a read-only
  check found zero nonterminal Tasks. Existing project `proj_ad135a77`, its clean
  no-remote checkout, private data/config directories and two terminal Tasks /
  two terminal Attempts were preserved; no business Task was retried.
- Initial preflight found Speech settings absent from the isolated Agent config.
  The already-existing user-private Speech settings were supplied only in the
  launcher child environment. No credential file was copied, edited or printed.
- First restart attempt stopped the old managed process but Windows PowerShell
  lacked `Get-FileHash`. Rerunning the unchanged controlled launcher with the
  available PowerShell 7 completed. No business source workaround was added.
- Controlled launcher: `scripts/live_voice/start_hands_free_demo.ps1`,
  `formal-web-validation`, current source branch, explicit existing project,
  data/config paths and ports; `-RestartExisting -NoBrowser`, Cascade, unchanged
  generation-interruption flag off. Build-time startup lead explicitly 250 ms;
  server VAD explicitly 800 ms. No saved configuration update or browser launch.
- New root service PID 3692; listeners 6175→3712, 18194→1816 and
  19120/19121→4568. Service log `swarm-20260904-130715.log`.
  Runtime contract reports source `40c9389340`, zero dirty files, validated
  routes/bundle, Speech round trip passed and eligible Gateway claim policy.
- Actual HTTP page returned 200 and loaded `/assets/index-DsZyj0lX.js` containing
  the diagnostic accessor, capture progress, UI barge-in gate and build setting
  `VITE_LIVE_VOICE_PLAYOUT_STARTUP_LEAD_MS: "250"`. Read-only process checks found
  `LIVE_VOICE_SERVER_VAD_SILENCE_MS=800` in both Agent and Web/Gateway processes;
  this establishes configuration, not a physical endpoint latency result.
- Launcher exit 0: real TTS→STT, formal receipt, mismatched identity rejection,
  forged claim rejection and zero business side effects passed. Probe audio and
  transcript were not retained. Microphone/speaker, spoken revision with a real
  model, historical root-cause reproduction and latency gains remain unproved.
- `npm install` left tracked dependency files unchanged and reported 16 audit
  findings (5 moderate, 11 high); no dependency/security-policy upgrade was
  attempted. Build emitted existing large-chunk/mixed-import warnings.
- Reload the page to load the new bundle before reproduction; export the
  browser diagnostic ring before a subsequent refresh. Reproduce speech end,
  first heard audio and two spoken interruptions with video markers, then join
  that ring to the new service log. Neither HTTP/probe success nor a short
  sample alone establishes stable listening, interruption or physical sound.
