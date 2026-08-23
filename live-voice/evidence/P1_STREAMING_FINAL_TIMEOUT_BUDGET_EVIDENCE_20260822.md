# P1 streaming-final timeout-budget forwarding evidence

## Boundary and final disposition

- Date: 2026-08-22; consolidated 2026-08-23
- Baseline: `2e01965ecd89a33ca5917cdad1c1080018bb8b1b`
- Consolidated implementation:
  `6aad3a7f3` (`fix(live-voice): preserve streaming-final timeout budget`)
- Risk: Tier 3 under root `TESTING.md`
- Gate: **PASS — `C0 / I0 / M0`**
- Physical credit: exact-tree normal Provider recognition completed without a
  15-second false `activation / REQUEST_TIMEOUT`
- Remaining physical non-claim: real >15-second Provider degradation/fallback

This boundary owns transparent timeout/AbortSignal forwarding from both Formal
P1 Speech adapters through the Panel request seam to WebClient. It does not
change the 38-second policy, create an AbortController, alter Provider fallback
or own P2 activation, same-tab recovery or browser capture ownership.

## Root cause and final invariant

Gateway may retain a streaming final for up to 36 seconds, so
`GatewayBatchSpeechClient` owns a 38-second request budget. Initial and
successor P1 transport adapters previously discarded the third request-options
argument, and the Panel wrapped `productRequest` with another two-argument
adapter. WebClient therefore applied its unrelated 15-second default and could
report `activation / REQUEST_TIMEOUT` before a valid Gateway fallback settled.

The final invariant is:

- `GatewayBatchSpeechClient` remains the only 38-second policy owner;
- initial and successor adapters accept the existing
  `{ timeoutMs?, signal? }` shape and pass the same `options` object as the
  third `#request` argument;
- Panel passes the exact `productRequest` function; and
- streaming success never triggers duplicate batch recognition.

## Review closure

| Review HEAD | Result | Finding | Closed at |
|---|---|---|---|
| `c9ff11e460dd588b23b1761bf7609c446a208741` | FAIL `C0/I1/M0` | runtime fixtures used only `signal: undefined`; rebuilding options while dropping a non-empty signal stayed green | `1905b70b9ea2ac514f4772cc1b800def9404c4c2` |
| `1905b70b9ea2ac514f4772cc1b800def9404c4c2` | PASS `C0/I0/M0` | no finding; production-source dual-adapter oracle and four isolated mutations accepted | — |

The accepted oracle reads the real production source and requires exactly two
matching adapters. Dropping the third argument or rebuilding either adapter
with `signal: undefined` is deterministically RED. The production boundary is
frozen.

## Automated evidence

```text
focused initial/successor/Panel forwarding
5 passed, 0 failed

npm run test:live-voice-gateway-batch-speech
29 passed, 0 failed

npm run test:live-voice-integrated-web
466 passed, 0 failed on the rewritten consolidated product/test tree

npx tsc --noEmit
PASS

npm run build:live-voice
PASS
```

The exact option identity oracle is source-bound because Product P1 currently
does not produce a non-empty signal in the normal runtime journey. This closes
the adapter evidence without inventing a cancellation policy. Existing
duplicate-locale, mixed-import and chunk-size warnings are unchanged.

## Physical evidence and non-claims

The diagnostic run that exposed the 15-second timeout remains reproduction
evidence. The 2026-08-23 exact-tree physical run completed seven real EOT/
recognition/submit journeys with zero `REQUEST_TIMEOUT`, but their Provider
finals completed normally; it did not produce a streaming-final degradation
longer than 15 seconds. Explicit Exit/takeover generated truthful
`STREAMING_SPEECH_ROUTE_ABORTED` cancellation fallback, which is not promoted
to delayed-Provider credit. A real >15-second Provider degradation/fallback,
broader cancellation behavior and Provider fault injection remain physical
non-claims.
