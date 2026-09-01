# W3 generation interruption / Native adaptation integration — 2026-09-02

Baseline: `hx/0812_live_voice_w3@fec2bbe2d3c6ed2c658dd7a1df6683cc3e4cafc5`.
Ordered sources: `c400188d442f12e11ae22dae3923ea841d0ad884`, then
`4b247ddbf36c25f277fccfdfaf0aea90518052ee`, from
`codex/live-voice-generation-interruption-realtime-adaptation`.
The first maps to `c7140ecd`; the second is the commit containing this record.
Both retain their source attribution with `cherry-pick -x`.

Current judgement remains in [STATUS](../STATUS.md). This is local integration
evidence, not independent Tier-3, new Provider/device/human or product acceptance.

## Scope and conflict resolution

The pre-implementation packet in STATUS owns Tier-3 P1/P2/Gateway/authenticated
P3 integration seams. Existing W3 Task controls, exact managed-worktree authority,
confirmation binding, terminal notification recovery and successful unary replay
must survive the imported generation-interruption and explicit opt-in Native path.
No new protocol/policy beyond the two imported commits, model upgrade, default
switch, private configuration change, deployment or remote operation is included.

- First transplant: resolve the Integrated Panel, mounted tests, STATUS and
  decision-log conflicts. Keep W3's visible canonical TEXT fallback and exact
  notification/media replay. Keep incoming speaker-first generation interruption;
  its only cancellation remains the exact foreground `round.cancel`.
- Compose capture settlement before Task playout. Start the existing Task audio
  deadline only after capture settlement, and suppress overlap capture for Task
  system audio. The incoming deferred-announcement resume path now uses the same
  W3 deadline, no-overlap flag and exact Registry `presentation.failed` fallback.
  Fence an Exit/new loop after its awaited capture settlement. Recovery retry
  also suppresses overlap capture. No new local Task result or acknowledgement
  authority is introduced.
- Keep both mounted carriers: W3's actual product progress DOM/ACK carrier and
  the imported interruption carrier. The latter's speaker-deferral tests must
  issue real `AUDIO` presentations; a W3 `TEXT` fallback is intentionally displayed
  and ACKed without TTS. Add resumed synthesis-failure and deadline regressions:
  one exact failure report, zero success ACK, zero Task cancel/mutation.
- Second transplant: resolve the Integrated Panel and P1 route conflicts by
  retaining both captured-notification cleanup and Native chat dedup cleanup.
  The overlap predicate is `downlink && !native && capture_during_playout !== false`:
  Native keeps its continuous uplink, while Cascade Task audio cannot start a
  self-capturing successor. The timeout helper accepts a settlement-only
  `Promise<unknown>` because Native playback can return a chat projection;
  ordinary presentation awaits completion without claiming a Native projection.
- Review the automatically merged Agent client, composition Registry and
  authenticated P3 seams against both sources. W3's completed-unary replay skips
  only the false cancellation tombstone; incomplete unary/stream quarantine,
  queue/token ownership, exact Task/Attempt checks and managed-baseline checks
  remain. Native privacy changes still remove full transport payload logging.
- Preserve W3's current reopened-terminal status and exact historical P3-9 PASS;
  do not import the older assertion that P3-9 has never passed. Native physical
  and review evidence remains bound to its named source hashes, not this tree.
- Preserve W3 Task-control D-098/D-099/D-100. Map the imported generation branch's
  colliding D-098/D-099/D-100 to D-104/D-105/D-106. Native D-101/D-102/D-103 remain
  distinct. Historical generation records retain their original text with an
  explicit mapping note; mutable references point to the canonical decisions.

