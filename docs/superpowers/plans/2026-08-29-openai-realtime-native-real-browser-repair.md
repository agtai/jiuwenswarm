# OpenAI Realtime Native Real-Browser Repair Plan

**Goal:** Repair the real ordinary-Chrome failures reproduced on
`f0cdc30b69bc31da8468da8da6abedcb4db7a520` so an explicitly selected
`openai-realtime-native` interaction using `gpt-realtime-2.1-mini` sustains
continuous foreground speech-to-speech, produces an authoritative first-audio
measurement, supports barge-in, and can recover on the same page without
reusing a closed Runtime.

**Capability/module:** Audio Device & browser I/O, Realtime Media,
Conversation Runtime lifecycle, Integrated Web product experience, and the
existing content-free L0 measurement seam.

**Risk:** Tier 3. The repair changes browser media-consumption/backpressure and
response/generation lifecycle recovery at an existing authority boundary. The
ordinary-Chrome long-answer reproduction additionally proved that one 20 ms
audio proposal per Gateway-to-AgentServer E2A request cannot keep pace with the
Provider. After bounded E2A batching was enabled, direct Runtime admission of a
16-frame batch took about 1.2 ms, but Browser delivery remained intentionally
paced by actual playout at roughly 27--37 frames/second while the Provider
burst more than 512 frames in about 1.1 seconds. The 512-event reservoir
therefore filled before the measured barge stimulus could issue STOP. The
packet is explicitly re-scoped, still at Tier 3, to extend the existing private
`live_voice.internal.native.propose` method with one bounded audio-only batch
shape and to enlarge the Realtime-only in-memory Provider delivery reservoir
to 4096 20 ms frames (81.92 seconds of mono PCM16). STOP continues to bypass
that reservoir and fence queued stale audio. These are internal transport
changes at the existing authority; they create no new product authority or
public protocol.

## Reproduced facts and intended behaviour

- Real Realtime input, `TURN_COMMIT`, `SPEAK`, and Provider audio generation
  succeeded twice, but Browser downlink consumption collapsed to
  `MEDIA_CONSUMER_FAILED`; the Gateway later timed out its eight-frame bounded
  response source as `MEDIA_NATIVE_STREAM_BACKPRESSURE_TIMEOUT`.
- The existing 150-frame Browser test sends the next frame only after each ACK.
  Production may legally deliver an initial bounded burst, so Browser playout
  must consume and ACK that burst without loss, reorder, duplicate scheduling,
  or premature presentation truth.
- A media consumer exception must retain a bounded, content-free reason at the
  product diagnostic seam; raw audio, prompt, transcript, device identity, and
  exception text remain prohibited.
- After a terminal Native media failure, a same-page retry must allocate a new
  activation generation/Runtime/session or truthfully remain unavailable. It
  must never submit a new activation against the closed prior Runtime.
- OpenAI documents `response.output_audio_transcript.done` as also emitted for
  interrupted, incomplete, and cancelled responses. A blank/whitespace-only
  transcript on that event is therefore retained as no transcript and creates
  no history text; bounded nonblank text is edge-trimmed before admission,
  while wrong types, forbidden controls, and oversized text still fail closed.
- The real long-answer event contained an internal `U+000A` line feed. The
  existing Native audit contract correctly rejects every control character,
  including LF, so the Engine keeps that contract strict and canonicalizes
  Provider CRLF/CR/LF paragraph separators to ordinary spaces only when forming
  the outbound audit transcript. Every other `Cc`, all `Cf`, `Zl`, and `Zp`
  characters still fail before history text can be retained. This is a Tier-3
  correction of the existing transcript boundary, not a new history schema or
  product policy.
- A clean single-tab run then returned the exact Provider code
  `conversation_already_has_active_response`. OpenAI explicitly documents that
  `create_response=true` with `interrupt_response=false` may fail while the
  model is already responding. Provider auto-interruption must remain disabled
  so Runtime STOP and the exact played-audio truncation cursor keep authority.
  Native therefore disables VAD auto-create and sends exactly one
  `response.create` for each committed direct turn itself; if a locally
  cancelled prior response has not produced its terminal `response.done`, the
  request remains as one bounded pending turn and is emitted only after that
  terminal event. This is still the existing direct-response path and creates
  no new RPC, schema, classifier, or Agent/Tool/Task authority.
