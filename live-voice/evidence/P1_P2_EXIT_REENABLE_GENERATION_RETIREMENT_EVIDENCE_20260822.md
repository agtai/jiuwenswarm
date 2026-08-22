# P1/P2 Exit/immediate-re-enable lifecycle evidence

## Boundary, source and disposition

- Date: 2026-08-22
- Integration base:
  `451599b4319c8b4a29054d75d8e2c8b051edae37`
- Consolidated implementation: the commit containing this record,
  `fix(live-voice): consolidate Exit re-enable recovery`. The final hash is
  intentionally reported at handoff rather than embedded in its own content.
- Pre-rebaseline physical source:
  `698c6c375bf3d36563b4f035b573000de136a3e9`
- Disposition: **PARTIAL — ordinary Exit/re-enable paths repaired and observed;
  delayed predecessor presentation ACK still blocks successor activation**
- Risk: Tier 3 under root `TESTING.md`
- Owners changed: Formal Integrated Web presentation/capture arbitration,
  same-tab P2 recovery, Registry-to-P2 lifecycle retirement and the controlled
  Formal Web validation profile

No Provider, media wire protocol, shared schema, Agent/Tool/Task product policy
or generation-time Agent cancellation policy changed.

## Corrected root cause and retained boundaries

The first intermediate repair treated an accepted predecessor response as
presentation work that a successor generation should fetch, text-present and
ACK. That crossed the canonical generation fence. Exit closes the predecessor
notification consumer, while Runtime shutdown may discard its unpresented final
after the accepted Agent turn finishes. A successor was therefore waiting for
output it was not authorized to present and the backend could discard.

The consolidated repair implements this subset:

- Exit synchronously fences the old activation/generation, local output and all
  unpresented predecessor presentation authority;
- an accepted predecessor Agent turn may finish exactly once under its shielded
  Runtime close coordinator but produces zero successor notification, ACK,
  TTS/playout or assistant-history effect;
- Registry logically retires a route whose P2 lease is already `CLOSING` or
  `CLOSED`, while a retained background owner finishes physical Runtime cleanup;
- in the unresolved-Agent path, a strictly newer generation activates and
  captures without waiting for that Agent turn;
- the successor records, submits, presents, ACKs and plays only its own exact
  generation.

The same-tab explicit **Listen again** repair remains necessary for a different
failure. It promotes only a generic `result_unknown` journal with no durable
pending operation into exact predecessor reconciliation. Automatic recovery
remains zero-effect and fail-closed. This fallback does not and must not clear a
retained presentation ACK.

## Open delayed-ACK defect

The complete acceptance invariant is stricter than the implemented subset: an
old presentation ACK may finish once in the background, but its latency or
result must not gate, close, mutate or otherwise influence a newer generation.
The current browser recovery owner does not satisfy this.

The mounted test
`mounted Exit during a retained presentation ACK settles once before opening
one P2 successor` deliberately retains the ACK transport. After Exit followed by
immediate start, it asserts zero P2 close. Only after `releaseAck()` does it
expect predecessor close, generation-2 activation and successor capture. The
test is green, but that oracle encodes the undesired serialization. Formal Web
`443/443` therefore does not close the complete defect package.

The gate is in `productP2ActivationJournal.ts`: recovery treats a retained
presentation ACK like every other durable pending operation and awaits
`replay_operation` before predecessor close and successor allocation. The
Registry/P2 lifecycle already has the separate capability to logically retire a
`CLOSING` predecessor while its retained cleanup finishes. The follow-up repair
should preserve the ACK as a predecessor-owned, exactly-once background
operation while releasing successor activation from that wait.

Required follow-up oracle:

- retain the predecessor ACK promise;
- Exit and immediately re-enable;
- prove predecessor ACK call count remains exactly one;
- before releasing the ACK, prove generation 2 activates, reaches capture,
  records, submits and can present its own response;
- release the old ACK and prove its result cannot close/mutate generation 2,
  replay TTS/audio/history or allocate any Agent/Tool/Task effect;
- finish with balanced microphone, AudioContext, AudioWorklet, socket, timer,
  media-authority and Agent-pin ownership.

## Removable intermediate residue

The first intermediate presentation-fence model also left three obsolete pieces
in `LiveVoiceIntegratedRoutePanel.tsx`:

- `PendingForegroundPresentationFence.turn_id` is written but never read;
- `PendingForegroundPresentationFence.commit_id` is written but never read;
- `origin_voice_loop_generation` exists only to drive
  `crossesExitedVoiceLoopGeneration`.

The crossing branch is unreachable under the corrected invariant. The fence is
installed only when the component is mounted, the Session is current, Live Voice
is enabled and the loop generation still equals its origin. Session replacement,
Exit and every other generation-changing owner clear the pending fence. A
different loop generation therefore cannot observe the retained fence. The two
identity fields and the crossing branch may be removed, while the exact
Session/correlation/interaction/activation/response fence must remain.

This cleanup should be included in the delayed-ACK packet, not committed alone:
its focused source-structure and mounted resource oracles can then prove both
that dead code disappeared and that no stale-output/TTS protection was weakened.

## Product and test surfaces

Implementation:

- `LiveVoiceIntegratedRoutePanel.tsx` clears predecessor output authority at
  Exit, binds presentation to exact activation/response identity, fences capture
  timers and performs explicit same-tab retry recovery;
- `productP2ActivationJournal.ts` retains exact durable P2 operation/recovery
  truth; its current presentation-ACK serialization is the open seam above;
- `product_p2_interaction_adapter.py` admits a strictly newer binding after the
  old lease synchronously enters `CLOSING`;
- `product_composition_registry.py` archives the logically closed route,
  releases route-local Task/critical-token state, retains root cleanup ownership
  and drains pending P2 teardown in the background;
- the controlled Formal Web launcher owns the provider/origin/media/receipt/
  Direct-D2 runtime contract and verifies it with a credential-free probe.

## Automated result on the rebased tree

```text
npm run test:live-voice-integrated-web
443 passed, 0 failed

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

node --test tests/liveVoiceBuildProfiles.test.mjs
2 passed, 0 failed

pytest test_portable_launchers.py
3 passed, 0 failed

pytest test_product_p2_interaction_adapter.py test_product_composition_registry.py
214 passed, 6 failed

npm run build:live-voice
PASS

ruff check (changed Python product/test files)
PASS

git diff --check
PASS
```

The six Python failures are the existing P3 fixture/projection cases: test
`_P3Composition` lacks `_accepting`, or its collection projection fails with
`PRODUCTION_TASK_AUTHORITY_PROJECTION_MISMATCH`. The exact Exit/Agent-generation
Registry-to-Runtime race passes. These P3 failures are outside this repair, but
also grant no PASS credit to it.

The build retained existing Vite chunk-size, mixed-import and duplicate locale
key warnings. No warning category was introduced by this repair.

## Physical observation and non-claims

On the pre-rebaseline local tree `698c6c375`, the user completed four ordinary
physical scenarios successfully: baseline dialogue; Exit while the Agent was
working followed by immediate re-enable; Exit during playout followed by
re-enable; and Session isolation. No duplicate user/Agent/history/Tool/Task or
audio effect was observed, and the successor could record, submit and play.

That run did not artificially retain the presentation-ACK request and predates
the two D-093 remote commits. It is supporting physical evidence, not delayed-ACK
or current-candidate acceptance. Independent Tier-3 review, the delayed-ACK
repair and a clean current-source physical rerun remain open. This record does
not claim complete P1/P2, P3-9, product readiness or Production readiness.
