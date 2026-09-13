# P1 same-tab Task re-entry capture recovery evidence

## Boundary and final disposition

- Date: 2026-08-22; consolidated 2026-08-23
- Baseline: `2e01965ecd89a33ca5917cdad1c1080018bb8b1b`
- Consolidated implementation:
  `e284bdec4` (`fix(live-voice): restore capture after Task re-entry`)
- Risk: Tier 3 under root `TESTING.md`
- Gate: **PASS — `C0 / I0 / M0`**
- Physical credit: pre-repair failure reproduced; corrected exact-tree one-tab
  Task A -> B -> A PASS
- Remaining scoped physical acceptance: none

This boundary owns capture admission and recovery-state isolation when one
mounted browser surface changes Session/Task. It does not change Agent, Tool,
Task, ACK durability, Speech timeout, Provider selection, capture rotation,
launcher configuration or cross-tab ownership.

## Reproduction and root causes

The user used one tab: Task/Session A completed normally, the same tab moved to
B and used Live Voice, then returned to A. A displayed
`语音连接恢复失败`, and **Listen again** did not restore capture.

Three related same-tab seams were closed:

1. Recovery activated an authoritative P2 successor before React published its
   rendered `active` state. Capture admission also required that lagging
   rendered state, so the only scheduled successor start returned early and was
   never rescheduled.
2. Browser ownership integration let the parent Session effect read the already
   replaced mutable surface control. Late cleanup for A could therefore call a
   complete close on B instead of closing only A's exact P1 owner.
3. If A's exact P2 close exhausted retry after B became current, the shared
   diagnostic publisher could project A's recovery identity into B. B could be
   active while its visible recovery UI still referred to A.

The earlier 15-minute Dedicated Media expiry attribution is withdrawn. The cited
log line was a generic Web transport close while routing another Session, with
no matching media-authority rejection.

## Final invariant

- capture admission uses the authoritative activation-owner snapshot and exact
  Session/correlation/interaction/activation generation, not lagging rendered
  `p2Activation.status`;
- Session replacement retains the previous Session id and closes only the P1
  owner created for that Session;
- Exit and cross-tab takeover retain their complete-surface cleanup semantics;
- cleanup failure keeps the exact old Session/owner for retry before successor
  admission;
- a retained P1 owner whose Session differs from the current activation is
  rejected/revoked; and
- a recovery diagnostic with an explicit binding publishes only while that
  binding's Session is the current active Session. Binding-less current-route
  diagnostics retain their existing behavior.

Late A cleanup/callbacks therefore have zero B recovery-UI, P2, capture,
history, TTS, Agent, Tool or Task effect.

## Review closure

| Review HEAD | Result | Finding | Closed at |
|---|---|---|---|
| `a640ce97e78173a7f7764ccec29efd4db014c892` | FAIL `C0/I1/M0` | exhausted old-Session P2 cleanup could publish A's diagnostic after B activated | `c9ff11e460dd588b23b1761bf7609c446a208741` |
| `c9ff11e460dd588b23b1761bf7609c446a208741` | PASS `C0/I0/M0` | no finding; exact Session diagnostic fence and mounted production Panel accepted | — |

The final review confirmed that the Session comparison occurs before
diagnostic construction/state publication and is mutation-sensitive. The
production boundary is frozen.

## Automated evidence

The source and mounted oracles cover authoritative-owner admission, retained
old-Session cleanup, late parent cleanup, bounded old P2 close failure, zero
cross-Session diagnostic and final null B recovery state. Removing the
diagnostic Session fence deterministically makes the mounted oracle RED.

```text
focused same-tab production/source oracles
5 passed, 0 failed

npm run test:live-voice-integrated-web
466 passed, 0 failed on the rewritten consolidated product/test tree

npm run test:live-voice-browser-audio-io
103 passed, 0 failed

npm run test:live-voice-browser-dedicated-media
27 passed, 0 failed

node --test tests/liveVoiceBuildProfiles.test.mjs
2 passed, 0 failed

npx tsc --noEmit
PASS

npm run build:live-voice
PASS
```

Backend Speech/Media independently passes `195/195`. P2/Registry remains
truthfully disclosed as `214/220` with six unrelated P3 fixture/projection
failures; no backend file changed in this module. Existing duplicate-locale,
mixed-import and chunk-size warnings are unchanged.

## Physical evidence and non-claims

The corrected pre-repair A -> B -> A attempt remains the physical **FAIL**
reproduction. On 2026-08-23 the user repeated the journey in one tab on the
exact consolidated product/test tree: A recognized/answered/played, B did the
same, and returning to A established a fresh capture and completed another
response without stale A/B visible or audio effects. Runtime logs contained
zero `REQUEST_TIMEOUT` or recovery-failure event.

This module does not claim a continuous 15-plus-minute listening repair or a
real >15-second Provider-final degradation/fallback result.
