# P1 browser-global capture ownership evidence

## Boundary and disposition

- Date: 2026-08-22
- Base: the preceding streaming-final request-budget repair commit
- Implementation: the commit containing this record,
  `fix(live-voice): enforce one browser capture owner`
- Risk: Tier 3 under root `TESTING.md`
- Disposition: **SOURCE/AUTOMATED/SCOPED TWO-TAB PHYSICAL PASS; CORRECTED
  SAME-TAB RERUN AND INDEPENDENT TIER-3 REVIEW OPEN**
- Owners changed: same-origin browser capture ownership, Formal Live Voice
  enable/Exit/retry admission, losing-tab cleanup and exact cleanup-failure
  propagation

This is the third independent bug boundary. It does not redefine the same-tab
Task A -> B -> A capture-admission repair or the streaming-final request budget.
It does not restore the unrelated manual stop-and-recognize fallback from
`fde28d449`, any speculative long-lived authority renewal, or the discarded
exploratory history of `4c7d5af69`.

## Reproduction and root cause

The reproduced scenario used two browser tabs on the same JiuwenSwarm origin,
each displaying a different Task. Enabling Formal Live Voice in the second tab
left the first tab active, so both tabs captured the same physical microphone
and both continued their own Live Voice loops.

The product entry previously did this independently in every tab:

1. set the tab-local Live Voice UI to active;
2. call its local Formal P1 `start()` control.

There was no browser-global admission owner and no instruction for an existing
tab to generation-fence, close and release its microphone/media route. Session
isolation cannot solve that boundary because the conflict is between two page
processes sharing one physical input.

## Implemented contract

One same-origin browser profile now has at most one Formal Live Voice capture
owner:

- every explicit enable queues an exclusive, fixed-name Web Lock;
- BroadcastChannel sends a credential-free takeover claim to the held owner;
- the losing tab first marks its UI inactive and awaits its existing exact
  `close()` path, which fences the voice-loop generation, presentation, capture,
  timers, microphone, media socket and stale callbacks;
- only successful cleanup releases the lock, so the successor cannot start
  capture while the predecessor is still closing;
- a cleanup failure retains the lock and a later explicit takeover retries the
  exact cleanup instead of allowing overlap;
- claims use a monotonic browser timestamp plus an opaque tie-breaker, so a
  newer explicit enable supersedes an older queued/held claim while stale
  notices cannot evict the current owner;
- Exit and cross-tab takeover perform the complete current-surface `close()`
  before release. Same-tab Session replacement instead closes only the exact
  old-Session P1 owner before release, so a delayed parent cleanup cannot close,
  rotate or contaminate the replacement Session's P2 activation;
- failed old-Session cleanup retains its exact Session identity, and **Listen
  again** retries that owner before releasing/reacquiring the browser lock;
- a re-enable during takeover waits for release and returns as a new claim; and
- missing Web Locks or BroadcastChannel fails closed before microphone capture.

Web Locks also release automatically when a tab/process disappears. This packet
does not create a storage flag, heartbeat timer, backend lease or second media
authority.

## Red-first and automated evidence

Before implementation, the Formal Web command failed at compilation because
the required browser ownership module did not exist, and the ChatPanel oracle
showed direct tab-local start. The final focused owner suite covers:

1. successor start waits until predecessor cleanup completes;
2. failed cleanup retains the lock and explicit retry closes before takeover;
3. an older notice cannot revoke the current owner;
4. same-tab retry reuses one exact held owner;
5. re-enable during takeover returns only as a newer claim; and
6. missing Web Locks or BroadcastChannel has zero ownership/capture admission.

```text
node --test tests/browserLiveVoiceOwnership.test.mjs
6 passed, 0 failed

npm run test:live-voice-integrated-web
461 passed, 0 failed

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-gateway-media
38 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

pytest test_dedicated_media_registration.py test_product_streaming_synthesis.py
       test_live_voice_speech_rpc.py test_streaming_speech_route.py
       test_openai_streaming_speech.py
195 passed, 0 failed

npm run test:live-voice-build-profiles
2 passed, 0 failed

npm run build:live-voice
PASS

ruff check (P2/Registry product/test files)
PASS

pytest test_product_p2_interaction_adapter.py test_product_composition_registry.py
214 passed, 6 failed

git diff --check
PASS
```

The six P2/Registry failures are unchanged from the packet base: three P3
bounded/status cases, disconnect cleanup, in-flight query/stop and text-status
dispatch/projection. They retain the same `_P3Composition._accepting` fixture or
`PRODUCTION_TASK_AUTHORITY_PROJECTION_MISMATCH` causes. No Python source or test
changed in this packet, so `214/220` is disclosed rather than called PASS.

The production build retains its existing chunk-size/mixed-import warnings and
Formal Web retains its existing duplicate-locale warnings.

## Acceptance and non-claims

After deployment of the session-scoped cleanup correction, the user repeated
the scoped two-tab exclusivity rerun on the product code contained in this
commit on 2026-08-22:

1. enable and speak in Task A;
2. enable Task B and verify A becomes inactive before B listens;
3. speak once and verify only B recognizes/responds/plays;
4. re-enable A and verify B becomes inactive before A listens.

The user reported this forward and reverse takeover scenario **PASS**. That is
scoped physical credit for one-capture-owner behaviour only; it does not claim
a separate resource-zero measurement, different browser profiles, browsers,
devices or origins, server-wide multi-client arbitration, timeout policy,
Agent/Tool/Task semantics, presentation-ACK durability or launcher/provider
configuration.

The sanitized runtime window `21:12:42`–`21:15:21` shows two persistent browser
WebSocket owners, each bound to its own Session, alternating takeover in both
directions. It contains zero `REQUEST_TIMEOUT`, `FORMAL_P1_CLEANUP_PENDING` or
`live_voice_media_authority_refresh_failure` observations. One final
caller-cancelled Provider socket reported retained cleanup, so this run does not
claim backend resource-zero or the physical failed-cleanup retry branch.

An earlier separate one-tab investigation exposed a distinct integration race:
after Task A -> B replacement, the parent Session effect could invoke complete
`close()` through the already-updated B control. Logs show the new Session's P2
activation succeeding and then being closed tens to hundreds of milliseconds
later. The repaired parent path retains the previous Session id and invokes the
new session-scoped P1 cleanup only. A mounted oracle holds A's media close open,
activates B, invokes the late A cleanup and proves zero B P2 close/rotation plus
one B successor microphone after A settles. This repeated run used two browser
tabs; it does not close the post-repair one-tab Task-switch acceptance. That
rerun and independent Tier-3 review remain open.
