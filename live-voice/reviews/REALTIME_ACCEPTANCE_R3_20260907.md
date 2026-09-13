# R3 finite local tail after a provider transport fault

Approved Tier 3 boundary: only the exact current Native playback owner may
freeze and drain the browser-accepted contiguous PCM prefix after an identified
Provider send/receive/timeout fault. The new closed media detach reason
`MEDIA_NATIVE_PROVIDER_TRANSPORT_FAILED` preserves this fact over both media
directions. Invalid scope, malformed PCM, device failures, explicit interruption
and unknown closure retain immediate fencing. No wire fields are added.

Owned surfaces: Python media reason/source/Gateway seam and product P1 playback
route. The audio worker owns the immutable exact freeze/seal handles, finite
render deadline, STOP cancellation and browser protocol enum. Main owns shared
semantics and integration. Known EOF seals the exact accepted manifest; unknown
EOF settles only an accepted prefix. Neither provider fault nor prefix settlement
can publish successful playback/history or reacquire an activation automatically.
STOP, close and successor begin revoke old local ownership before new playback.

## Implemented behavior

- Gateway retains only `REALTIME_TRANSPORT_SEND_FAILED`,
  `REALTIME_TRANSPORT_RECEIVE_FAILED`, and `REALTIME_PROVIDER_TIMEOUT` as the
  recognized transport cause. It records the cause before `session.closed` is
  visible and retains it after removing the Native session. Uplink transport
  preserves this one closed reason; other consumer failures remain generic.
- Provider failure aborts each exact Native source, clears its unsent queue and
  wakes its reader with a typed failure. It cannot turn an unknown EOF into a
  successful completion. An already observed finite source EOF remains a source
  fact, independently of the failed interaction.
- Product route checks exact activation/session/interaction and current Native
  response ownership, changes operation/status and fences normal append/ACK/
  presentation eligibility synchronously, then freezes accepted PCM. The freeze
  can synchronously schedule a short reserve, so the callback fence precedes it
  and the owner is checked again after it returns.
- Capture, media leaves and remote authority are closed promptly. Only the
  immutable local drain handle survives until actual render, STOP, close,
  deadline or device failure. Its result is diagnostic and never a business
  `media.playout_receipt`, chat projection or successful history commit. Even a
  previously sealed complete source cannot publish success after this fault.
- A mismatched stop cannot cancel the retained response. Exact STOP and close
  stop it immediately; late PCM and late onended cannot revive it. Capture
  restart on the same failed owner is rejected. Main verified the Panel's
  explicit retry/session-switch/exit first closes the old owner, then creates a
  new one; failure notifications themselves do not close the local tail.
- `frozenFaultTailResponse()` exposes only the immutable exact local response
  for the UI STOP control. Freeze publishes the retained owner; confirmed STOP
  and drain settlement publish its removal even if other cleanup is pending.
  Main owns the Panel/DemoBar binding and mounted integration for this seam.
- The caller rechecks operation ownership after the asynchronous final capture
  flush. The receipt method independently rechecks the exact pending/settling
  object, stop, close and failure fences synchronously before issuing its RPC.
  A fault queued before that continuation therefore cannot mint a successful
  render/history receipt even when every sample previously rendered.

## Verification (2026-09-07)

All verification used this isolated worker checkout, its own frontend cache and
`JIUWENSWARM_DATA_DIR=.repair-test-data`. No Provider/network/service/session or
real microphone action was used.

- Strict TypeScript compile for `productP1VoiceRoute.ts`, including unused
  local/parameter checks, passed with the fixed R6 audio snapshot.
- Full `productP1VoiceRoute.test.mjs`: **150 passed**, 0 failed/cancelled
  (67.76 seconds). Twelve new R3 cases cover 0/1/256 accepted frames (the maximum
  5.12-second local queue), fault over either media direction, stalled actual
  source completion despite all transport ACKs, frozen-cutoff late PCM/no ACK,
  wrong-response STOP, no implicit new activation, explicit STOP/close, verified
  EOF followed by fault, generic-close hard cut, and close re-entry from the
  first short-tail `source.start`. Every fault case asserts no successful media
  receipt/history/Agent/Task effects. The original 138 route cases remain green.