OpenAI Docs was used only to cross-check the existing Native boundary: WebSocket
clients own stopping playback and reporting the actually played cursor through
`conversation.item.truncate`. No API/model/configuration upgrade was made. See
the [official Realtime conversation guide](https://developers.openai.com/api/docs/guides/realtime-conversations).

## Fresh-source verification

All frontend checks compile current source through their package scripts before
running tests. No old `.cache` bundle is credited. Python uses the existing local
`.venv`; provider/device tests below are controlled fixtures unless stated otherwise.

| Check | Result |
|---|---|
| First transplant: generation interruption, Batch Speech, composition Registry, dedicated-media registration and streaming route | 405 passed |
| Final composition: all 30 changed Python test files, including launcher, AgentServer, channel, Gateway and Live Voice | 1,568 passed; two dependency deprecation warnings |
| `npm run test:live-voice-integrated-web` | 547 passed, 5 pre-existing failures, 1 skipped; not a cumulative PASS |
| `npm run test:live-voice-native-interaction` | 111 passed |
| `npm run test:live-voice-gateway-batch-speech` | 32 passed |
| `npm run test:live-voice-browser-gateway-media` | 40 passed |
| `npm run test:live-voice-browser-audio-io` | 105 passed |
| `npm run test:live-voice-l0-measurement` / `test:live-voice-l0-ordinary-batch` | 5 / 5 passed |
| `npm run test:live-voice-build-profiles` | 2 passed |
| `npm run build:live-voice` | TypeScript and production Vite build passed after resolving the cross-commit playback return-type mismatch |
| Ruff `--select F` on all changed Python files | Three existing `app_gateway.py` findings only; identical findings reproduced by piping baseline `fec2bbe2` into Ruff |
| Conflict-marker, decision-ID, changed-link and `git diff --check` checks | Passed |

The backend file set is reproducible from the final integration commit with:

```powershell
$integrationTests = @(git diff fec2bbe2 HEAD --name-only -- tests/unit_tests scripts/live_voice/w2_rehearsal/tests | Where-Object { $_ -match '(^|/)test_[^/]+\.py$' })
& .\.venv\Scripts\python.exe -m pytest @integrationTests --no-cov -q
```

The five Integrated Web failures are the already recorded W3 mounted
notification/ACK diagnostic failures; both transplants preserve them as failures,
not skips or rewritten success assertions:

1. `mounted P3 origin panel reconciles and ACKs authoritative completed and failed progress`
2. `mounted stale Task TEXT replays after foreground ACK and presents before its only ACK`
3. `mounted terminal notification replays its exact P2 observation after Live Voice creates a media owner`
4. `mounted Exit retires a deferred stale Task AUDIO owner before same-Session successor capture`
5. `mounted foreground status query restarts an idle P2 poll after background terminal settlement`

Their earlier non-PASS status is recorded in [STATUS](../STATUS.md). This batch
does not claim that all five are harmless timing issues or that the current
notification boundary has passed; triage remains with that reopened owner. Ruff's
unchanged findings are unused `host`, unresolved annotation `RoutingTarget` and
unused exception `e`; no imported-module undefined/unused symbol was found.

## Matrix, review and limitations

- `P/S`: generation interruption/replacement, speaker deferral/resume, Native
  continuous capture/playout, Task admission/control and exact terminal replay.
- `N/B/F`: malformed/unauthorized Native carrier, bounded media/replay queues,
  default-off/explicit opt-in, injected resumed synthesis failure and playout
  deadline. Negative oracles retain zero Agent/Tool/Task/audio/history effects
  where forbidden; failed audio never counts as a presentation ACK.
- `T/C/R/I`: exact response/activation/Session/Attempt fencing, interrupted
  generations, stale/duplicate delivery, close/re-enable, lost-response retry,
  media-start replay and owner-specific cleanup. Both branches' oracles remain.
- `K/X`: affected Cascade/P3/frontend suites and the production Gateway receiver
  through real localhost WebSocket replay tests. Provider and browser audio
  fixtures are not real microphone/audibility or live-service evidence. No
  additional schema migration or external account/billing boundary was changed.

Cold self-review of the complete composition delta versus the two source lines
found and corrected the deferred-announcement recovery and playback-type seams
above. An independent local reviewer is unavailable in this execution; the
disclosed self-review substitute grants no independent Tier-3 PASS. Historical
reviews and physical results are not upgraded. The product remains PARTIAL
pending independent integration review, the existing five-failure triage and a
fresh authorized controlled-service/human journey. No deployment or push occurred;
machine-private configuration, data, logs, dependencies and build output are
excluded from commits.