- The next ordinary-Chrome barge run proved that one Provider response may
  legally advance from an audio item at `output_index=0` to a different audio
  item at `output_index=1`. The current response state incorrectly treats that
  transition as an identity replay conflict and closes the Native route. The
  existing response boundary must retain each bounded audio-item identity and
  its per-item received cursor, keep response-wide delivery sequence ordering,
  and permit only strictly increasing output-item transitions. Barge
  cancellation must validate and truncate the exact presented item rather than
  whichever later item the Provider most recently emitted. Duplicate,
  regressing, changed-replay, or cross-response identities remain fail closed.
  This is a Tier-3 correction of the existing Realtime output mapping; it adds
  no method, schema, classifier, or Agent/Tool/Task authority.
- A later clean run refined that fact: `output_index=1` may begin before the
  `response.output_audio.done` event for `output_index=0`. Provider audio-item
  streams may therefore interleave. Each retained item needs its own bounded
  partial-frame buffer and completion state, while emitted Runtime sequence is
  still the exact event-arrival order across the response. A newly observed
  output index must advance, but an already registered earlier item may
  continue until its own done event; an item-local delta after that done still
  fails closed.
- After seven successful real barge rounds, the session reached the Runtime's
  4096-entry audio replay ledger even though earlier responses were already
  terminal or cancelled. That ledger currently retains every 20 ms frame for
  the lifetime of a continuous activation, so its nominal bound is also an
  unintended 81.92-second session limit. Runtime must retire frame-level replay
  records only when a prior response is terminal/cancelled and a successor is
  admitted, while preserving cumulative diagnostics and all current-response
  exact replay, sequence, presentation, history, and barge authority. The same
  Runtime boundary receives no Provider output index in the existing contract,
  so it must accept the Engine's bounded registered item identities in their
  exact interleaved frame sequence and validate a barge cursor against the
  selected item's own received duration. Index creation/regression remains
  enforced at the Engine boundary that actually receives `output_index`. This
  is bounded working-set compaction for the
  existing continuous foreground interaction, not persistence or a new
  history/Task policy.
- After Runtime compaction crossed that limit, a later real round reached the
  separate Session transport replay ledger's 4096 retained Provider events.
  This ledger is not the Provider delivery reservoir and every returned event
  is also fenced by the Engine's processed-event identity before any Native
  mapping. Session therefore keeps an LRU working set of exact canonical event
  bodies: recent identical replay remains idempotent, recent changed replay
  remains a conflict, and the oldest already-returned transport record is
  evicted before a new identity is retained. Eviction cannot authorize a stale
  effect because the Engine still drops every previously processed event id.
  The retained count remains fixed and content-free.
- Real short-turn replay also proved that `TURN_COMMIT` and `SPEAK` were queued
  behind Browser-paced audio from the prior response. The Provider could then
  emit the next response audio before Runtime response admission, exhausting
  the intentionally small unadmitted-audio buffer. Ordered turn lifecycle
  actions (`LISTEN`, `REVISE`, `SILENCE`, `TURN_COMMIT`, `SPEAK`) must therefore
  become delivery barriers: they retain order behind prior audio, but the
  Provider reader must stop before mapping later audio until each Runtime
  boundary is admitted. STOP alone keeps its immediate bypass; Provider
  completion and DELEGATE remain on their existing delivery paths.
- After twelve eligible barge rounds across a recovered ordinary-Chrome batch,
  the continuous uplink stopped ACKing and the Browser reached its exact
  1500-frame bound. The Gateway reported only the aggregate
  `MEDIA_NATIVE_INPUT_FENCE_REJECTED`, which currently combines missing/closed
  session, stale record, terminal route, sequence/cursor, and frame-format
  failures. This Tier-3 recovery repair first makes that existing rejection
  safely diagnosable with content-free state/cursor facts, then corrects only
  the reproduced predicate. A healthy continuous Native activation must keep
  ACKing capture while Runtime audio delivery is busy; a genuinely closed,
  stale, reordered, gapped, or format-mismatched frame must still fail closed
  with zero presentation/history/Agent/Tool/Task effects. No public media
  reason, wire field, method, or authority is added.
- The next clean 20/20 barge batch completed, but leaving the foreground route
  listening then exposed a separate lifecycle defect: 30 seconds without a
  Provider event was treated as `REALTIME_PROVIDER_TIMEOUT`, closing an
  otherwise healthy continuous Realtime session and causing later Browser
  capture to fail the exact `session_closed` input fence. Provider silence is
  normal between spoken turns. The operation deadline remains authoritative
  for connect, negotiation, send, and close, while an open session's receive
  deadline becomes an idle polling interval that keeps waiting for the same
  continuous session. Remote close, transport/protocol failure, cancellation,
  and process control remain terminal. This adds no heartbeat, Provider event,
  public reason, fallback, or product authority.
