# P2 bounded notification pull default-on evidence — 2026-08-21

## Scope and source

- Accepted feature-on source: `4b405fca119699fa51b3a1189567665fa53ce1f8`.
- Accepted validation-branch implementation: `6d5f6759724310b40c5bd3562e8d557aeb6ac61f`.
- Current W3 production/test review target: `b4f449aea73aacbcc635f02f2472e478d25f2047`.
  The final amend changes this evidence/STATUS only; its production and test
  trees remain the tested target's trees.
- Decision: [D-094](../decisions/DECISIONS.md). It removes only the two
  validation deployment switches and changes no Successor-ACK/TTS policy.
- Capability: P2 Realtime Media / Integrated Web notification delivery.
- Risk: Tier 3 because batched authoritative finals cross presentation and TTS
  authorization. The earlier repair validates and authorizes each batch item
  before downstream media effects.
- Exclusions: no Speech Provider/model/billing, protocol maximum, raw-audio,
  Task authority, Successor-ACK/TTS, Exit, VAD, generation interruption or
  fixed-corpus policy change.

## Accepted product behaviour

1. Production Integrated Web constructs its P2 notification owner with batch
   size `16`.
2. The server accepts an explicit canonical integer from `2` through `16`.
3. A client that omits `max_notifications` continues to receive one
   `notification`, preserving the old client protocol.
4. A/B automation injects batch size `1` or `16` into the owner. Deployment
   environment no longer selects the transport mode.
5. The former frontend and backend P2 batch deployment switches are retired.
6. Successor-ACK/TTS has no feature switch and remains default-on.

## Human acceptance

The user accepted the feature-on run after the dedicated-media authorization
repair. Visible task times were:

| Prompt | Accepted observed time |
|---|---:|
| Eight-point Hangzhou answer | `10.65s` |
| Five-point water-cycle answer | `7.05s` |
| City-name-only answer | `2.78s`, `3.14s`, `3.14s` |

All scoped answers produced audible TTS. The earlier
`SPEECH_OPERATION_NOT_AUTHORIZED` recovery failure did not recur.

The small prompt set was not frozen, randomized or large enough for p50/p95.
It proves the accepted default path and the absence of the repaired failure in
that run; it does not prove feature-complete latency or broad product readiness.

## Current integration verification

- Backend batch/compatibility/authorization focus: `7/7` PASS across Registry,
  P2 Adapter, Runtime, Dedicated Media and streaming synthesis.
- Frontend dependency-injected A/B test: `2/2` PASS; batch sizes `1` and `16`
  retain zero forbidden submit/presentation/barge-in/P3/Agent/Tool/Task/history/
  audio effects in the synthetic benchmark.
- Current deterministic CLI benchmark used three samples and an identical
  `10ms` injected per-RPC delay. For 10/50/100 notifications, RPCs per attempt
  changed from `10/50/100` to `1/4/7`; observed p50 changed from
  `156.766/785.545/1561.254ms` to `15.922/61.904/108.936ms`, reductions of
  `89.8%/92.1%/93.0%`. This proves the causal queue/RPC improvement, not real
  end-to-end Provider p50/p95.
- Full Formal Integrated Web: `472/472` PASS.
- Browser Audio I/O: `103/103` PASS; Dedicated Media registration: `47/47`
  PASS; build profiles: `2/2` PASS.
- TypeScript `--noEmit`, production Live Voice build, affected Ruff and scoped
  `git diff --check`: PASS. The build retains the disclosed mixed-import and
  chunk-size warnings; Formal Web retains the existing duplicate locale-key
  warnings.
- The five affected Python files cumulatively report `352 passed / 6 failed`.
  The six failures are the already disclosed P3 fixture/projection set
  (`_P3Composition._accepting`, production Task projection, disconnect/inflight
  query and text-status projection); all seven new P2 batch tests pass. This run
  is therefore not described as a cumulative Python PASS.

## Independent Tier-3 integration review

The first integration-delta review on `eb9e484e664c03d7eddabb9947595d2ef2760bda`
failed `C0 / I1 / M0`: a batch containing a valid final followed by a same-
binding invalid tail could retain one partial Speech authorization before the
tail was rejected. The old-source deterministic probe reported
`authorized_entries=1`.

The production/test follow-up target `b4f449aea73aacbcc635f02f2472e478d25f2047`
closes that finding by validating the complete exact batch/item key sets,
activation binding, publish sequence and non-tail observer barrier before any
legacy notification authorization runs. The same probe reports zero authority;
valid single and valid observer-plus-final batch paths each authorize exactly
one final. Extra-key, duplicate-sequence and barrier violations retain zero
authority. The independent follow-up is **PASS — C0 / I0 / M0**. The two older
playout/capture decoupling seams have no production delta and retain their
separate PASS; no physical or product-readiness credit is added.

## Remaining acceptance

- Frozen environment/corpus/sample-size latency p50/p95.
- Speech interruption while the Agent is still generating.
- Broader device/network/backpressure/reconnect and P3-9/controlled product
  acceptance. The consolidated lifecycle journey, including Exit/re-enable, is
  already closed by newer exact-tree evidence and is not reopened here.

## Sanitization

No bearer token, Speech credential, raw audio, transcript log, subject identity,
private project content or machine-private environment value is retained here.
