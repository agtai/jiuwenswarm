# P7 Native terminal notification preparation

Main accepted this Tier-3 boundary on 2026-09-07 under the user's full P0–P9
execution grant. This is the implementation checkpoint, before code changes.

## Intended behavior and authority

After a current authenticated Native activation receives a true terminal Task
notification, it may prepare that exact notification's existing TTS while user
speech or foreground playback retains priority. Preparation never opens a browser
downlink, displays text, changes heard history, acknowledges a presentation, or
invokes Agent/Tool/Task work. Existing playback arbitration owns claim. A claimed
source receives a fresh one-use media ticket with the existing 30-second TTL.

The preparation owner binds session, connection, media subject, activation and
generation, correlation, interaction, Task/attempt/event, response and generation,
unit, exact text SHA-256, locale and sample rate. The server compares these with
the existing server-originated terminal AUDIO presentation transfer; client text
or a preparation identifier alone grants no authority. Cancelled Task notices,
running notices, ordinary Agent text, Native response audio and Cascade do not
acquire this capability.

## Protocol and lifecycle

The new local-only capabilities/prepare/claim/cancel RPC family negotiates the
closed `live-voice.task-notification-preparation.v1` contract. An unavailable or
older server preserves the existing synthesis path. Existing Speech RPC schemas
and legacy consumers remain supported unchanged.

There is at most one opening/retained/claimed preparation per activation and a
global capacity of eight slots, including cancellation-hostile cleanup. Exact
duplicate prepare requests share one result; changed
identity or content conflicts. A TTS admission lease rejects preparation while
another TTS owner is opening or active, before response-generation changes. Normal
TTS cannot silently supersede an unclaimed preparation; it may explicitly fence
that exact source. Native user response audio remains independent.

A different queued terminal response leaves the first preparation intact. A
rewrite of that same response/event/unit/text fences its old preparation.
Capabilities are re-negotiated for each new capture activation. The established
authenticated Task preview remains the normal presenter's responsibility;
preparation readiness adds no display, heard-history or presentation effect.
The existing Native foreground notification polling policy is unchanged.

Preparation drains the existing streaming TTS producer into an in-memory PCM
spool, avoiding its ordinary 16-frame/two-second media backpressure deadline.
The spool is limited to 750 ordered 20 ms frames (15 seconds) and 3 MiB of decoded
PCM, with one producer and one consumer; bounds apply to total produced audio,
including audio already read. One source frame never exceeds the negotiated
sample rate divided by 50, mono float32. Preparation has a 15-second production
deadline and a 30-second unclaimed retention deadline. A full or malformed source
fails that exact preparation closed. Produced/ready is never presented.

Claim starts the fresh existing 30-second ticket deadline. Ticket attachment
atomically verifies that exact child and starts a separate 30-second render
deadline; this is a failure fence, never evidence of playback. PCM EOF and even
successful downlink transport completion retain the claimed slot and its child
source pointer until the existing Registry accepts the actual browser render
receipt. Cancel, rewrite or render timeout removes only that child and its exact
matching downlink evidence, so late transport completion cannot recreate ACK
authority. Accepted render truth remains immutable under later duplicate cancel.
The real media leaf calls iterator `aclose()` after successful EOF too; that
cleanup preserves the awaiting-receipt identity. Incomplete transport completion
and exceptional socket abort explicitly fence and remove only the prepared child
before generic source cleanup can discard the pointer.
This refinement was accepted by Main during independent review on 2026-09-07.

Claim rechecks the complete owner and source identity after existing capture
arbitration. It mints at most one ticket; duplicate continuations reuse one local
claim promise. Cancel, expiry, source replacement, activation close/replacement
and a user-priority handoff fence the slot and discard its PCM. Cleanup targets
only its producer/source and never calls generic `media.close`. Cancellation-
hostile completion is retained within the capacity limit and cannot revive a
slot. Reactivation re-observes the durable Task notification under the new owner;
old preparations, tickets and ACKs are not transferred. Failed/expired preparation
does not silently resynthesize the already consumed old grant; existing canonical
presentation failure/recovery supplies the truthful next presentation.

## Owned surfaces and dependencies

