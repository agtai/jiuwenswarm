# OpenAI Realtime Native physical human foreground acceptance — 2026-09-01

## Disposition

The bounded physical-device and human-acoustic foreground Gate is **PASS** on
exact runtime source `b54730170bc560933c6b345fb984b843295282de` from branch
`codex/openai-realtime-native-interaction-engine`.

An operator used an ordinary installed Chrome window, a real microphone and
audible browser playout with `openai-realtime-native` and
`gpt-realtime-2.1-mini`. The same foreground session passed activation and
first audio, continuous turns, one playback-time voice interruption whose new
utterance was understood without repetition, one safe read-only Jiuwen Agent
delegate, and Exit followed by immediate re-entry and another audible answer.

This closes only the Native packet's previously `NOT_RUN` physical
device/human foreground class. It does not upgrade P3-9, the controlled product
candidate, feature completeness, Production readiness or the separately
deferred strict physical-acoustic/latency/generalization boundaries.

## Run identity and environment

- Runtime source: `b54730170bc560933c6b345fb984b843295282de`.
- Branch: `codex/openai-realtime-native-interaction-engine`.
- Runtime profile: `formal-web-validation` with a passing credential-free
  runtime contract and clean source at launch.
- Interaction Engine/model: `openai-realtime-native` /
  `gpt-realtime-2.1-mini`.
- Browser/origin: ordinary installed Chrome at `http://localhost:5273`.
- Session: `web_1a059e481ba_c5c01af3266b`.
- Project: one registered disposable no-remote Git project bound by the
  launcher contract.
- Witness: the operator explicitly accepted the complete bounded minimum
  journey after hearing and observing every scenario.

The Chrome version, microphone/headset identity, room conditions and raw
speech are intentionally not retained. Their absence prevents a broader
compatibility, device or acoustic-quality claim.

## Bounded scenario result

| Scenario | Operator result | Runtime/browser corroboration and credit |
| --- | --- | --- |
| Activation and Native first audio | **PASS** | The authorized project activated the Native descriptor, committed real microphone input and rendered an audible Native response. |
| Continuous two-turn dialogue | **PASS** | Two successive spoken turns were committed and answered without another button activation or page reload. |
| Playback-time voice interruption | **PASS** | The operator heard the predecessor stop, observed the interrupting utterance commit, and received the new answer without repeating it. The predecessor downlink closed, the successor Native audio was served and its presentation was acknowledged. |
| Safe Jiuwen Agent delegate | **PASS** | The existing Agent Bridge performed a read-only project-file lookup and returned the expected first README heading. The private log records the real file search/read operations; no fake or context-only answer is credited. |
| Exit, cleanup and immediate re-entry | **PASS** | The foreground route closed, Live Voice became available again, a new short microphone turn received an audible answer, and the final route closed cleanly. |

The acceptance window contains matching Native audio-served and presentation
ACK observations, zero `NATIVE_DELEGATE_AGENT_TIMEOUT` events and zero
Native/Native-media error codes. Generic optional Agent-workspace file probes
remain outside this Native result and did not prevent the accepted journey.

## Authority, isolation and side effects

- The safe delegate was read-only. The disposable fixture's tracked worktree
  remained unchanged; one pre-existing untracked fixture artifact remained
  present and receives no acceptance credit.
- The JiuwenSwarm source worktree remained clean at the tested source.
- The concurrent P3-9 listeners on ports `5173`, `18092`, `19000` and `19001`
  retained their original processes while the Realtime listeners used `5273`,
  `18192`, `19100` and `19101`.
- No background Task, Task mutation, product-readiness journey or public
  deployment was invoked by this bounded foreground run.

One post-re-entry short utterance displayed a character-level transcription
mismatch while preserving the intended arithmetic meaning and producing the
correct audible answer. The operator accepted the semantic journey. This is a
non-blocking ASR observation, not pronunciation accuracy, fixed-corpus or
language-generalization evidence.

## Explicit exclusions

This record does not claim:

- fixed-corpus or p50/p95 physical latency;
- AEC, echo, double-talk, noise, room or device generalization;
- Provider outage/fallback, network degradation or reconnect recovery;
- background Task, P3-9 or combined hands-free product acceptance;
- browser/OS compatibility beyond the observed local Chrome run;
- Production security, tenancy, SLO, retention, deployment or release status.

## Private evidence inventory

The following ignored machine-local artifacts were reviewed but are not added
to Git:

- `logs/live_voice_runtime_contract.json`;
- `logs/swarm-20260901-000307.log`;
- the ordinary-Chrome page and user-visible session history;
- private runtime databases and Agent history.

No credential, bearer token, raw audio, device identifier or verbatim spoken
prompt is committed in this evidence.