- After the idle repair, a fresh combined batch completed first-audio 20/20
  and then failed on the first long barge response. Browser diagnostics showed
  `frames=1500`, `sent=1148`, `native_sent=10122`, `pending=8`: at least 1140
  frames in the current Browser buffer had already been Gateway-ACKed, but the
  existing Native compactor refuses to release any prefix unless every local
  frame has first entered the eight-frame media window and that window is
  empty. A continuously producing capture can remain slightly ahead of the
  socket indefinitely, so that all-or-nothing predicate turns a small unsent
  tail into a false 30-second retention failure. Native capture must retire the
  exact ACKed prefix (`enqueued - media-pending`) even while a bounded unsent or
  unacknowledged tail remains, preserve the leaf-owned transport sequence and
  cursor, and keep cumulative ACK diagnostics truthful. Cascade capture keeps
  its full recognition buffer and is unchanged; no queue bound, media wire
  field, rotation, Runtime, or product authority is added.
- The next clean combined run completed first-audio 20/20 and 19/20 barge
  attempts before the 257th Native lifecycle action failed as
  `ACTION_LEDGER_FULL`. The exact run produced 60 `LISTEN`, 60 `SILENCE`, 59
  `TURN_COMMIT`, 59 `SPEAK`, and 19 `STOP` proposals. The OpenAI Realtime
  Engine already retains a bounded 1024-action ledger, but the P2 activation
  lease silently used `InteractionEnginePort`'s generic 256-action default.
  Realtime-only P2 activation must use the same existing 1024-action bound so
  the downstream authority does not expire before its source Engine; Cascade
  keeps the generic 256-action default. This is a capacity alignment inside
  the existing action authority, not an unbounded ledger, new action, or new
  product policy.
- After that capacity alignment, a fresh real run completed first-audio 20/20
  and 17/20 barge attempts before the next response closed with
  `NATIVE_AUDIO_BATCH_INVALID`. The retained Gateway trace proves that one
  delivery batch ended with audio from response generation 55 even though the
  preceding queued audio belonged to a different response/item or sequence;
  the Runtime client correctly rejected the mixed batch as not contiguous and
  response-exact. The Gateway delivery worker must split only at the existing
  audio-batch identity boundary (Runtime response, Provider response/item,
  content index and contiguous sequence), retain the first incompatible event
  as the next ordered queue item, and preserve every `task_done`/join and STOP
  fence invariant. This is a Tier-2 queue/state correction inside the existing
  private audio-only batch optimization; it changes no wire shape, capacity,
  Provider mapping, public reason, or Agent/Tool/Task authority.
- A later fresh run completed first-audio 20/20 and five barge-in scenarios
  before OpenAI emitted a normal non-empty audio transcript containing an LF.
  The Engine currently preserves that Provider formatting, but the existing
  `NativeTurnCommit.audit_transcript` contract deliberately rejects every
  control character, including LF, so the otherwise valid Provider completion
  closes the session with `NATIVE_TRANSCRIPT_INVALID`. At the Engine-to-Runtime
  boundary, canonical non-empty Provider transcript line breaks must therefore
  become ordinary spaces before the transcript is proposed for authoritative
  history; safe text and exact Provider provenance remain intact. This is a
  Tier-2 representation repair inside the existing optional audit transcript,
  not a relaxation of the Native contract or a change to speech, routing,
  history authority, Agent, Tool, or Task semantics.
- First-audio latency is measured from the authoritative Browser end-of-speech
  milestone to `webaudio_actually_started`, using the same content-free clock
  model as the existing Cascade L0 baseline. A comparable Cascade run uses the
  same ordinary Chrome, injected corpus, warm-up rule, and browser milestone
  definition.

## Owned product and test surfaces

- `productP1VoiceRoute.ts`, `browserDedicatedMediaRoute.ts`,
  `browserGatewayMediaTransport.ts`, and `browserAudioIOAdapter.ts` only as
  required by the reproduced consumer/backpressure defect.
- Integrated Panel/P2 activation owner only as required to rotate or replace a
  terminal Native activation on the same page.
- Existing Gateway Native response source/registration only if the Browser RED
  test proves a cross-boundary ordering defect.
