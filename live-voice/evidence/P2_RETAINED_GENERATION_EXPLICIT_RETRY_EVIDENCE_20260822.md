# P2 retained-generation explicit-retry evidence

## Boundary and source

- Date: 2026-08-22
- Integration base: `451599b4319c8b4a29054d75d8e2c8b051edae37`
- Implementation source: the consolidated commit containing this record,
  `fix(live-voice): consolidate Exit re-enable recovery`; final hash is reported
  at handoff rather than embedded in the commit itself
- Risk: Tier 3 under root `TESTING.md`
- Owner: Formal Integrated Web P2 recovery and capture admission
- Changed product surfaces:
  `LiveVoiceIntegratedRoutePanel.tsx` and
  `productP2ActivationJournal.ts`
- Changed automated surfaces:
  `liveVoiceIntegratedRoutePanelMounted.test.mjs` and
  `productP2ActivationJournal.test.mjs`

No backend, shared protocol/schema, Provider, Agent/Tool/Task policy or
automatic-refresh recovery policy changed.

## Reproduced failure and invariant

A same-tab refresh preserves the P2 activation journal in `sessionStorage`.
The reported route retained generation 12 in the legacy generic
`result_unknown` phase. Automatic recovery correctly kept this unclassified
truth as a zero-effect barrier, but the user-visible **Listen again** action
called only ordinary capture start. With no active P2 binding, that action was
a no-op; another F5 restored the same barrier.

The repair keeps automatic refresh fail-closed. Only an explicit user retry may
promote a generic unknown with no durable pending operation into exact
activation reconciliation. The recovery owner must replay and close the same
predecessor before creating a successor. Unknown cleanup truth remains
`closing_unconfirmed` and blocks the successor. A successful successor resumes
the requested voice loop and starts capture once.

This transition never declares submit, presentation ACK, barge-in or activation
success and never clears a durable pending operation. It therefore cannot use
the retry action to invent Agent, Tool, Task, history, TTS or audio truth.

## Automated oracle

The mounted regression uses the reported Session/correlation and generation 12.
It asserts:

- first mount and a second same-tab remount perform zero P2/media effects;
- explicit **Listen again** performs generation 12 activate replay, generation
  12 close and generation 13 activate, in that order;
- the old binding closes once and one microphone/media route starts;
- submit and presentation ACK effects remain zero;
- the journal becomes active only on generation 13 and the recovery diagnostic
  clears;
- an uncertain old close retains the exact barrier and allocates no successor.

The adjacent mounted Exit/immediate-re-enable cases also remain green, including
old unified success/rejection, retained presentation ACK, stale TTS settlement,
successor capture and zero old-generation audio replay.

The retained-presentation-ACK case is not a closure oracle for immediate
re-enable: it currently waits for the old ACK before opening the successor. This
retry repair remains necessary for the separate generic `result_unknown` path,
but it neither fixes nor authorizes clearing that durable ACK.

## Commands and results

From `jiuwenswarm/channels/web/frontend`:

```text
npm run test:live-voice-integrated-web
443 passed, 0 failed

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

npm run build:live-voice
PASS

pytest scripts/live_voice/w2_rehearsal/tests/test_portable_launchers.py
3 passed, 0 failed
```

`git diff --check` passed. The build retained the pre-existing Vite chunk-size,
mixed static/dynamic import and duplicate locale-key warnings; none was
introduced by this repair.

## Review and non-claims

A cold local diff review found no path that bypasses exact predecessor cleanup,
clears a durable pending operation or admits successor capture before a higher
generation is active. Independent Tier-3 review remains open.

This record grants source and automated credit only for the exact explicit-retry
fallback. It does not grant delayed-ACK or complete Exit/re-enable closure and
does not claim a new physical microphone/speaker result. Current-source Chrome
acceptance must still
prove both the retained generation-12 retry and Exit during response processing
with immediate re-enable, normal successor recording/submission/playout and
final device/media cleanup.