- Independent review identified the async-return receipt window. Its regression
  hooks the public media leaf's `flush`: after the original flush returns with
  zero pending ACKs, it queues an exact Provider-fault microtask before the
  awaiting playback caller resumes. With only the two receipt guards temporarily
  removed from the compiled test artifact, this test failed with **1 receipt**
  versus expected **0**; the artifact was restored exactly. With the guards,
  **17 focused tests passed**, including this zero-receipt case and positive
  short/streaming EOF receipts. The initial socket-buffer getter attempt did
  not isolate this window and is not counted as evidence.
- Full Python `test_native_response_downlink.py`,
  `test_browser_gateway_media_transport.py`, and
  `test_dedicated_media_registration.py`: **197 passed** (8.86 seconds).
  Ten new tests include a real fake-Engine task failure flowing through registry
  cleanup to the retained downlink source, an empty blocked source, queued PCM,
  already verified EOF, wrong response, exact-only consumer cause preservation,
  and held close-coroutine tests before/after session removal for all three
  recognized causes plus an unrecognized cause. Initial focused fixture mistakes
  (receiver method name and timeout token) were corrected; no production policy
  was broadened to satisfy them.
- Full `test_dedicated_live_voice_media_route.py`: **116 passed** (5.06 seconds).
- `git diff --check` and the pure R6 bridge patch reverse check passed.

Reproduce from the repository root with the original installed Python runtime:

```powershell
$env:PYTHONPATH=(Get-Location).Path
$env:JIUWENSWARM_DATA_DIR=Join-Path (Get-Location).Path '.repair-test-data'
& 'C:/Users/admin/Desktop/live voice hx/.venv/Scripts/python.exe' -m pytest --no-cov -o addopts='' -q tests/unit_tests/gateway/test_native_response_downlink.py tests/unit_tests/gateway/test_browser_gateway_media_transport.py tests/unit_tests/gateway/test_dedicated_media_registration.py tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py
```

Frontend uses the existing `test:live-voice-native-interaction` TypeScript
compile arguments and product route test entrypoint. The focused selection is
`node --test --test-name-pattern='provider fault|unknown media closure' tests/productP1VoiceRoute.test.mjs`.

## Dependencies, review and limits

Main's product integration found that the original UI STOP was gated on `playing`,
so it became a no-op after the fault changed status to `cleanup_pending`. The
local immutable `frozenFaultTailResponse()` seam now supplies the exact target;
its freeze/clear notifications drive an optional local surface flag. The voice
bar retains the genuine failure status and shows enabled STOP for this tail even
when remote availability is false. STOP needs no active P2 route, capture or new
RPC. Session reset clears the flag; retry and exit still close the exact old owner.
The flag changes neither the wire protocol nor business/history authority.

Main's mounted production Panel tests passed all four 256-frame (5.12 s) cases:
natural onended drain, local STOP, exit/close and explicit restart to a new capture.
They assert prompt capture and remote-media retirement, no initial source stop,
no late-frame extension, no stale-onended restart and zero business or successful
playout/presentation receipt effects. The production voice-bar adapter separately
passed enabled STOP during unavailable cleanup and removal after settlement;
the existing compact failure-details/retry test also passed. Its first fixture
selected the shared diagnostic-export CSS class and was corrected to the exact
STOP accessible label. Main's complete frontend `tsc --noEmit` passed.
Evidence: `logs/r3-mounted-tail-first.txt` (4/4), `logs/r3-bar-stop.txt` (2/2),
and `logs/r3-frontend-types.txt` in the integration worktree.

The audio worker independently reviewed Main's complete UI diff and actual
mounted logs: no remaining blocking finding. The final integrated Web script
includes all new cases: 706 tests / 681 passed / 24 baseline failures / 1 skipped.
The new local flag is the sole difference in one baseline failure's state dump;
the other 23 first errors are unchanged. Final Native/Gateway integration passed
757 checks. See the consolidated candidate record for exact evidence limits.

R3 depends on the exact immutable drain API in R6 worker commit
`9d46db79cea09d3987b27234b536c31d36702600` and the separate pure product EOF bridge.
Those four audio source files were copied only for verification and are excluded
from this R3 commit. The protocol adds one closed enum value and no fields or
authority. An older peer that rejects the new value still fences immediately.

Independent read-only review is assigned to `control_receipt_ultra`; its earlier
closed/cause and synchronous freeze-callback findings are implemented and tested.
The final review passed after inspecting the receipt guard, public-flush
counterfactual and restored 17/17 focused plus 150/150 complete route results;
all three findings are closed with no remaining worker-source findings.
Main owns mounted integration and real-device
acceptance; these offline checks establish bounded ownership/effects, not physical
speaker output quality or the original socket's external close cause.
