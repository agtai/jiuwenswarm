# Processing display and accepted-answer recovery repair — 2026-09-03

Disposition: **PARTIAL — bounded correction deployed; no full Demo or physical
acceptance credit.** The user authorized correction after three long spoken
questions appeared to return to listening in Session
`web_1a06779d66f_3cc112920518`.

## Source and scope

The baseline is HEAD `87248911fde2220be6a97f72f8c0210ac67d5b67` on
`hx/0812_live_voice_w3`, ahead 7 / behind 0 at handoff. The inherited candidate
is preserved; no commit, history operation or push was performed. Six product
files and two frontend test files changed relative to this repair's private
backups. The sorted product path/hash map has SHA-256
`4bcbfe3fa8f85c894f7248d30ff3360e663431473a0f4f6c72846ffa8a21d125`.

Private evidence is under
`C:\Users\admin\AppData\Local\Temp\live-voice-processing-state-repair-20260903`:
`before`, `before.json`, `repair.diff`, `final-product-manifest.json`, focused
test/build logs, `data-before.json`, `data-after.json` and `deployment.json`.

Tier 1 owns ChatPanel/DemoBar activity presentation and locale keys. Tier 2
owns the existing Integrated Web/P2 recovery boundary and exact close retry.
The behavior, surfaces and exclusions were recorded in STATUS before editing.
There is no new classifier, business phrase matching, domain-specific answer,
Task policy, schema, provider configuration or authorization expansion.

## Diagnosis and changes

All three historical long inputs reached the semantic dialogue path and real
Agent file reads. First/third P2 activations closed before their final answers;
the second answer was explicitly superseded by generation interruption and
the replacement was presented. Those historical close requests did not record
their caller origin. The first transcript also contained recognition errors.
Neither length rejection nor the exact first/third close source is proven.

The preceding repair placed `capturing` above `waiting` in the activity display.
That hid processing while the microphone listened for interruption. The shared
activity projection now shows processing with interruption available, preserves
speaking/error/recovery priority, and returns to ordinary listening after
processing settles.

A mounted reproduction held an accepted answer while disconnecting and
reconnecting the same page. Recovery could close the still-owned P2 response;
disconnect also destroyed the P1 playback owner. Preserving P2 alone still
failed to play the answer. The final repair retains an exact still-authorized
in-flight P2 response and silently releases an idle capture without destroying
its speaker owner. Reconnection wakes the existing guarded capture start.
Actual speech or failed release retains the existing cleanup path. Exit,
Session changes, explicit successor requests and unknown authority do not gain
permission to preserve stale output. This proves the reproduced path, not the
cause of an unlogged historical UI action or every possible reconnect timing.

P2 close requests now carry a bounded origin in the existing opaque request ID;
retries retain the same ID and first origin. Named paths distinguish Exit,
Session change, task redelivery, active recovery, unavailable route, native
closure and media authority failure; other owner cleanup has a default label.
No new wire parameter is introduced.

## Focused verification

From `jiuwenswarm/channels/web/frontend`, fresh targeted bundles preceded:

```text
node --test --test-name-pattern='formal activity distinguishes|mounted reconnect preserves an accepted|mounted TTS failure and ACK transport loss|mounted Exit during generation-time listening leaves|mounted Session switch during generation-time listening abandons|mounted generation interruption stays off|mounted generation interruption ignores the cancelled predecessor|P2 close retains its exact|panel recovery coordinator closes an idle poll' tests/liveVoiceIntegratedRoutePanelMounted.test.mjs tests/productWebActivation.test.mjs
```

**9 passed in 6.906 s.** The reproduction failed before the repair and after
only the P2 preservation change; its final form passes with an exact original
response ACK, one playback start, and zero duplicate submit, generation
interrupt, P3 mutation or P2 close. Other selected regressions cover real
generation replacement in the mounted harness, explicit Exit/Session fences,
feature-off behavior, TTS/ACK retry and idle closed-notification recovery.

`tsc --noEmit` and one Vite `build --mode live-voice` pass. The build enables
Integrated Web, P1, P3 mutation and generation interruption, matching the
retained rehearsal profile. Existing duplicate locale keys and large chunks
remain build warnings. No full suite, provider/model probe or physical
microphone/speaker test was run for this frontend correction.

Cold review covered the complete incremental product/test diff. No independent
review tool was available; self-review is the unavailable-tool substitute and
receives **no independent review credit**. Cumulative candidate review remains
open. The applicable risk checks cover the positive replay path and forbidden
effects under the selected failure, retry and scope-change conditions; this is
not process-crash or full multi-Task acceptance.

## Retained deployment

Only frontend assets were installed in the existing 6175 runtime. Old hashed
assets remain available to already-open pages; the new index was replaced last.
No backend process was restarted. Before deployment, all six changed product
files matched the prior runtime source at their private baseline; the only
other recorded source difference was STATUS.

HTTP for the original chat returns 200, and the served index and main script
hashes match the new build. The entry index SHA-256 is
`72e66cd2c3c192080c82ead840dee88aeb140441353081beabab862f224df8fe`.
The retained runtime's `frontend-source-processing-repair-20260903.json`
records this overlay without rewriting its preceding backend source manifest.
Read-only fingerprints confirm the original **6 Tasks**, attempts, results,
commands, Task/Executor events and business project files are unchanged.
Deployment verification did not consume a Task result notification.

Refresh the existing page to load this frontend. Recognition accuracy,
first-audio latency, recommendation/artifact quality and the complete
multi-Task/offline/revision journey retain their earlier open status. No
historical failure is retroactively granted a pass.
