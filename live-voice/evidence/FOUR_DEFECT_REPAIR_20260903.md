# Four-defect rehearsal repair, 2026-09-03

## Scope and source

User-authorized targeted repair of foreground model latency, media attachment
recovery, material-defined scenario time, and truthful Task receipts. This is a
scoped repair checkpoint, not complete-product or human acceptance.

Base HEAD: `87248911fde2220be6a97f72f8c0210ac67d5b67`. The pre-existing working
candidate is retained. Machine-private evidence directory:
`C:\Users\admin\AppData\Local\Temp\live-voice-four-fixes-20260903`.
`baseline.json`, `before/`, `incremental.diff` and `tested-source.json` identify
the inherited files and this repair. No provider configuration or credentials
are copied; model configuration is read in place.

## Changes and verification

- Extend verified per-invocation non-thinking options from receipts to the
  isolated formal file-using Agent. Saved model/provider configuration and
  background execution keep their configured behavior. Tool authorization is
  unchanged.
- Pass the committed formal envelope directly, without the ordinary chat
  machine-time wrapper or duplicated policy text. Replace only the isolated
  Agent's written-deliverable output section, restore it on settlement, and
  stop ResponsePromptRail from overwriting it before every model call.
- Prefer explicit material-defined scenario clocks over runtime metadata.
  Explain create/query receipts from actual states; accepted/queued, running
  and terminal/completed remain distinct. No domain or phrase classifier,
  fixture timestamp/file name, canned business result or Task bypass was added.
- Retry a failed numeric-loopback media TCP connection once, before HTTP
  upgrade/authentication/media bytes are sent. Each connect is bounded to one
  second, within the browser's existing three-second attach window. Hostname,
  remote and nonmedia connections keep their existing policy. A disconnected
  browser no longer produces a secondary write-error traceback.
- Retry an initial attach timeout once after exact predecessor cleanup. Exit,
  session, activation and loop-generation fences remain effective. Retrying
  listening never resubmits an utterance or repeats a Task operation.

Focused Python checks: 38 passed (`python-final.log`), followed by 5 passing
prompt/facade/model checks including 2 new dynamic-output regressions
(`prompt-verified.log`). Frontend: 9 selected mounted cases passed
(`web-final.log`): transient recovery, persistent failure, Exit during cleanup,
authority rejection, generation interruption, session switching, feature-off
and stale Task ACK settlement. The first recovery fixture omitted the required
EOT capability and failed before opening a socket; corrected fixtures exercise
the actual attachment timeout, with failure logs retained.

TypeScript and the Live Voice production build pass. Focused Ruff comparison
against each inherited file reports no added findings; 7 pre-existing app_web
and 1 interface.py findings remain (`ruff-comparison.json`). Git diff whitespace
check passes. No full suite or full Demo was run.

## Real-provider results and limits

`real_probe.py` and subsequent bounded probes use the actual formal facade,
configured model and real project file tools in disposable no-remote projects.
Task receipt inputs are explicit test fixtures: they verify model narration,
not new Task execution, browser capture or audio playback. Model/tool outputs,
source files and timings remain in the private evidence directory. Project
files and saved provider configuration remained unchanged.

The last full analysis sample before the final receipt-only wording adjustment
(`verified-probe/real-probe.json`) took 15.328 seconds at the formal Agent seam.
It used the material's 16:00 scenario time and read the real project file.
This is **not** the same end-to-end metric as the earlier 49.404-second
committed-input-to-history observation and is not first audible output.

**Failed behavior is retained:** several analysis samples still exceeded the
spoken brevity target and made arithmetic/feasibility errors. In particular,
one answer put the departure deadline at 16:25 while omitting the required
30-minute station-arrival margin. These failures are not fixed by selecting a
shorter sample. Artifact arithmetic/fidelity and reliable concise analysis
remain open; this record does not claim a correct complete business journey or
stable few-second latency.

Final receipt-only samples (`receipt-state-probe/real-probe.json`) spoke
"后台任务已受理，文稿会生成，不会发送。" for the accepted fixture, and
"任务已完成。" for the completed fixture, with zero Tool events. Their Agent
seam times were 7.109s and 2.625s; these are not first-audio measurements. The
preceding receipt sample incorrectly said generation was underway for accepted
work; it is retained, and the last wording explicitly distinguishes those states.

The original TCP connect timeout's operating-system/network cause is not
proven: the old proxy traceback lacks request correlation. Tests prove bounded
recovery at the changed seams, not elimination of every network failure.

## Review and runtime handoff

The scoped incremental diff was reviewed locally against the recorded scope,
including zero repeated submission/Task effects, exact close-before-retry,
configuration isolation and ordinary-chat restoration. No independent review
was run in this turn; that gate and cumulative candidate review remain open.
No new commit or remote update was made; the inherited candidate is not split
into a knowingly incomplete commit merely to create a checkpoint.

The owned 6175 runtime is reloaded only after all four existing Tasks are
terminal. Before/after task/result/command and project-file fingerprints are
retained as `demo-before.json` and `demo-after.json`. Its source manifest and
process/readiness records identify deployment. HTTP returned 200 and two real unauthenticated media WebSocket upgrades through
port 6175 completed in 0.093s and 0.016s (`deployed-transport.json`); this does not
prove a microphone, media capability attachment, ASR or TTS. Final backend edits
preceded service creation at 14:12:31; the source record taken before the build
was preserved and synchronized after the build (`deployed-source.json`).
Physical microphone/speaker, full offline/ACK/A2 journey and new-source first-audio acceptance remain unrun.