- Gateway Native Provider event routing only as required to stop reading later
  Provider audio while an ordered turn-lifecycle boundary awaits Runtime.
- Realtime-only Provider event buffering only as required to absorb the
  reproduced faster-than-playout burst, with a fixed 4096-frame bound; the
  Browser response source remains separately bounded and playout-paced.
- Existing private Native proposal client/AgentServer handler and Runtime audio
  admission only as required to admit at most 16 ordered, contiguous,
  same-response audio proposals in one E2A round trip and return one exact
  ordered result per proposal.
- Gateway Native delivery batching only as required to partition adjacent audio
  events at the existing Runtime/Provider response, item, content-index or
  sequence boundary while preserving queue accounting and event order.
- Gateway Native uplink session/cursor diagnostics and focused registration
  tests only as required to distinguish and repair the reproduced long-session
  ACK fence; raw PCM, transcript, prompt, credentials, and opaque capabilities
  remain absent from logs and evidence.
- OpenAI Realtime Native Engine transcript-event mapping only as required to
  distinguish a documented empty interrupted/cancelled transcript from
  normal bounded multiline output and malformed or unsafe history content.
- OpenAI Realtime Native Engine direct-response scheduling only as required to
  serialize one VAD-committed turn behind an actually terminal prior Provider
  response while keeping Provider automatic interruption disabled.
- OpenAI Realtime Native Engine response-output tracking only as required to
  preserve bounded, ordered multi-item audio output and exact per-item barge
  truncation within one already-admitted Provider response.
- Native Runtime audio replay working set only as required to retire terminal
  or cancelled predecessor frame records on exact successor admission, retain
  cumulative content-free counts, and mirror ordered per-item cursor checks.
- OpenAI Realtime Session transport replay working set only as required to
  replace its lifetime event cap with exact bounded LRU retention; no Provider
  payload is logged or persisted.
- Product composition's Realtime-only P2 `InteractionEnginePort` capacity only
  as required to align it with the existing 1024-action OpenAI Realtime Engine
  bound; Cascade configuration and action validation remain unchanged.
- Focused Browser Audio, Product P1, Native interaction, Product activation,
  Gateway downlink/registration, Runtime lifecycle, and existing L0 tests.
- Sanitized validation evidence plus STATUS current packet/capability rows after
  the real Gate actually reruns.

## Explicit exclusions

- No background Task positive journey, P3 policy, Agent/Tool/Task schema, Store
  migration, new classifier, or Provider-direct Jiuwen mutation.
- No new Browser RPC, notification kind, media frame/control, WebSocket
  subprotocol, fourth Native internal method, or second Runtime/session/history
  owner. The existing private proposal method may accept the bounded audio-only
  batch above; actions, delegate, done, and mixed batches remain forbidden.
- No silent fallback to Cascade inside the failed interaction.
- No unbounded queue, disk/raw-audio spool, removal of Browser playout
  backpressure, or relaxation of STOP/stale-generation fences.
- No priority bypass for DELEGATE or Provider completion and no reordering
  within the Native turn-lifecycle action sequence.
- No API-key persistence/logging, raw audio/transcript evidence, account,
  billing, deployment, Production, remote-ref update, AEC/room/device
  generalization, or physical-acoustic percentile claim.

## Acceptance

- RED first: production-shaped eight-frame burst reproduces the current
  Browser failure or missing ACK, while mutation-capable failures assert zero
  presentation/history/Agent/Tool/Task effects.
- GREEN: bounded burst, 149/150/151 continuous frames, completion ACK, delayed
  render, duplicate/reorder, consumer failure, queue limit, close, and barge-in
  paths pass without weakening exact fences.
- Same-page failure/retry proves a new generation and no
  `NATIVE_RUNTIME_CLOSED` reuse; changed replay and foreign generation remain
  fail closed.
- A bounded audio batch proves exact order, per-frame Runtime admission and
  result correspondence; empty, oversized, mixed, non-audio, cross-binding,
  cross-response, gapped, changed-replay, and partial-invalid batches fail
  before new presentation, history, Agent, Tool, or Task effects. STOP remains
  able to overtake queued audio and exact stale returns remain fenced.
- A Provider burst larger than the former 512-frame reservoir is absorbed
  without failure until measured barge-in; STOP is applied ahead of the queued
  audio, queued stale audio creates zero new presentation/history/Agent/Tool/
  Task effects, and overflow beyond the new fixed bound still fails closed.