P7 owns the new preparation owner and tests; precise integration in dedicated
media registration, product streaming synthesis and streaming synthesis admission;
the exact local RPC allowlist; Gateway browser wrappers; the P1 preparation slot;
and terminal preview/claim/cancel glue in the Integrated panel and focused tests.
The existing product/streaming synthesis and streaming route implementations are
unchanged: the exact Registry admission wrapper supplies the no-supersede lease
around their existing path. Main owns semantic integration with P2 and P5, one eventual P7 commit and candidate
acceptance. No worker Git changes or remote updates are authorized here.

## Verification and exclusions

The applicable P/N/B/S/T/C/R/I/F/K/X matrix includes a positive true-terminal
prepare→claim→actual media receipt journey, duplicate/changed/wrong-scope calls,
busy admission, source rewrite, overflow, timeout, late/cancellation-hostile
completion, exact child cancellation, user speech/Native successor priority,
activation replacement, reactivation and lost/duplicate claim responses. Every
preclaim and rejected path asserts zero audio enqueue, UI/heard-history,
presentation ACK and Agent/Tool/Task effects. Existing Native Task TTS and Cascade
regressions, type checking, frontend build, cold scoped review and independent
review are required. Real Registry→synthesis owner→media-source integration is
required; fake Provider data is not real Provider or physical acceptance.

No Provider/model/configuration, notification wording or policy changes; no
pre-terminal guesses, new Task authority, persistent PCM, Native-audio shortcut,
Cascade prefetch or cross-activation cache. Main owns the selected real TTS and
current-source browser/device benchmark. The imported 6.12-second reactivation
sample and 3–4.5-second target are conditional; the original 33 seconds includes
user speech/voice-off time and cannot be claimed eliminated. No measured speedup
or complete candidate acceptance is claimed by this implementation checkpoint.

## Implementation evidence and remaining acceptance

Worktree baseline: `841c14ac2e9b0aef45336066cd4e7c401ab27436`, branch
`codex/realtime-p7-notification-20260907`, no upstream. Worker made no Git
mutations or Provider calls. Node packages are individual junctions with a local
`.cache`; baseline checks use a read-only Git archive and a second local cache.
Python checks use Main's isolated pinned SDK environment.

| Matrix | Concrete evidence |
|---|---|
| P / X | Production Registry → existing streaming synthesis owner → registered media socket leaf, including successful completion callback and iterator-finally cleanup; positive exact claim, contiguous PCM download, transport evidence and existing render-receipt acceptance. Provider/socket/render inputs are fixtures, so this is not physical/real-Provider acceptance. Mounted production Panel/P1/AIO positive emits one media receipt and one P2 ACK after render, with the same microphone still capturing. |
| N / I | Wrong event/text/activation/subject/connection/origin, cancelled/running notices and malformed closed fields fail before Provider/ticket/audio/receipt effects. Exact identity includes durable Task/attempt/event and response/unit/text digest. |
| B / S | Frame/byte ceilings, zero/invalid sources, global eight-slot bound, hard production timeout, unclaimed/ticket/render expiry, and EOF-versus-render state are enforced. Cancelled producers retain capacity until cleanup truly exits. |
| T / C | Concurrent duplicate prepare uses one synthesis; exact duplicate P1 play continuations share one entire claim/play/receipt promise. Busy normal TTS opening prevents preparation before supersession. Late ready/claim, close and cancellation-hostile completion cannot revive the source. |
| R | Lost claim response fails without old-grant resynthesis; exact close/source replacement fences old ownership. Existing media-reauthorization replay is moved before capture arbitration on reactivation. Current-source full reactivation/physical measurement remains Main's candidate acceptance. |
| F / K | Unsupported negotiated capability preserves the old TTS path. Task failure uses the existing canonical presentation-failure route. Continuous Native input, Native audio and Cascade regressions remain exercised. No new Task policy or persistent format is introduced. |

Focused checks on the final production source:

- Backend: `test_task_notification_preparation.py`,
  `test_product_streaming_synthesis.py`, `test_dedicated_media_registration.py`,
  `test_live_voice_speech_rpc.py`: **215 passed**, `--no-cov`, 9.60 seconds;
  `logs/p7-backend-leaf-final.log`.
- Gateway/browser privacy: **35 passed**, including closed negotiation and
  child operations preserving a pending ordinary synthesis;
  frontend `node_modules/.cache/p7-gateway-final.log`.
