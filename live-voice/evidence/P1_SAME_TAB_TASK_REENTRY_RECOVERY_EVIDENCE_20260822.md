# P1 same-tab Task re-entry capture recovery evidence

## Boundary and disposition

- Date: 2026-08-22
- Base: `b016c14c0168c38757d716bc437ffe874a3a3cdb`
- Implementation: the commit containing this record,
  `fix(live-voice): restore capture after Task re-entry`
- Risk: Tier 3 under root `TESTING.md`
- Disposition: **SOURCE/AUTOMATED PASS; PRE-REPAIR PHYSICAL FAIL OBSERVED;
  POST-REPAIR PHYSICAL RERUN AND INDEPENDENT TIER-3 REVIEW OPEN**
- Owner changed: the Formal P1 capture-admission seam after an exact P2 owner
  becomes active during same-tab Session/Task recovery

This packet does not change Agent, Tool, Task, presentation-ACK durability,
Dedicated Media authority TTL, capture rotation, Speech timeout policy,
provider selection, credentials, launcher configuration or cross-tab ownership.

## Corrected reproduction

The user used one browser tab, not two. Task/Session A completed its current
voice interaction normally, the same tab navigated to Task/Session B and used
Live Voice successfully, and the same tab later returned to A. A then exposed
`语音连接恢复失败`; **Listen again** could not restore capture.

The recovery log for Session A shows:

- generation 2 replayed at `16:52:10.439`;
- its retained media route opened at `16:52:11.200`;
- generation 2 closed at `16:52:12.189`;
- generation 3 activated at `16:52:12.254`;
- no generation-3 media/capture start followed.

The earlier claim that a `16:28:58.484 connection closed` line proved a
15-minute Dedicated Media authority expiry is withdrawn. That generic Web
transport close occurred while the same browser surface was routing Session B,
and the runtime log contains no `MEDIA_PRODUCT_ACTIVATION_UNTRUSTED` rejection.
It cannot support a long-lived authority-renewal root cause for this incident.

## Root cause and invariant

`startProductVoiceCaptureOwned` already reads the authoritative activation-owner
snapshot and verifies exact Session, correlation, interaction, activation id
and activation generation. It additionally required the rendered React
`p2Activation.status` to be `active`.

During recovery, the owner can become authoritatively active before React
publishes the corresponding rendered state. The only scheduled capture then
returns early and is not rescheduled, which exactly explains an active
generation 3 with no media start.

The repair removes only that redundant rendered-state gate. Exact owner,
Session/generation, capture barrier and resource-cleanup checks remain. This is
the valid source invariant originally explored in `4c7d5af69`; the exploratory
commit, its incorrect browser attribution and unrelated changes are not
restored.

## Follow-up integration race and corrected invariant

The later browser-global capture-owner integration exposed a second same-tab
race during the user's corrected A -> B run. P2 activation itself succeeded,
but the `ChatPanel` Session effect read the mutable current surface control
after the child had already rerendered for B. Its complete `close()` therefore
targeted B instead of only settling A. Runtime logs repeatedly show this shape:

- replacement Session generation 1 activates successfully;
- tens to hundreds of milliseconds later that same generation is closed; and
- a successor generation activates, while the UI can remain failed and
  **Listen again** collides with retained cleanup.

The corrected invariant separates two teardown scopes:

- Exit and cross-tab takeover retain complete current-surface close;
- same-tab Session replacement retains the previous Session id and closes only
  the P1 owner that was created for that exact Session;
- the scoped close never reads, refreshes or closes the successor P2 owner;
- cleanup failure retains the old Session id and browser lock, and **Listen
  again** retries that same old owner before successor admission; and
- a start path also rejects/revokes any retained P1 owner whose recorded Session
  differs from the exact current activation binding.

## Red-first and automated evidence

The source oracle requires capture admission to:

- read `activationOwnerRef.current?.snapshot()`;
- require the authoritative snapshot to be active;
- match the current binding generation; and
- contain no `p2Activation.status` rendered-state dependency.

The oracle fails on the packet base and passes with the one-line repair.
Existing mounted Tier-3 scenarios also pass for exact old-Session close fencing
and same-tab retained-activation cleanup before successor capture.

The added mounted integration oracle deliberately holds A's media close open,
allows B's P2 activation to complete, then invokes the late parent cleanup for
A. It proves zero B P2 close/rotation and exactly one B microphone/media start
after A settles.

```text
node --test --test-name-pattern="successor capture admission uses the authoritative activation owner|mounted same-tab refresh stays fail-closed|mounted P1 retained Start cannot allocate an old-binding successor after Session replacement|mounted late old-Session capture cleanup" tests/liveVoiceIntegratedRoutePanel.test.mjs tests/liveVoiceIntegratedRoutePanelMounted.test.mjs
4 passed, 0 failed

npm run test:live-voice-integrated-web
461 passed, 0 failed
```

At the three-commit integration boundary, browser audio `103/103`, Gateway
Media `38/38`, browser Dedicated Media `27/27`, build profiles `2/2`, the
production Live Voice build and Git diff checks also pass. Backend source is
unchanged; its preceding Speech/Media `195/195`, Ruff PASS and disclosed
P2/Registry `214/220` baseline remain recorded in the browser-owner evidence.

## Review and non-claims

The corrected physical acceptance is one tab following A -> B -> A. Task A
must acquire a fresh authoritative generation and capture on return; stale A
or B work must produce zero cross-Session visible/audio/business effect.

The corrected pre-repair physical attempt is explicitly **FAIL**: switching
Tasks sometimes produced `语音连接恢复失败`, and **Listen again** did not recover.
No post-repair physical PASS or independent Tier-3 review is claimed. This
packet does not claim a 15-plus-minute continuous-listening repair; the separate
streaming-final request-budget and browser-global single-owner contracts retain
their own boundaries and evidence.
