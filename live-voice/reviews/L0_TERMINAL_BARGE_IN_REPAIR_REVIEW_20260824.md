# L0 terminal-response barge-in repair review — 2026-08-24

## Later L0 disposition — 2026-08-25

This review's terminal-response repair boundary remains PASS. D-097 later uses
its authoritative ordinary-Chrome button/voice/Stop+Exit settlement as one
input to the bounded warm L0 closure, together with separate 8/8 manual and
warm 20+20 evidence. The original statement that this repair alone did not
close D-095 remains true; the later decision changes the L0 completion scope
without retroactively changing this run. The separately excluded false Speech
cancel-degradation/cleanup diagnostics are now repaired and accepted in the
[Speech cancel review](L0_SPEECH_CANCEL_OBSERVABILITY_REPAIR_REVIEW_20260825.md).

## Scope and disposition

- Capability: Conversation Runtime playback stop through Product P2, Web and
  E2A diagnostics.
- Tested source: the final local commit containing this review; the scoped
  verification is repeated after the final amend with a clean worktree.
- Risk: Tier 3 shared response/presentation/cancel-state boundary under root
  `TESTING.md`.
- Intended behaviour: an exact retained response can still own audible browser
  playout after Agent generation is terminal. Barge-in must settle as a
  replayable `playback.stop`; terminal generation suppresses
  `response.cancel` and must never widen to `round.cancel` or `task.cancel`.
- Owned source: `conversation_runtime_loop.py`, the Product P2 consumer seam and
  `wire_codec.py`; owned regressions cover Runtime, Product P2, AgentServer/E2A
  and Integrated Web.
- Exclusions: generation-time interruption semantics, Speech Provider/VAD/TTS
  tuning, transport-cleanup acknowledgement, formal Task policy/recovery,
  D-095 cold/warm measurement execution and remote refs.
- Disposition: **AUTOMATED AND PHYSICAL ORDINARY-CHROME REPAIR PASS.** The
  original session is pre-repair evidence and is not relabelled; the new run is
  recorded separately.

## Located cause and repair

The Web route establishes the local browser-audio fence before it sends the P2
barge request. In the reproduced sequence, the text presentation ACK and Agent
generation terminal transition had already completed while browser TTS could
still be audible. Conversation Runtime rejected every such request as
`RESPONSE_ALREADY_TERMINAL`, so the user heard a successful local stop while
the authoritative RPC was encoded as `e2a.error`.

The repair separates the two lifecycles. Terminality blocks only a new Agent
response-cancel request; it no longer blocks the exact playback stop. Existing
identity, generation, replay and one-stop fences remain in force. The Web's
harmless-terminal-error convergence guard remains for compatibility with an
older server during rolling replacement, while the repaired server returns
`e2a.complete` on the normal terminal-response path.

For failed unary responses, the shared wire log now includes only stable,
bounded `error_code` and `error_reason` tokens. Free-form messages, nested
payloads, credentials and unstable tokens remain absent or are rendered as
`-`.

## Applicable D-032 matrix

| Dimension | Evidence and result |
|---|---|
| P | Actual Product P2 submit reaches terminal generation, accepts presentation ACK, then accepts barge-in with exactly one `playback.stop`; PASS. |
| N | Existing wrong generation/cross-surface/changed-action tests fail closed; log tests reject free-form diagnostic tokens; zero forbidden effects asserted; PASS. |
| B | All five terminal outcomes and already-stopped state are explicit; unstable and missing error tokens are bounded to `-`; PASS. |
| S | Response remains terminal with its exact outcome and `CancelState.NONE`; it is not reopened or relabelled; PASS. |
| T | ACK-before-barge ordering, exact action replay and later already-stopped action are covered; PASS. |
| C | Existing ordered-control and duplicate action tests retain single-effect linearization; PASS. |
| R | Exact replay returns the retained effect identity and creates no duplicate stop/cancel; Web retains old-server convergence compatibility; PASS. |
| I | Existing exact response/generation/route bindings remain enforced at Runtime, Product P2 and Web; PASS. |
| F | Master flag-off creates no registry/adapter or effect; diagnostic logging changes no response payload; PASS. |
| K | Full Integrated Web regression and E2A round trips pass; old-server terminal conflict remains harmless on Web; PASS. |
| X | Actual Product P2 registry/runtime, AgentServer wire encoding and compiled Integrated Web seams pass. The ordinary installed-Chrome microphone/audio rerun produced three successful authoritative barge settlements; PASS. |

