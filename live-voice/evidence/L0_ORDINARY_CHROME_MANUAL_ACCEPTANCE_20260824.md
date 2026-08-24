# L0 ordinary Chrome manual acceptance — 2026-08-24

## Scope, source and disposition

- Capability: bounded L0 manual functional acceptance under
  [D-095](../decisions/DECISIONS.md).
- Tested source: `362403cd6c6671b04d4c4129019047bf81df1d53` on
  `hx/0812_live_voice_w3`, clean and equal to its configured upstream before the
  documentation-only closeout commit.
- Browser and page: the operator used an ordinary installed Chrome window on the
  local Integrated Web page for Session `web_1a034feac64_9781824cb619`. No
  isolated Chrome profile was launched for this manual session.
- Runtime: `formal-web-validation`, disposable no-remote Git project, Direct D2
  executor profile and configured real Speech Provider round trip. The runtime
  contract passed before acceptance and retained no credential in this record.
- Operator result: **BOUNDED BASIC FUNCTIONAL PASS — 8/8 scenarios**, including
  real microphone input, audible short and longer responses, continuous turns
  and a real terminal Tool call. The operator also confirmed that button
  interruption, voice interruption and playback Stop followed by Exit had the
  expected visible/audible effect.
- D-095 result: **MANUAL DELIVERABLE PARTIAL; OVERALL L0 MEASUREMENT CLOSURE
  OPEN.** The session does not positively prove formal Task create/status
  completion, explicit silence rejection, or an authoritative successful
  server-side `barge_in`. The required independent cold/warm scripted series and
  sanitized aggregate were not run.

The 8/8 result is the operator's bounded product-journey judgement. Durable
runtime and Store evidence corroborates the requests and responses but cannot
independently prove what was physically audible. Conversely, a user-visible
effect does not override a server-side error or turn an Agent-internal todo into
a formal P3 Task.

## Preconditions and evidence boundary

The launcher contract recorded the exact clean source, formal profile, required
Live Voice flags, configured Speech Provider round trip and a disposable project
with zero remotes. The browser session then used the real microphone, Agent,
terminal Tool, TTS and WebAudio path. Raw logs, runtime databases, history,
recognized text and machine-private paths remain local and ignored.

The committed report retains only the minimum identities needed to correlate the
session. It does not retain credentials, bearer tokens, private configuration,
raw audio, device identity or the disposable project path.

## Eight-scenario result

| # | Bounded scenario | Operator result | Durable corroboration and credit |
|---|---|---|---|
| 1 | Short factual dialogue | PASS | Unified committed input completed and produced response generation `0` through the formal Runtime/Agent route. |
| 2 | Longer constrained answer | PASS | Unified input completed and produced generation `1`; operator accepted the audible result. |
| 3 | Spoken topic change during the continuing session | PASS | ASR committed a final input and generation `2` completed. The recognized wording was imperfect, but the operator accepted the resulting behaviour. |
| 4 | Follow-up with an additional requested detail | PASS | Unified input completed and produced generation `3`. |
| 5 | Strict short-answer constraint | PASS | Unified input completed and produced generation `4`. |
| 6 | Explicit real terminal Tool request | PASS | Generation `5` completed; private Agent history contains the actual terminal invocation and branch-status result rather than a context-only answer. This grants bounded Tool-path credit. |
| 7 | User-visible task-like create-and-report request | PASS for the basic journey | Generation `6` completed and the Agent reported an internal todo/tool workflow. Store truth classifies the input as `dialogue / DIALOGUE_RESOLVED`; it created no formal P3 Task, so it grants no formal Task-path credit. |
| 8 | User-visible task-like status follow-up | PASS for the basic journey | Generation `7` completed and the Agent reported the internal todo status. Store truth again classifies the input as `dialogue / DIALOGUE_RESOLVED`; it grants no formal `task.status` credit. |

All eight unified journal rows are `completed`, with consecutive response
generations `0..7`. This supports the bounded 8/8 judgement and also explains
why that judgement must not be restated as 8/8 formal background Tasks.

## Interruption and lifecycle observations

- The operator first exercised button interruption and voice interruption and
  confirmed that both stopped or replaced the audible/visible response as
  expected.
- The operator then repeated three focused journeys: button interruption, voice
  interruption, and playback Stop followed by Exit. All three had the expected
  user-visible effect.
- The server log contains the corresponding P2 `barge_in` and `close` traffic,
  including the final close immediately after the last playback stop.
- Every `barge_in` unary response in this runtime log is nevertheless recorded as
  `e2a.error`. The INFO record contains no error code or reason. Cancellation
  cleanup also emitted `STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` and retained-
  transport diagnostics on some close/interrupt paths.

The interruption result is therefore **operator-visible PASS, authoritative
server acknowledgement NOT PROVEN**. It is not eligible for the D-095 dedicated
barge-in series or its `stop_to_silence_ms` percentile.

## Formal Task follow-up and recovery observation

A later, explicit “background task” formulation did route to
`background.create` and durably created one formal Task. Store truth records
`accepted -> running -> terminal/failed` with
`NO_EFFECTIVE_TARGET_CHANGE`. The subsequent natural-language status question
routed to `dialogue / DIALOGUE_RESOLVED`, not to formal `task.status`.

At the same time, task audio reported `task_audio_playout_failed`. The retained
`presentation.failed` retry reused its request ID and entered a Gateway unary
wait that eventually timed out at 600 seconds. This corresponds to the page
remaining in “recovering”. These facts are diagnostic follow-up, not successful
positive Task-path acceptance. They are recorded independently in the
[known-issues review](../reviews/L0_ORDINARY_CHROME_KNOWN_ISSUES_20260824.md),
and no implementation or configuration fix is included in this closeout.

## D-095 closure mapping

| D-095 conjunctive deliverable | Result on `362403cd6c` | Remaining evidence |
|---|---|---|
| One complete ordinary-Chrome manual session | **PARTIAL** | Basic dialogue, short/long output, continuous turns, Tool and user-visible interrupt/Stop/Exit behaviour passed. Explicit silence rejection, positive formal Task create/status completion and authoritative successful server-side barge-in are not proven. |
| Warm and cold scripted series | **NOT RUN** | Each temperature still needs at least 20 eligible first-audio and 20 eligible dedicated barge-in samples under the accepted runner contract. |
| Sanitized counts and p50/p95 aggregate | **NOT RUN** | Counts, failure/drop classification, both required Browser digital metrics and cold/warm comparison remain absent. |
| Overall L0 engineering measurement closure | **OPEN** | D-095 requires all three deliverables on one accepted source plus applicable automation and risk-proportional review. |

This result does not change feature-complete, controlled-candidate, Production,
release or remote-ref status. It also claims no strict physical acoustic p95,
AEC/double-talk, device/room generalization or release stability.

## Raw evidence inventory

The following ignored, machine-local artifacts were reviewed but are not added
to Git:

- runtime contract: `logs/live_voice_runtime_contract.json`;
- runtime log: `logs/swarm-20260824-193521.log`;
- unified committed-input and formal Task SQLite stores under the disposable
  runtime data directory;
- private Agent session history for `web_1a034feac64_9781824cb619`.

No scripted D-095 physical cold/warm capture directory or same-source sanitized
aggregate was present. Historical injected and Provider-component L0 JSON files
remain governed by the earlier
[measurement baseline evidence](L0_MEASUREMENT_BASELINE_EVIDENCE_20260823.md)
and receive no physical or D-095 closure credit here.