- Full focused Native/P1 suite: **140 passed** before the narrow shared-promise
  review fix. Its seven directly affected P7 scenarios then passed with exact
  Promise identity, one claim/play/receipt and no duplicate cancellation;
  `p7-native-final.log`, `p7-frontend-coalesced.log` in the same frontend cache.
  Main reran the full **140 passing** Native/P1 and **35 passing** Gateway/privacy
  checks after the fix. The independent reviewer also freshly compiled and ran
  the complete P1/Gateway pair: **157 passed**, plus **2 passed** new mounted
  scenarios; local cache `p7-independent-frontend-fixed.log` and
  `p7-independent-mounted-fixed.log`.
- Mounted candidate comparison: **8 passed / 2 failed** over ten selected nodes.
  The unchanged baseline has **6 passed / the same 2 failed** over its eight
  existing nodes; the two added P7 mounted scenarios pass. The repeated baseline
  failures are `mounted response-generation failure failed projects exact
  terminal recovery identity with zero Task authority` (diagnostic timeout) and
  `mounted already-settled interruption retains its answer without claiming
  playout over the speaker` (expected deferred reason, received null).
- Pure Panel suite: **69 passed / 1 failed**. Its unchanged `actual Live Voice
  product entry selects the formal P1 owner while compatibility fallback remains
  flag-off only` source-pattern assertion expects `onTaskRefresh=` in untouched
  `index.tsx`; the same node fails identically in the baseline archive.
- Strict TypeScript, Ruff `F,E9` on owned Python surfaces and `git diff --check`
  pass. Production frontend build passes, with pre-existing duplicate locale
  keys and large-chunk warnings. Final `build:live-voice` passes after the
  shared-promise fix (Vite 24.92 seconds, plus successful TypeScript), cache
  `p7-build-reviewed.log`. Main independently reports the same build passing.

The attempted broad mounted run is **not PASS**. Only the named failures have
baseline comparisons; unsampled mounted failures remain unclassified and are
not excluded from candidate acceptance. Logs for the baseline comparison live
under `logs/p7-baseline-841c14ac/jiuwenswarm/channels/web/frontend/node_modules/.cache/`.

Independent Astra max review found EOF/transport-complete cancellation could
otherwise permit a late receipt. The repair retains exact child cancellation
through real render settlement. Regression
`test_eof_keeps_cancel_ownership_until_real_render_receipt` covers cancel,
authoritative rewrite, render timeout and failed transport both before and after
transport completion, including successful EOF iterator cleanup. The positive
test now traverses `handle_registered_media_socket`; genuine send-error and
receive-cancellation tests verify exact unfinished-child removal and zero parent
receipt/downlink/close effects. Additional review repairs cover coalesced play
and attach-time expiry. Main/reviewer own final recheck and integration acceptance.

Final independent Astra max recheck passed on the frozen helper
`D5AD4762F94ADCD72546A95675A090BFDD5BC3AE7BCEB41172F89E40EF3F6E03`,
Registry `3BC5E2B853F0C72BC12EC9975D0465320893B73334167262697B4C350DEECE23`
and P1 `86C0DDF467A6A1518E2C098522F5BFB94E8BE3F1264F5DF947CB789CC5D5D4C3`.
The four backend files passed **215 tests / 9.14 seconds**, and the independent
original EOF probe passed before/after transport completion: successful iterator
cleanup retained cancellation authority; exact cancel removed the child; late
completion returned false and late render ACK was untrusted, with zero receipts
or parent close. No actionable finding remains in the scoped review. Logs:
`logs/p7-independent-leaf-final.log` and
`logs/p7-independent-eof-fixed-probe.log`. Integration and physical acceptance
remain Main's responsibility.

Main's real selected-TTS probe at the preceding EOF-ownership freeze produced
173 contiguous frames / 3.46 seconds of PCM, ready in 971.02 ms and claim in
0.26 ms. EOF retained one revocable slot; exact cancel removed its child with
zero receipts and the parent open. A separate preclaim cancellation was ready
in 624.43 ms and left no ticket/receipt/parent close. All route/preparation tasks
were cleaned up and private configuration stayed unchanged. Evidence:
Main worktree `logs/p7-real-worker-reviewed/evidence.json`, which records its
precise source hashes. The Task and Native activation were synthetic canonical
fixtures; Registry, existing selected TTS Provider and PCM were real. There was
no physical playback, Task mutation or fabricated browser render ACK. These
single samples establish that path's conformance, not a measured reactivation
speedup. Main owns the final leaf-repair source rerun and candidate measurement.
