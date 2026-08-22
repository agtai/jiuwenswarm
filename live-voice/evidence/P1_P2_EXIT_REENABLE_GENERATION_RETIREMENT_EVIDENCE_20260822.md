# P1/P2 Exit/immediate-re-enable lifecycle evidence

## Boundary, source and disposition

- Date: 2026-08-22
- Original integration base:
  `451599b4319c8b4a29054d75d8e2c8b051edae37`
- Delayed-ACK packet base:
  `2e01965ecd89a33ca5917cdad1c1080018bb8b1b`
- Delayed-ACK implementation: the commit containing this updated record,
  `fix(live-voice): decouple retired ACK from successor`. The final hash is
  intentionally reported at handoff rather than embedded in its own content.
- Scoped physical source:
  `8994489ba79db18ccdde16593dd44d61450697af`
- Pre-rebaseline physical source:
  `698c6c375bf3d36563b4f035b573000de136a3e9`
- Disposition: **SOURCE/AUTOMATED/SCOPED PHYSICAL PASS; PACKET ACCEPTANCE
  PARTIAL — independent Tier-3 review remains open**
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

## Delayed-ACK repair

The completed source invariant is stricter than the earlier implemented subset:
an old presentation ACK may finish once in the background, but its latency or
result must not gate, close, mutate or otherwise influence a newer generation.

The mounted oracle was changed first. With the predecessor ACK transport still
retained, it required generation 2 to activate, acquire its media authority and
reach capture before `releaseAck()`. The focused run then failed
deterministically with `retained predecessor ACK blocked generation-2
activation`, establishing the intended red result before implementation.

`productP2ActivationJournal.ts` now upgrades the session journal to v3 and moves
an unresolved presentation ACK from the current blocking operation slot into a
bounded predecessor-owned ledger before predecessor reconciliation. The exact
method, request id and closed parameter set remain durable. The current binding,
phase and successor operation slot no longer depend on that ledger.

The separate retired-ACK drainer:

- replays the exact old request id without owning the current activation recovery
  token;
- removes only that old operation after success, authoritative
  `accepted: false`, route-not-found or another definitive rejection;
- retains the same operation and request id after timeout/unknown settlement;
- skips an original same-page ACK request that is still in flight;
- is Session-scoped and uses a separate same-tab Web Lock/CAS boundary, so a
  late settlement cannot overwrite a successor binding or its own pending ACK;
- bounds unresolved retained authority at 16 entries and fails closed rather
  than evicting an unsettled ACK.

The green mounted oracle now proves generation 2 captures, submits and starts
its own playout before `releaseAck()`. Releasing generation 1 then leaves the
successor playing, creates no additional activation/media/TTS/history effect,
and does not close it. Generation 2 settles its own ACK independently. Final
Exit balances microphone, AudioContext, AudioWorklet and socket ownership and
the retired durable ledger returns to zero.

## Removed intermediate residue

The delayed-ACK packet removes the three obsolete pieces left by the first
intermediate presentation-fence model in `LiveVoiceIntegratedRoutePanel.tsx`:

- `PendingForegroundPresentationFence.turn_id`;
- `PendingForegroundPresentationFence.commit_id`;
- `PendingForegroundPresentationFence.origin_voice_loop_generation` and the
  unreachable `crossesExitedVoiceLoopGeneration` branch.

The crossing branch is unreachable under the corrected invariant. The fence is
installed only when the component is mounted, the Session is current, Live Voice
is enabled and the loop generation still equals its origin. Session replacement,
Exit and every other generation-changing owner clear the pending fence. A
different loop generation therefore cannot observe the retained fence. The
exact Session/correlation/interaction/activation/response fence, capture
barrier, timer clearing and resource cleanup remain. A focused source-structure
oracle enforces both the retained exact fields and the deleted residue.

## Product and test surfaces

Implementation:

- `LiveVoiceIntegratedRoutePanel.tsx` clears predecessor output authority at
  Exit, retires an in-flight predecessor ACK, binds presentation to exact
  activation/response identity, drains old ACKs separately and fences capture
  timers;
