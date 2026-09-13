# L0 terminal-response barge-in repair evidence — 2026-08-24

## Source and boundary

- Behaviour source: `39932971f8e438b01f04fce656e6cbf8e66b261f` on
  `hx/0812_live_voice_w3`, clean and one local commit ahead of its upstream at
  launch. The later documentation-only amend changes no runtime or test source.
- Runtime: controlled `formal-web-validation` profile, fixed ports
  5173/18092/19000/19001, current Live Voice bundle and Product P2/P3 routes.
- Launcher probes: real Speech TTS→STT, critical receipt, identity-mismatch
  rejection and forged-claim rejection passed with zero business side effect.
- Browser: the operator used the existing ordinary installed Chrome Session
  `web_1a034feac64_9781824cb619`. The launcher used `-NoBrowser`; process review
  found no managed isolated Live Voice Chrome profile.
- Privacy: this record retains no transcript, raw audio, credential, device ID,
  private path or free-form error payload.

## Operator actions and authoritative results

After loading the repaired bundle, the operator completed the requested actions
in order: button interruption, voice interruption during playback, and playback
Stop followed by Exit. User-observed audible/visible completion is operator
truth; the table below is the independent server-log correlation.

| Action order | Stable action | Response generation | P2 request received | Wire result | Settlement |
|---|---|---:|---|---|---:|
| 1 — button interruption | `product-barge-1` | 17 | 22:13:47.668 | `e2a.complete` | 56 ms |
| 2 — voice interruption | `product-barge-2` | 18 | 22:14:02.099 | `e2a.complete` | 57 ms |
| 3 — Stop then Exit | `product-barge-3` | 19 | 22:14:11.866 | `e2a.complete` | 56 ms |

The three requests targeted three distinct response IDs. All carried the
contracted `cancel_response=true`; Runtime automation separately proves that a
terminal response suppresses response cancellation and emits only the exact
playback stop. There were three barge requests, three completions and zero barge
errors. No E2A unary error of any kind occurred from the first action through
the final Exit close. The close received at 22:14:12.503 returned
`e2a.complete` at 22:14:12.550.

## Residual diagnostics

This run does not hide adjacent log anomalies:

- two Speech socket cleanup timeouts occurred at 22:13:42.469 and 22:13:52.764;
- Exit produced one caller-cancelled socket cleanup-incomplete diagnostic and
  one `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` warning at 22:14:12.529–.530.

These diagnostics are in the separately excluded Speech Provider
transport-cleanup boundary. They did not turn any P2 barge or the final close
into an E2A error and receive no repair credit here.

## Disposition

**PASS — TERMINAL-RESPONSE BARGE REPAIR BOUNDARY.** The original nine-error
session remains an exact pre-repair record. This new evidence proves the repaired
ordinary-Chrome button/voice/Stop+Exit path and authoritative server settlement;
it does not supply explicit silence-rejection evidence, positive formal Task
credit, D-095 cold/warm samples, physical acoustic percentiles or Provider
transport-cleanup closure.
