# D114 S6-02 cold EOT and long playout repair

> Frozen implementation and validation record for source commit `70dcc563` on
> 2026-08-13. Current milestone state and next actions remain authoritative in
> [STATUS.md](STATUS.md).

## 1. Packet and result

- Stage/node: `S6 - Alpha Module Closure` / `A1`.
- Task: `S6-02`.
- Track/modules: P1 AIO/SR/SS and Shared-X Web/Gateway composition.
- Risk: Tier 2 because the repair changes bounded recognition queues, streaming
  playout lifetime and the transport/render acknowledgement split.
- Base: `2e4cfeb0`; tested source: `70dcc563`.
- Scope: first-turn server-VAD recognition, long streaming TTS delivery,
  browser WebAudio scheduling, dedicated-media backpressure and affected tests.
- Exclusions: Provider/model/voice selection, credentials, microphone device
  choice, P2 semantics, Task authority, public deployment and production scope.
- Result: all three reported source failures are repaired and automated/runtime
  verified. `S6-02` remains `ENVIRONMENT` until a human confirms the real
  microphone short-EOT behavior, complete speaker output/quality and O6.

## 2. Measured causes

### 2a. A first short utterance stayed in listening

The first post-start Provider recognition connection was still opening when the
browser finished the short utterance. Dedicated media retained only 64 fixed
20 ms frames (1.28 seconds) before the Provider handle existed. The cold open
overflowed that queue, emitted `EOT_PROVIDER_FAILED` and exhausted the streaming
event route. A later, longer utterance happened after the Provider connection
was warm, so server VAD produced EOT and made the behavior look text-dependent.

The outer Provider open already allowed 15 seconds, but its pre-open queue and
the downstream Provider-send queue were both only 64 frames. In addition, the
native recognition session itself inherited the 15-second open timeout even
though the legal precommit and final-event windows extended beyond it.

### 2b. Long speech stopped at the same phrase

The repeated phrase was coincidental; the stop occurred at an exact time/frame
boundary. Product P1 rejected streaming frame sequence 1,500 and the Gateway
also bounded a downlink at 1,500 20 ms frames, which is exactly 30 seconds.
Separately, Product P1 started the next microphone capture during playout. That
capture has its own correct 30-second bound and could therefore cancel a long
answer even if the TTS stream itself remained healthy.

### 2c. Provider WAV was clean but browser speech sounded broken

The Provider PCM was not the faulty artifact. The browser acknowledged each
20 ms media frame only after its `AudioBufferSourceNode` finished rendering.
Because the Gateway sender owns an eight-frame ACK window, this coupled every
successive frame burst to browser-render time plus a network round trip. Gaps in
delivery were exposed as clicks, tearing or electrical-sounding speech. The
first Provider TTS chunk could also be followed by a measured seed-to-burst gap
longer than the former browser scheduling lead.

## 3. Repair boundary

The source now enforces these independent contracts:

1. Cold recognition pre-open and Provider-send queues retain 800 20 ms frames,
   covering the bounded 15-second open plus one second of scheduling margin.
2. The native recognition session budget covers open, legal precommit and final
   windows (70 seconds), while the outer connection-open call remains separately
   bounded at 15 seconds.
3. Streaming playout is independently bounded at 9,000 frames / 180 seconds;
   the 30-second limit remains only the microphone capture limit.
4. Replies estimated above 20 seconds defer successor microphone capture until
   the complete rendered answer finishes. Short replies retain duplex overlap.
5. A media ACK now means the exact frame is safely scheduled in WebAudio and may
   release transport backpressure. The separate `media.playout_receipt` still
   requires actual contiguous render completion, so product truth was not
   weakened into a scheduling claim.
6. Browser playout starts with a one-second scheduling lead, keeping ordered
   20 ms sources contiguous across the Provider's initial seed-to-burst gap.

No raw audio is persisted by these changes. Capture, media authority, response
identity, render receipt and forbidden Agent/Tool/Task/history/Store effects
remain under their existing exact bindings and fail-closed behavior.

## 4. Regression and review

The added regressions distinguish the old failures:

| Scenario | Result on repaired source |
|---|---|
| Cold Provider open with 100 early frames followed by provider-time speech-started/stopped | PASS; every frame preserved, one EOT, zero Provider cancel |
| Provider recognition timeout budget versus open/precommit/final windows | PASS; native session budget is larger than the outer open bound |
| True eight-frame downlink ACK window | PASS; sender advances only from scheduled-frame ACKs |
| Streaming downlink with 1,501 frames | PASS; all frames render and one exact receipt is sent |
| Long answer with successor capture | PASS; capture starts only after final downlink ACK/render settlement |
| Browser source schedule | PASS; sources start at 1.00 s and 1.02 s, contiguously |
| Early/foreign/malformed media, receipt and business effects | Existing negative suites remain PASS |