Malformed arbitrary content beyond the existing request parsers, Provider
faults and Task recovery are inapplicable to this narrowly owned playback-stop
state repair. They remain owned by their existing boundaries.

## Verification

All commands ran from the repository root unless another working directory is
shown.

- `.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_conversation_runtime_loop.py -q --no-cov`
  — 40 passed.
- `.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_product_composition_registry.py::test_master_flag_off_constructs_no_registry_or_adapter tests/unit_tests/live_voice/test_product_composition_registry.py::test_product_p2_barge_in_is_exact_replayable_and_playback_scoped tests/unit_tests/live_voice/test_product_composition_registry.py::test_product_p2_terminal_barge_after_text_ack_is_playback_only -q --no-cov`
  — 3 passed.
- `.venv\Scripts\python.exe -m pytest tests/unit_tests/agentserver/test_live_voice_p3_route.py -q --no-cov`
  — 52 passed, including P2 barge-in encoded as `e2a.complete`.
- `.venv\Scripts\python.exe -m pytest tests/unit_tests/e2a/test_wire_codec.py -q --no-cov`
  — 16 passed.
- `npm run test:live-voice-integrated-web` from
  `jiuwenswarm/channels/web/frontend` — strict TypeScript compilation and 479
  tests passed. The build emitted only the existing duplicate `empty` locale-key
  warnings.
- `git diff --check` — passed.

A broad three-file Python run produced 232 passes and six stable failures in
excluded P3 Task query/cleanup tests. Five occur before the new Product P2 test;
all six reproduce when selected without it. Their failures point to existing
Task authority projection and `_P3Composition._accepting` fixture mismatches,
not to any touched Runtime, E2A or Product P2 source. They are not counted as a
pass and are not repaired or hidden by this packet.

## Ordinary-Chrome repair acceptance

On behaviour source `39932971f8`, the controlled `formal-web-validation`
launcher passed its real Speech round-trip and safety probes, loaded the current
bundle and routes on the four fixed ports, and started no isolated Chrome. The
operator used the existing ordinary installed-Chrome Session and reported
completion of, in order, button interruption, voice interruption, and playback
Stop followed by Exit.

The three exact actions `product-barge-1..3` targeted distinct response
generations `17..19`. Their P2 unary results were all `e2a.complete` in 56, 57
and 56 ms; no P2 barge `e2a.error` occurred. The close immediately following
the third action also returned `e2a.complete`. See the
[sanitized evidence](../evidence/L0_TERMINAL_BARGE_IN_REPAIR_EVIDENCE_20260824.md).

Three `live_voice_speech_transport_cleanup_incomplete` diagnostics and one
`STREAMING_SPEECH_CANCEL_UNACKNOWLEDGED` warning were also present. They are
reported, not suppressed or credited as fixed: they belong to the excluded
Speech Provider transport-cleanup boundary and did not change any of the three
successful P2 barge results.

## Review and remaining acceptance

A cold complete-diff review found no widening into Agent, Tool, Task, history or
other-scope mutation. Replay remains exact, terminal response truth remains
immutable, and error diagnostics are content-free. An independent `/review`
worker was unavailable under the active no-subagent execution constraint; this
self-review and the separate module/integration test boundaries are the recorded
substitute and limitation.

The owned terminal-response barge repair acceptance is complete. This bounded
rerun is not a D-095 cold/warm aggregate and does not close the separately open
Task, silence-rejection, Provider-cleanup or measurement work.
