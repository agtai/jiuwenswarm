# P2 stock-Web real Agent/Tool evidence: 2026-08-07

## Conclusion

- Result: `PASS` for one bounded committed-text P2 journey on immutable source `fb40f12b46fd3c407314c66055bf99911bc35267`.
- Proven path: stock desktop Web formal P2 control -> Gateway -> AgentServer -> real JiuwenSwarm Agent/Harness -> real DeepSeek model -> two real Bash/Git tool calls -> exact final text -> presentation acknowledgement -> formal history -> terminal/close cleanup.
- Scope: this run closes no P2/product scope, makes no Integrated Demo or Alpha Gate claim, and grants no Replacement Ledger credit. See [STATUS.md](../STATUS.md) for current mutable state.
- Privacy: credentials, API base, bearer value, raw browser frames, and raw service logs remain outside Git. Only sanitized identities and outcomes appear here.

The tested branch was `codex/lv-p2-real-e2e-hardening`. Its parent hardening commit was `0ac21ce40a8bdd077be98d87cfdcd3a7cd3187a2`; the tested tip adds the reviewed passive `tracer_agent` filter and focused regression test. Neither commit was pushed by this run.

## Environment and immutable identities

| Item | Sanitized fact |
|---|---|
| OS / carrier | Windows / JiuwenSwarm desktop Web frontend |
| browser | Google Chrome `151.0.0.0`, platform `Win32` |
| application source | `fb40f12b46fd3c407314c66055bf99911bc35267` |
| model | `deepseek-v4-flash` through the configured DeepSeek provider |
| isolated runtime | basename `.jiuwenswarm-live-voice-p2-20260807` |
| retained raw-log set | basename `e2e-logs-formal-p2-immutable-fb40f12b-formal-20260807-160951` |
| disposable project | basename `live-voice-p2-e2e-project-20260807` |
| project HEAD | `4e2b1d7d54d9972b8a1a19a5881c9403e3a604bc` |
| project identity | `proj_d57d502e` |
| persistent Session | `sess_19fdbf71d54_98f3b1f5805c` |
| formal interaction | `web-interaction-integrated-web-r1` |
| formal round | `round-b73b59b08f53d6378178f2ffb5c89c4e` |

The exact application and disposable-project worktrees were clean before the formal journey. The disposable project remained on the same HEAD and clean after it. Runtime services listened only on the isolated local ports `18092`, `19000`, `19001`, and `5173`; all four listeners were stopped after capture.

The model TLS check was temporarily enabled for the real call at the user's direction. After capture, the isolated default model was restored to `verify_ssl: false`; the main and isolated configurations both reported `deepseek-v4-flash` with that restored value. No private model configuration is Git evidence.

## Browser and route facts

- The test used `http://127.0.0.1:5173` on a localhost-controlled origin. Chrome reported `isSecureContext=true`, and the UI summarized the transport as secure because localhost is a browser secure-context exception. This is **not** deployed HTTPS/WSS, reverse-proxy, TLS-certificate, CSP/CORS, or exact public-origin evidence.
- Microphone permission remained `prompt`; input and output devices were enumerated; autoplay required user activation; the page was visible, not discarded, and online. The AIO foundation reported capture/playout available but `wired:false`.
- The cumulative route banner remained unsupported because P1 and P3 were not formal. The P2 product-composition segment independently reported `formal`, with trusted Authority, an open activation lease, observed runtime path, and closed notification backpressure.
- The server-held bearer and allowlisted project were supplied only through runtime configuration. They are not present in this record.

## Formal journey

All timestamps below are UTC on 2026-08-07.

| Time | Observation |
|---|---|
| `14:10:33.900` | Web sent `live_voice.composition.p2.activate`. |
| `14:10:38.818` | Activation returned `active`. |
| `14:12:02.949` | The dedicated formal P2 control sent `live_voice.composition.p2.submit`. |
| `14:12:04.478` | Submit returned `round_accepted`. |
| `14:12:15.763`–`14:12:16.255` | Formal notifications delivered two `chat.tool_call`, two `chat.tool_update`, and two `chat.tool_result` events, all without an event error. |
| `14:12:23.283` | Formal notification delivered `chat.final` with one text presentation unit. |
| `14:12:23.286` | Web sent the exact `live_voice.composition.p2.presentation.ack`. |
| `14:12:24.490` | The acknowledgement returned `presentation_acknowledged`, `history_records_written=1`, and `history_pending=false`. |
| `14:12:24.592` | The terminal progress notification reported `state=terminal`, `outcome=completed`; its harness source event was `round.terminal`. |
| `14:14:08.215` | Selecting New Chat sent `live_voice.composition.p2.close`. |
| `14:14:08.339` | Close returned `closed`. |

The committed text required the Agent to execute exactly:

```text
git rev-parse --short HEAD
git status --short --branch
```