- Empty or whitespace-only transcript completion followed by cancelled or
  incomplete response completion remains effect-free for history and does not
  close the Native session; a later normal turn still succeeds. Nonblank
  canonical transcript provenance is retained; Provider LF and canonicalized
  CRLF/CR become ordinary spaces at the outbound audit boundary, while every
  other forbidden control or oversized transcript input still fails before
  history admission. The resulting transcript must construct a
  `NativeTurnCommit` without widening its control-character policy.
- With audio delivery blocked, an ordered turn-lifecycle barrier stops the
  Provider reader before later audio is mapped; once prior delivery resumes,
  the barriers reach Runtime in order and `SPEAK` admits the exact Provider
  response before reading its audio. STOP still overtakes blocked audio, while
  DELEGATE and Provider completion do not bypass their existing boundaries.
- Session negotiation sets both VAD `create_response` and
  `interrupt_response` false. First turn and completed-turn continuation each
  send one direct `response.create`; a barge turn sends none before the prior
  cancelled response's terminal event and exactly one afterward. Duplicate
  commits, changed replay, send failure, and a second pending direct turn fail
  closed before new presentation/history/Agent/Tool/Task effects.
- Two ordered audio items in one response retain one continuous Runtime frame
  sequence while preserving each frame's exact Provider item/content identity;
  a presentation cursor for either emitted item is checked against that item's
  own received duration. Same-index identity changes, output-index regression,
  content-index mutation, foreign item cursors, and cursor-ahead values fail
  before presentation/history/Agent/Tool/Task side effects.
- Two interleaved audio items keep independent partial-frame buffers and done
  states; completing or adding audio to one cannot flush, combine with, or
  mutate the other. Runtime frame sequence follows exact Provider event
  arrival, and a new regressing index or delta after item-local completion
  remains effect-free.
- With the Runtime audio-record limit reduced in test, a terminal or cancelled
  predecessor can fill the bound and a successor still admits audio after
  exact retirement; an active predecessor is not compacted, current-response
  duplicate/changed replay still fails closed, cumulative audio counts remain
  truthful, and old-response replay creates zero new media/history/Agent/Tool/
  Task effects.
- With the Session event limit reduced in test, exact replay inside the retained
  window remains identical, changed retained replay fails closed, a new event
  evicts only the oldest returned transport record, retained count stays at the
  bound, and the Session remains open.
- Continuous Native input remains independently ACKed while response audio
  proposal delivery is delayed or saturated at its legal bounded batch. At
  least 1501 contiguous frames cross the same real session without a false
  input fence; missing/closed session, stale record, completed route, duplicate,
  gap, cursor mismatch, and wrong frame size remain rejected before any new
  presentation/history/Agent/Tool/Task effect.
- An already negotiated open Session remains open across multiple receive-idle
  intervals, returns the next real Provider event when it arrives, and records
  no false primary timeout. Negotiation and send deadlines still fail closed;
  remote close, transport/protocol failure, cancellation, and process control
  retain their existing terminal behavior and unique cleanup.
- With an eight-frame Native media window and capture continuing while ACKs
  arrive one task later, the Browser repeatedly retires only the exact ACKed
  prefix, retains unsent plus sent-unacknowledged frames in order, crosses the
  former 1500-frame wall-clock boundary on one uplink, and reports cumulative
  ACK/sent counts without rotating the activation. Missing ACKs still fill the
  fixed bound and fail closed; Cascade recognition buffering is unchanged.
- A Realtime P2 activation accepts and exactly replays more than 256 bounded
  action-only proposals without effect, while the 1024-action maximum, invalid
  action, wrong scope/interaction, duplicate and changed-replay fences remain
  unchanged. Cascade still uses its established 256-action capacity.
- Back-to-back queued audio from two responses/items is delivered as separate
  bounded batches in exact order; a sequence gap or content-index transition
  also starts the next batch, no event is lost or double-completed, and a
  following ordered control still observes normal queue-join semantics.
- Focused and cumulative Tier-3 automation, production frontend build, Ruff,
  applicable mypy/compile, `git diff --check`, and an independent scoped review
  pass.
- In an isolated runtime, ordinary installed Chrome completes warm-up,
  foreground first-audio rounds, a dedicated barge-in round, a second normal
  turn, and cleanup with correlated Provider/Runtime/Browser logs and zero
  background Task effects.
- Realtime and Cascade first-audio results report sample count, p50/p95, exact
  milestone definition, environment/model, and non-claims; missing samples are
  never converted into latency values.
