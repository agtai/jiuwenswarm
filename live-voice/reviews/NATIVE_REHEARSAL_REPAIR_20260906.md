# Native rehearsal integration repairs

## Accepted scope and implementation boundary

The user authorized all repairs in the diagnosed Native rehearsal and a local
redeployment. Baseline: `d3949f97a6df52470cc0095ec7e9312fb6c80efb`. Failed physical
evidence remains private under `logs/realtime-incident-web_1a07697cb7d_489bd2261dd0/`.
This packet supersedes the previous packet's unchanged transcript/ACK exclusion.

Intended behavior:

- A Native Agent delegate cannot monopolize the activation lock and prevent
  presentation/history acknowledgement or exact teardown. Admission, identity,
  expiry, close and late-result fences remain authoritative.
- Native playback remains interruptible after download has completed. Exact
  played-cursor delivery survives normal downlink completion through authenticated
  control; local stop never pretends that server acknowledgement occurred.
  Provider-confirmed speech remains the interruption authority. Native's bounded
  tentative-pause interval accounts for Provider confirmation delay, with false
  pause rollback and unchanged Cascade behavior.
- Generated Native assistant text appears independently of complete audio ACK;
  an interrupted reply remains visible and marked as interrupted. Generated text
  does not claim heard audio or accepted Task mutation. Late/foreign output cannot
  overwrite the replacement turn. Existing audio-history admission stays exact.
- Native Task discovery and terminal progress refresh the existing authenticated
  Task list. An empty list retains a usable refresh entry. No duplicate Task or
  cross-session/project projection is allowed.
- Current capture availability and a previous request's failure are separate.
  Retry restores input without replaying committed business requests; the old
  failure cannot permanently cover a successfully recovered microphone.
- Bounded diagnostics preserve stable reasons and Native phases, and distinguish
  text generation, first audio, played completion and recovery actions.

Owners: P2 activation/Conversation Runtime, Native Engine/Gateway media, browser
P1 playback, integrated Web Task/chat/recovery projection and existing diagnostics.
Risk: Tier 2 for lock, recovery, Task refresh and pause timing; Tier 3 for the
exact control/text projection seams and their cross-module identity guarantees.
Any narrow protocol addition belongs to these owners and this packet; no general
Task authority, classifier, model/configuration or performance policy is added.

Verification follows root [TESTING](../../TESTING.md): regressions reproducing the
ACK/delegate overlap, completed-download stop, interrupted text, mounted Native
Task discovery/recovery; relevant P/N/B/S/T/C/R/I/F/K/X dimensions with explicit
zero forbidden effects; affected backend/frontend checks and build, cold scoped
diff review and independent boundary review. Real-path evidence must include the
actual Agent/tools and Native control/presentation integration. Deployment checks
bind clean source, served bundle, processes, real Speech readiness and preserved
historical Task state. Physical headset acceptance is reported separately from
automation; no full product or latency/SLO claim follows from this repair alone.

Exclusions: unrelated historical failures, optional embedding/tool configuration,
new providers/models, broad performance optimization, new Task controls, remote
Git updates, and production release. Existing historical Task/result/ACK state
and registered project are preserved during local deployment.

## Evidence

The module repair passed scoped verification and independent read-only review on
2026-09-06. The repair commit identifies the tested source; local deployment
identity and its subsequent readiness result belong to the machine-private
`logs/live_voice_runtime_contract.json` and `logs/native-rehearsal-repair/`.

### Implementation and observable behavior

- P2 releases its activation operation lock before awaiting the admitted Native
  Agent round, and rechecks exact open identity before returning. Runtime retains
  cancellation authority. This removes the observed history-ACK/Agent lock wait.
- Completed Native downloads retain only bounded Provider cursor metadata until
  playback ACK, stop or teardown. `live_voice.media.playout_stop` carries the
  existing exact stop receipt over authenticated Web control. It validates the
  live activation, connection, origin, response and sent/received cursor before
  effects, then rechecks lifetime after asynchronous settlement. Exit retires
  stopping leaves; an old stop failure cannot close replacement input.
- Provider transcript deltas/done yield display snapshots only after exact
  Runtime SPEAK admission. The Gateway's separate read-only
  `live_voice.media.native_text` projection avoids audio backpressure and makes
  no Runtime/Agent/Tool/Task/history acknowledgement. Snapshots retain at most
  64 responses, 65,536 UTF-8 bytes per response; reads page at eight snapshots
  and 256 KiB. Browser polling is non-overlapping at 200 ms with exact identity
  and monotonic revision fences. Interrupted text freezes; exact heard history
  replaces its preview without a duplicate. Exact turn metadata orders a late
  user transcript before its answer and survives same-page history refresh.
- Generated/interrupted text is retained in the current page's session runtime,
  including same-page reconnect. A full page reload restores existing canonical
  heard history only. No durable generated-text store, browser persistence or
  change to the Agent's heard-history contract is introduced.
- Native task association refreshes the existing Task experience before voice
  discovery; terminal progress refreshes its current state. Empty recent-task UI
  exposes refresh. These are authenticated reads, without business resubmission.
- A failed response remains a distinct chat message; recovered capture or the
  listening action clears obsolete request failure presentation without replay.
  Native's verified-headset tentative pause waits up to 1,000 ms for Provider
  confirmation; Cascade retains 300 ms. Local pause still grants no semantic or
  Task authority, and false pauses remain reversible.