The AgentServer log records both Bash executions against the disposable project. The Web-facing formal stream proves the ordered sequence `tool_call, tool_update, tool_call, tool_update, tool_result, tool_result`; it does not expose stable tool-call IDs for one-to-one Web pairing. The normalized semantic oracle from the final was:

```text
short_sha=4e2b1d7
branch=master
worktree=clean
modified_files=0
```

Independent Git verification after the run returned full HEAD `4e2b1d7d54d9972b8a1a19a5881c9403e3a604bc` and an empty short status on branch `master`.

The reused persistent Session history contains this round's formal committed-user record bound to the exact `turn_id`/`commit_id` and the exact final record bound to the acknowledged `response_id`, text unit, cursor, and `content_ref`. The acknowledgement confirms that one final record was written and no history write remained pending. Tool trace/reasoning payloads were not copied into these two formal records. This does not claim that every older record in the reused Session belongs to a successful or complete round.

## Isolation from compatibility traffic

The same retained service process also saw an earlier normal `chat.send` at `14:10:48.745`. That compatibility request has its own request ID and ordinary history records and is excluded from formal P2 credit.

The credited formal sample is isolated by all of the following:

- a later, distinct `live_voice.composition.p2.submit` request ID;
- a distinct formal commit/turn/response binding;
- a distinct formal round ID;
- a second observed pair of Bash/Git executions after formal submit;
- formal notification sequences for both tool lifecycles and the final;
- exact presentation ACK, formal history binding, terminal progress, and explicit P2 close.

Two earlier startup attempts are also excluded: one never made a request after invalid local token generation, and one omitted the formal P2 Authority-provider flag and therefore used only compatibility traffic. Neither contributes evidence here.

## Failure-signal and regression checks

Within the credited formal submit-to-terminal window, structured P2 RPC errors, Agent error events/error reasons, failed terminal outcomes, notification errors, acknowledgement errors, compatibility `chat.*` envelopes, task failures, and user-process cancellations were all zero. Across the retained exact-process logs, the following formal rejection/detachment/history failure signals had zero matches:

```text
output_detached
FORMAL_EXECUTION_EVENT_UNSUPPORTED
formal execution rejected
sequence mismatch
history write failed
presentation ack failed
```

Closing the activation then produced one expected `NOTIFICATION_STREAM_CLOSED` to release a pending notification poll. Post-close navigation also attempted a new placeholder-Session activation and task query that were denied by Authority. An earlier compatibility TTS request returned `ok=false`. These post-round/cross-route observations do not invalidate the completed formal P2 round, but they prohibit any claim that the entire browser process or all product routes were error-free.

The focused formal-adapter regression suite passed:

```text
tests/unit_tests/agentserver/test_formal_live_voice_adapter.py
16 passed, 1 third-party Authlib deprecation warning
```

The added regression proves that a raw passive `tracer_agent` payload is dropped without entering a formal response while normal answer/final delivery remains intact. Existing malformed, unknown, active unsupported, cleanup, and no-history guards in the same file remained green. Focused Ruff passed with the file's pre-existing `E402` baseline excluded; raw Ruff continues to report only that existing import-order baseline. `git diff --check` passed apart from informational Windows line-ending warnings. Implementation self-review, cold complete-diff review, and an independent equivalent review all returned no actionable finding.

The immediately preceding immutable candidate `0ac21ce40a8bdd077be98d87cfdcd3a7cd3187a2` is retained as a failed diagnostic sample: a raw internal `tracer_agent` event was treated as unsupported, the formal execution rejected, and its tool output detached. A later dirty-worktree diagnostic proved the filter direction but was not immutable. Only the clean `fb40f12b` rerun above receives this bounded PASS.

## Explicit limits and follow-up

This record proves one authenticated, single-turn, committed-text P2 vertical. It does not prove:

- microphone capture, Speech recognition/synthesis, Media transport, playout, or P1;
- P3 Task Core, Code Executor, voice handoff, or a joint P2/P3 journey;
- production identity/authorization or Provider authority;
- a registered X-OBS backend, exporter, retention/redaction policy, or SLO;
- deployed HTTPS/WSS, reverse proxy, public origin, CSP/CORS, or TLS operations;
- cancel, barge-in, reconnect/refresh recovery, faults, notification saturation, 256-turn rollover, or multi-Session concurrency;
- the complete D-032 matrix, Integrated Demo acceptance, Web Alpha acceptance, or the Immutable Alpha Gate.

The raw AgentServer log was not error-free: Windows console handlers emitted non-fatal `UnicodeEncodeError` diagnostics for Chinese tool descriptions, and framework resource-registration diagnostics also appeared during startup/runtime logging. The two Git tools and structured P2 business path nevertheless completed successfully. These diagnostics remain observability/operability follow-up and are not evidence of an all-service clean run.

This evidence leaves the P2 product scope incomplete and grants no replacement credit. See [STATUS.md](../STATUS.md) for current Gate and ledger state.
