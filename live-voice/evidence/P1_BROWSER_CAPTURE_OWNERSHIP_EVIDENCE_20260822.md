# P1 browser-global capture ownership evidence

## Boundary and final disposition

- Date: 2026-08-22; consolidated 2026-08-23
- Baseline: `2e01965ecd89a33ca5917cdad1c1080018bb8b1b`
- Consolidated implementation:
  `6cc613354` (`fix(live-voice): enforce one browser capture owner`)
- Risk: Tier 3 under root `TESTING.md`
- Gate: **PASS — `C0 / I0 / M0`**
- Physical credit: exact-tree ordinary forward/reverse two-tab takeover PASS
- Remaining physical non-claims: failure-injected/resource-zero paths

This boundary owns same-origin browser capture admission, explicit
Enable/Retry/Exit, losing-owner cleanup, Session replacement handoff and
cleanup-failure retention. It does not own Speech timeout policy, retained
presentation ACK durability, Agent/Tool/Task semantics or server-wide
multi-client arbitration.

## Root cause and final contract

Two same-origin tabs previously enabled Formal Live Voice independently. Both
could hold a microphone, Speech route and response/audio loop because admission
was tab-local.

The final contract establishes one capture owner per browser origin:

- every explicit enable mints a strictly newer claim and queues the fixed
  exclusive Web Lock;
- BroadcastChannel asks the held owner to close; stale claims cannot evict a
  newer owner;
- the successor starts only after exact predecessor cleanup and Web Lock
  release;
- cleanup failure retains the exact surface control, coordinator, lock and
  takeover callback, so retry is fail-closed rather than overlapping;
- pending -> pending re-enable aborts the older claim and preserves
  newest-explicit-enable-wins;
- Exit and cross-tab takeover close the complete current surface;
- same-tab Session replacement closes only the exact old-Session P1 owner;
- exact Session close, Web Lock release and cleanup-control handoff execute in
  one serial production barrier, and successor enable waits for that complete
  barrier before acquire/start;
- unmount retains the exact cleanup owner until cleanup succeeds, then disposes
  the channel only after lock release; and
- missing Web Locks or BroadcastChannel fails before capture.

The lifecycle lives in the production
`useProductVoiceBrowserOwnership` hook used by ChatPanel. The mounted oracle
executes that hook and injects only leaf coordinator/control gates.

## Review closure

| Review HEAD | Result | Finding | Closed at |
|---|---|---|---|
| `4c6af2f7436dd60466435b50136e61c1013c39c8` | FAIL `C0/I2/M0` | pending re-enable reused an old claim; failed unmount cleanup could lose the exact owner | `962a1b5b6515dd95f2bc66fb81eb7ec064d99f5c` |
| `962a1b5b6515dd95f2bc66fb81eb7ec064d99f5c` | FAIL `C0/I1/M1` | Session cleanup exposed completion before lock/control handoff; STATUS counts stale | `5d5bf24d947172079124a128c3f3a570eed533e3` |
| `5d5bf24d947172079124a128c3f3a570eed533e3` | FAIL `C0/I1/M0` | mounted test reimplemented the barrier instead of executing production wiring | `1a31cbf762768c751686012afcc5608ec0d03d9a` |
| `1a31cbf762768c751686012afcc5608ec0d03d9a` | PASS `C0/I0/M0` | no finding; production hook and mounted timing seam accepted | — |

The final review accepted P/N/B/S/T/C/R/I/F/K/X for this module seam and froze
the production boundary. Review follow-ups are folded into the consolidated
implementation commit; the historical HEADs remain evidence, not the current
branch shape.

## Automated evidence

The owner suite covers predecessor cleanup ordering, cleanup failure, stale
takeover rejection, same-tab retry, takeover re-enable, pending -> pending
newest claim, missing platform capabilities and exact successor cleanup.
Mounted production-hook coverage holds Session close and lock release
separately and proves zero successor start before complete handoff.

```text
node --test tests/browserLiveVoiceOwnership.test.mjs
7 passed, 0 failed

npm run test:live-voice-integrated-web
466 passed, 0 failed on the rewritten consolidated product/test tree

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-gateway-media
38 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

pytest focused backend Speech/Media
195 passed, 0 failed

npm run test:live-voice-build-profiles
2 passed, 0 failed

npx tsc --noEmit
PASS

npm run build:live-voice
PASS

ruff check (affected P2/Registry product/test files)
PASS
```

The independently rerun P2/Registry baseline was `214/220`: its six disclosed
failures were unrelated P3 fixture/projection cases, and no Python product/test
file changed in this module. Existing duplicate-locale, mixed-import and
chunk-size warnings remain non-findings.

## Physical evidence and non-claims

The user physically passed ordinary takeover in both directions:

1. A listened and responded;
2. enabling B made A inactive before B listened;
3. only B recognized/responded/played;
4. re-enabling A made B inactive before A listened.

This proves ordinary one-owner behaviour for the tested browser/origin/device.
It does not cover pending -> pending competition, forced cleanup failure,
SPA unmount/remount, crash recovery, separate resource-zero measurement,
different browsers/profiles/devices/origins or server-wide arbitration.

The 2026-08-23 final run repeated ordinary takeover on the exact consolidated
product/test tree. The user observed the losing tab stop listening before the
winner accepted speech, in both directions. The same run also passed corrected
one-tab Task A -> B -> A recovery. Runtime activation/close generations changed
with the handoffs and contained no `REQUEST_TIMEOUT` or recovery-failure event.
Injected pending competition, cleanup failure and independent resource-zero
measurement remain automation-owned/non-claims.