### Executed checks and review

| Boundary | Result and evidence under `logs/native-rehearsal-repair/` |
|---|---|
| P2 concurrency, Native Engine, Gateway media, diagnostics | 270 passed; four affected Python test files, `backend.txt`. Includes actual event-pump delivery, completed download stops at 24/48 kHz, and close while Provider stop settlement is pending. |
| Native browser route and existing P1 regressions | 128 passed; `npm run test:live-voice-native-interaction`, `frontend-native.txt`. Includes 400 ms Provider confirmation without playback revival and incoming frames while stop control waits. |
| Native text parser and classifier | 17 passed; `frontend-native-projection.txt`. |
| Mounted Native UI | 3 passed; scoped Native lifecycle/recovery variants, `frontend-mounted.txt`. Text becomes visible while the simulated AudioContext is playing, before full playout receipt; authenticated Task discovery and response-failure recovery are exercised. |
| Message store and timeline | 6 and 14 passed; `frontend-store.txt`, `frontend-timeline.txt`. Covers interrupted text, exact canonical replacement, duplicate suppression, retained failure and reconnect turn metadata. |
| Frontend typecheck and production build | `npm run build:live-voice` passed; `build.txt`. Existing duplicate localization key / large chunk warnings are outside this repair. |
| Real configured Agent and real file tools | `real-agent-network.txt`, `real-agent-152414/result.json`: six synthetic files read, expected total 135, completion 10.578 s; interrupted execution started one read and settled cancellation in 0.031 s. Files unchanged, audio/history effects zero. Provider facts were synthetic; this is real Runtime → Agent → file-tool evidence, not physical Native voice evidence. |
| Deployment preservation baseline | Read-only snapshot of 17 formal Task tables, 90 terminal Tasks, zero nonterminal Tasks and six project files; `state-before-deploy.json`. Compare after controlled restart. |

Earlier Agent probe attempts failed at network connection, with no successful
business evidence claimed. The successful network run followed the user's
explicit approval. Credentials and project contents are not in this packet.

The independent review found and closed event-pump omission, late-frame/stop
settlement, obsolete failure display, late user transcript ordering and reconnect
metadata issues. Main reviewed the complete scoped diff and reran affected
checks. The final close-during-stop regression also passes. No outstanding
module blocker was reported. Broader historical failures remain scoped in the
preceding Native foreground packet; this does not claim a full-suite pass.

### Applicable scenario matrix

| Dimension | Owned evidence / limit |
|---|---|
| P | Real Agent reads succeed; mounted Native text and Task list succeed; exact full ACK replaces generated display. |
| N / I | Foreign connection/origin/session/activation/provider response, malformed payload and unsent cursor reject with zero forbidden Agent/Tool/Task/audio/history effects. |
| B | Strict closed fields, UTF-8/control-character/response/revision bounds, empty text and 24/48 kHz cursor conversion are exercised. Bounded retention/paging is enforced in the read seam. |
| S / T | Interrupted and closed identities do not revive; delayed transcript, history replacement, duplicate ACK/projection and late downlink frames retain exact ownership. |
| C | ACK and close do not wait for an admitted Agent; stop/ACK share serialization, delayed Provider stop cannot acknowledge a retired session; browser local fence handles late transport frames. |
| R | Same-page reconnect keeps generated/failure rows and exact turn order. Listening recovery does not replay a committed request. Repeated retired stop fails closed; there is no automatic control retry or new replay ledger. |
| F / K | Native-only selection preserves existing Cascade timing and media paths; scoped P1 regressions pass. Diagnostics are bounded/passive and omit content. Existing durable Task/heard-history formats are unchanged. |
| X | Actual Engine event pump, Gateway/Runtime authority, mounted browser components and real configured Agent/file tools are exercised at their stated boundaries. Browser audio is simulated in automation; physical current-source microphone/speaker and complete A/B/A2 acceptance remain open. |

### Timing diagnosis and redeployment boundary

The failed rehearsal's end-of-turn → actual browser first audio was 53.296 s for
the initial project read (Agent about 45.48 s), 11.254 s for Task acknowledgement,
2.450 s for adjustment preface, 2.265 s for manager-note preface before interruption,
1.641 s for query preface (substantive answer 10.735 s), 2.148 s for the reply that
later failed ACK, and 6.483 s for the recovered query. These are distinct response
stages; preface timing is not substantive-answer latency.

Added diagnostics distinguish generated text/first visible text, response identity
and revision, exact stop acknowledgement/failure, listening actions and Runtime
presentation ACK elapsed time/original error. Existing Agent, first PCM and browser
first-audio diagnostics remain. The observed 300 ms rollback versus 367 ms Provider
confirmation explained revived playback; the history ACK waited behind the Agent
lock and exceeded the transport deadline. Optional embedding/tool warnings remain
configuration observations, outside this repair.

The real Agent synthetic test is not comparable to the travel rehearsal workload;
no latency improvement or SLO is claimed. A new physical rehearsal is needed for
response/first-audio comparison. Controlled restart uses clean source, NoBrowser,
the same registered project/data/configuration, `openai-realtime-native`,
`gpt-realtime-2`, configured GPT-5.6 Agent and verified-headset profile. Verify
served assets, all four ports, real Speech readiness and unchanged Task/project
hashes before handing the Demo back. Deployment does not clear retained
notifications or reset historical Task/result/ACK state.