### 4a. Counterfactual red/green proof

On 2026-08-13 the new regression files were copied, without the repaired
implementation, into a disposable detached worktree at base `2e4cfeb0`. The
same selected tests were then run against the repaired implementation. This
checks whether the tests can actually distinguish the reported defects from
the fix instead of merely recording a green result after the change.

| Executable observation | Base `2e4cfeb0` with new test | Repaired implementation |
|---|---|---|
| Cold open retains 100 early frames through Provider VAD EOT | FAIL: accepted 100 frames but retained `0`; expected `100` | PASS: `1 passed` |
| Long answer defers successor capture until final downlink settlement | FAIL: timed out after 10,000 ms waiting for final downlink ACK | PASS: 91.9 ms |
| Streaming answer renders 1,501 frames beyond the former ceiling | FAIL: timed out after 10,000 ms waiting for final downlink ACK | PASS: 162.9 ms |
| Browser playout starts with the declared scheduling lead | FAIL: actual starts `[10.00, 10.02]`; expected `[11.00, 11.02]` | PASS in the 102-test browser audio suite |
| Scheduled-frame ACK and rendered receipt remain separate | PASS | PASS |

The last row is a negative control: the counterfactual setup did not make every
new test fail indiscriminately. It isolated the missing cold-frame retention,
long-playout lifetime and browser scheduling lead while preserving the already
valid receipt semantics. Both disposable proof directories were removed after
the run; the main worktree remained clean before this record update.

A complete cold self-review covered the scoped diff, queue/lifetime alignment,
transport-versus-render semantics, long-answer capture ordering and forbidden
effects. No independent reviewer was invoked because this execution did not
have delegation authorization. The substitute was the cold review plus focused
backend/frontend suites, a production build, real HTTPS/WSS probes and Computer
Use activation. This limitation is recorded rather than represented as an
independent Tier 2 review; phase closure still owes its required independent
review under D-074.

## 5. Automated and runtime verification

- Backend streaming recognition, dedicated media, Batch Speech and OpenAI
  streaming suites: `210 passed`.
- Frontend Integrated Web suite: `317 passed`.
- Frontend browser audio suite: `102 passed`.
- Frontend Gateway Speech suite: `29 passed`.
- Ruff on affected Python files and `git diff --check`: PASS.
- Production frontend build with Integrated Web, P1 and P3 mutation enabled:
  PASS; the deployed bundle contains the formal P1 label and 9,000-frame bound.
- B-environment runtime probe: HTTPS 200 with trusted certificate, WSS control,
  project list, session creation, Agent send/final and control plane all PASS.
- B-environment media probe: formal P2 activation, media ticket, fixed media
  path, memory-only privacy, WSS subprotocol/first-frame auth, attach/detach and
  authority close all PASS.

Computer Use selected `live-voice-alpha-fixture`, created a post-restart Agent
session, observed P2 `formal`, opened Live Voice, observed
`P1 · Gateway Speech · formal`, and caused a real
`/ws/live-voice/media` connection. The automation host supplied no continuing
microphone frames, so the route correctly failed closed with
`AUDIO_INPUT_GAP_EXCEEDED` and returned to `Start speaking`. This proves the
page, project binding, activation and media-entry path, but it is not a claim
that a human utterance was recognized or that speaker output was heard.

The first rebuild accidentally omitted the three required Vite feature flags
and truthfully exposed only Browser Speech fallback. It was discarded, rebuilt
with the declared flags, and all services were restarted. A separate false
`unsupported` observation was traced to a global New task bound to
`default_code` with an empty project directory; choosing the registered project
in the input-area selector produced the formal route. These were deployment
diagnostics, not evidence against the repaired source.

## 6. Remaining physical acceptance

The prepared Chrome task is stopped at `Start speaking`. Human verification is:

1. As the first voice turn after a service restart, say only “你好”, do not click
   Stop, and confirm server VAD automatically ends listening and recognizes it.
2. Speak the supplied three-paragraph prompt, again allow automatic EOT, and
   confirm playback continues past “通常是十六千赫或者更高”, reaches the final
   text, and has no tearing, clicking, electrical sound or unintended voice
   change.
3. Run O6 hidden/background/resume from the physical observation runbook.

Until those observations pass, no heard-playout or completed physical S6-02
claim is made. No remote ref was updated. Credentials, provider configuration,
browser profile, raw audio and private runtime artifacts remain outside Git.
