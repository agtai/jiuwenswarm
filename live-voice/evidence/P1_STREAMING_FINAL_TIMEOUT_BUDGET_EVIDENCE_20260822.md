# P1 streaming-final timeout-budget forwarding evidence

## Boundary and disposition

- Date: 2026-08-22
- Base: the preceding same-tab Task re-entry repair commit
- Implementation: the commit containing this record,
  `fix(live-voice): preserve streaming-final timeout budget`
- Risk: Tier 3 under root `TESTING.md`
- Disposition: **SOURCE/AUTOMATED PASS; PHYSICAL RERUN AND INDEPENDENT TIER-3
  REVIEW OPEN**
- Owners changed: the Formal P1-to-Gateway Speech request type, both initial and
  successor capture Speech adapters, and the panel-to-P1 request adapter

This packet does not change the 38-second client budget, Gateway's bounded
36-second retained streaming-result wait, Provider selection/fallback policy,
P2 activation, same-tab Task recovery or browser-global microphone ownership.

## Reproduction and root cause

During the later two-tab diagnostic run, both P2 activation/refresh sequences
succeeded in tens of milliseconds. Successor media handshakes began near
`17:57:14`; Provider EOT arrived near `17:57:22`, protocol degradation followed
near `17:57:23`, and Gateway's existing batch-fallback settlement completed near
`17:57:42`. The UI nevertheless reported `activation / REQUEST_TIMEOUT`.

The UI seam label was misleading: the timeout did not come from P2 activation.
`GatewayBatchSpeechClient.recognizeStreamingFinal()` declares a 38-second request
budget because Gateway may retain the streaming result for up to 36 seconds.
Formal P1's initial and successor transport adapters accepted only method and
params, discarding the third request-options argument. The panel wrapped the
request once more as `(method, params) => productRequest(method, params)`. The
WebClient therefore used its unrelated 15-second default and failed locally
before Gateway could return the safe fallback.

## Red-first and implemented invariant

Before implementation, the focused initial and successor runtime oracles both
observed `undefined` request options instead of
`{ timeoutMs: 38000, signal: undefined }`. The panel source oracle also rejected
the option-dropping wrapper.

The repair:

- extends `ProductP1Request` with the existing optional timeout/signal shape;
- forwards the exact third argument through the initial capture adapter;
- forwards it through the successor capture adapter; and
- passes the exact `productRequest` function into P1 without another wrapper.

No timeout value is duplicated or redefined in P1. The Speech client remains
the sole owner of the 38-second policy.

## Automated evidence

```text
node --test --test-name-pattern="formal P1 binds media activation|formal P1 consumes the streaming STT final|formal P1 preserves the streaming finalize budget|formal P1 receives the exact Web request function" tests/productP1VoiceRoute.test.mjs tests/liveVoiceIntegratedRoutePanel.test.mjs
4 passed, 0 failed

npm run test:live-voice-integrated-web
453 passed, 0 failed
```

Formal Web retains the pre-existing duplicate locale-key warnings. The complete
browser/build/static matrix is rerun after the browser-global ownership commit.

## Review and non-claims

The failed two-tab attempt is exact reproduction evidence for this adapter bug,
not a physical PASS. No successful real Provider degradation/fallback rerun or
independent Tier-3 review is claimed. This packet does not solve two tabs
capturing the same microphone and does not claim the separately corrected
same-tab A -> B -> A recovery acceptance.