- `productP2ActivationJournal.ts` retains exact durable P2 operation/recovery
  truth, performs v1/v2-to-v3 migration and isolates bounded retired ACKs from
  the active binding;
- `product_p2_interaction_adapter.py` admits a strictly newer binding after the
  old lease synchronously enters `CLOSING`;
- `product_composition_registry.py` archives the logically closed route,
  releases route-local Task/critical-token state, retains root cleanup ownership
  and drains pending P2 teardown in the background;
- the controlled Formal Web launcher owns the provider/origin/media/receipt/
  Direct-D2 runtime contract and verifies it with a credential-free probe.

## Automated result on the final source tree

```text
npm run test:live-voice-integrated-web
450 passed, 0 failed

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

node --test tests/liveVoiceBuildProfiles.test.mjs
2 passed, 0 failed

pytest test_portable_launchers.py
3 passed, 0 failed (unchanged packet-base evidence; not rerun)

pytest test_product_p2_interaction_adapter.py test_product_composition_registry.py
214 passed, 6 failed

npm run build:live-voice
PASS

.venv/Scripts/python.exe -m ruff check (P2/Registry product/test files)
PASS

git diff --check
PASS
```

The six Python failures are unchanged from the packet base and all remain in
`test_product_composition_registry.py`: three P3 bounded/status fixture cases,
the disconnect cleanup case, the in-flight query/stop case and the text-status
dispatch/projection case. Their existing causes are the `_P3Composition`
fixture missing `_accepting` or
`PRODUCTION_TASK_AUTHORITY_PROJECTION_MISMATCH`. No Python file changed in this
packet, so the result is disclosed as `214/220`, not called PASS.

The production build retained its existing chunk-size warning; the Formal Web
run retained existing duplicate-locale warnings. Build-profile truth is `2/2`.
The unchanged launcher/probe `3/3` result belongs to the `2e01965ec` packet base
and was not rerun because no launcher or probe surface changed.

## Review result and limitation

A fresh Main cold review inspected the v3 parser/migration, storage CAS, separate
retired-ACK lock, live-request race, refresh/route-loss recovery, Session
isolation and mounted resource ownership. It found one corrupt-storage gap: a
single request id could have been reused across different retired ACK params.
The final source rejects that journal and includes a negative oracle.

No independent reviewer facility was available under the current execution
constraints. This cold review is useful substitute evidence but does not satisfy
the independent Tier-3 review requirement in root `TESTING.md`; that Gate remains
explicitly open.

## Physical observation and non-claims

On exact clean product source `8994489ba79db18ccdde16593dd44d61450697af`,
running the controlled `formal-web-validation` profile, the user completed five
scoped checks across two local Formal Web Sessions:

1. real text input reached the JiuwenSwarm Agent/tool path and returned grounded
   tool output;
2. an ordinary microphone turn was recognized once, answered once, played once
   and returned to listening;
3. Exit during an active response followed by immediate re-enable let generation
   2 listen and capture immediately, with no resumed predecessor audio, duplicate
   response or successor shutdown;
4. switching Sessions kept late response, audio and state authority isolated;
5. Exit reduced microphone/audio/media ownership to zero and a later re-enable
   re-established one clean capture/response cycle.

All five checks passed. The physical journey owns the real browser, microphone,
speaker, Session and resource-lifecycle seam. It did not artificially retain or
reject the presentation-ACK transport. Delayed ACK success, rejection, timeout,
route-not-found, refresh and durable replay are therefore credited only to the
automated fault oracles above, not inferred from physical execution.

The earlier pre-rebaseline `698c6c375` four-scenario observation remains
supporting history. The documentation-only amend that records the current run
does not change the tested product or test files. Independent Tier-3 review
remains open, so this scoped PASS does not claim complete P1/P2, P3-9,
controlled-candidate, product-readiness or Production-readiness acceptance.
