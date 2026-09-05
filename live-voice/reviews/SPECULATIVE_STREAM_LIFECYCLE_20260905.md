# Speculative Agent stream lifecycle repair

## Scope recorded before implementation

- Baseline: `5948c9572e9bd900f8c9c777f31ac73c9758ccd3`.
- User authorizes repair and controlled local redeployment after the analysis
  request in session `web_1a070da5ce1_7a3d44a2f091` failed.
- Owner/risk: Agent Bridge and its Formal adapter / Web error presentation;
  Tier 2 lifecycle and cancellation repair under root `TESTING.md`.
- Intended behavior: speculation before admission remains bounded and tool-gated.
  Once admitted, already-consumed chunks are released and slow consumers apply
  backpressure. A long answer is never stopped by cumulative chunk/byte counts.
  Completion, error and cancellation close the stream in its driving task's
  context, release buffered content and settle cleanup before reporting it done.
  Terminal-without-final outcomes remain explicit in Web recovery diagnostics.
- Owned surfaces: `speculative_dialogue.py`, Formal facade/deep-adapter stream
  delegation, Harness stream closure if needed to preserve context ownership,
  integrated Web terminal reason construction, their focused tests, this evidence
  and the affected STATUS consequence.
- Exclusions: Agent prompts/output/model options, VAD/playout defaults, semantic
  routing, background Task/Store/schema changes, business classifiers, broader
  hardcode retirement, production/SLO or physical-audio acceptance claims.
- Acceptance: exact long-stream delivery beyond 2048 chunks and byte turnover;
  bounded unread occupancy under slow consumption; pending/oversize rejection;
  success/error/cancel/repeated-close cleanup; concurrent candidate isolation;
  no Tool execution before admission or after rejection; exact Web failure
  identity and zero Task control effects. Exercise actual facade/adapter cleanup,
  affected integration regressions, independent review and controlled deployment.
  Restart/crash durability is unchanged and outside this in-process boundary.

## Root-cause evidence

The private runtime log `logs/swarm-20260905-110805.log` records successful
`资料.md` reading at 11:16:23 (+02), then Agent event sequence 2047 and stream
cancellation at 11:16:36. The admitted candidate still retained every consumed
chunk in a list. Its 2048-chunk limit therefore acted as a lifetime quota.
A paced local reproduction (only one chunk produced per consumption) delivered
2048 chunks, dropped the final, and aborted on chunk 2049. This was not the
retired 12-second answer-verification path.

Nested async generators also lacked explicit child closure; their garbage
collection cleanup reset permission ContextVars in another context. Web composed
`PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL:<outcome>` but its diagnostic validator
rejected that representation and replaced it with `PRODUCT_AGENT_OUTPUT_FAILED`.

## Implementation and verification

The admitted stream now uses a deque of unread chunks. Consumption releases byte
and chunk occupancy before yielding; a full admitted buffer pauses production.
Pending overflow still rejects the candidate and allows the existing serial
fallback. An individually oversized chunk fails explicitly; resource bounds
remain in force. No text is shortened, rewritten or independently checked.

The producer closes its iterator, and both Formal delegation layers explicitly
close their children. Harness closure stays in its driving task; a late cancel
cannot interrupt that closure. Concurrent discard/close sends one cancellation
and joins the retained producer even when a waiter is cancelled. Deep output and
session cleanup also retain their joins when cancellation arrives during cleanup.
The ended/settled state no longer precedes cleanup or discard of unread output.

Verified against the scoped diff from `5948c957` (private logs below):

- Red tests reproduced lifetime overflow, missing explicit child closure,
  cross-context Harness closure, concurrent producer cleanup cancellation and
  cancellation during actual adapter output/session cleanup. Red Web checks
  reproduced loss of all four canonical terminal reasons.
- `python -m pytest tests/unit_tests/live_voice/test_speculative_dialogue.py
  tests/unit_tests/agentserver/test_formal_live_voice_adapter.py
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py
  tests/unit_tests/live_voice/test_agent_bridge_runtime.py --no-cov -q`:
  **172 passed**, one existing Authlib deprecation warning.
- The positive stream tests turn over both chunk and byte bounds across 4097
  chunks. Other cases cover pending gates, oversize rejection, failure repeated
  20 times, concurrent candidate isolation, duplicate close/cancel, retained
  cleanup and exact provenance rejection. Bridge/Runtime tests cover ordered
  terminal truth, stale/wrong identities, feature-off, fallback and history
  authority. Restart/crash and physical audio are outside this in-process repair.
- Mounted Web failure and generation-interruption selection:
  `node --test --test-name-pattern='mounted response-generation failure|generation
  interruption|generation-interruption|retire.*close'
  tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`: **10 passed**.
  Exact activation/response identity and zero Task mutations remain asserted.
- `tsc --noEmit`: passed. Pure Web suite: **68 passed, 1 pre-existing failure**
  in the source-only `onTaskRefresh=` assertion. Baseline and current
  `ChatPanel/index.tsx` are identical and both lack that string; the unrelated
  entry/oracle migration remains open, not counted as a pass.
- Removing a detached cleanup hop exposed an incidental scheduling dependency
  in the no-consumer notification test. Bridge completion means source terminal
  observation, not completion of the separate presentation consumer. Its test
  now waits boundedly for the existing presentation precondition without
  draining notifications; all original lease/history/shutdown assertions remain.
- Main reviewed the complete scoped diff. Independent `review_stream_lifecycle`
  found the two cancellation cleanup races above; both were fixed and its
  original repros now wait for actual release. Final scoped review found no
  remaining actionable issue. The reviewer also checked the test synchronization
  change. A pre-existing cancellation/failure during session acquisition, before
  the Formal root try/finally, remains routed to Agent Bridge startup/recovery;
  it is not claimed fixed by this output-stream packet.
  Its independent focused check completed with 21 passes and exit 0.

Private evidence: `logs/speculative-lifecycle-*-20260905.txt` and
`logs/speculative-lifecycle-20260905/`. These contain red/green outputs, baseline
comparison, actual-model evidence and the source file manifest; they stay out of
Git. No prior failed evidence was overwritten by a success record.

## Actual Agent and file-tool boundary

An isolated registered no-remote project used a byte-identical copy of the current
`资料.md`, the existing private model configuration in place, and the user's
analysis wording. Real semantic routing returned `dialogue`; the actual configured
Agent and `glob`/`read_file` tools then ran through the speculative/attached stream.

The request delivered **3680 chunks** and a **712-character final** unchanged from
the adapter's actual parsed final. Peak unread occupancy was one chunk / 313 bytes;
after completion both buffer counters were zero, no overflow/error was recorded,
and no Formal cleanup or speculative producer task remained. It took about
30.2 seconds. This is typed real-model/file-tool evidence, not microphone or
latency/SLO acceptance. There was no Task dispatch or write/edit/shell tool call.
Fixture and configuration hashes were unchanged.

## Controlled deployment

Committed implementation: `618a6c6122` (`fix(live-voice): drain admitted streams
and retain cleanup ownership`). At 11:45 (+02), the controlled launcher completed
from that clean source, using the saved `formal-web-validation` profile. Its
`-PreflightOnly -NoBrowser` check passed before
`-RestartExisting -NoBrowser` rebuilt and restarted the services.

The new runtime contract records Cascade, all required flags enabled, generation
interruption enabled, `verified_headset_aec_v1` local pause, and the existing
`live-voice.direct-project-code.d2.v2` Executor. Real Provider TTS→STT, formal
receipt, identity-mismatch rejection and forged-claim rejection passed with zero
business side effects. The deployed frontend was fetched over HTTP and is
byte-identical to `/assets/index-BI5E3I1w.js` in the new build (SHA-256
`8b532dcf8a4cf554bfa5317cfbb89028437b1a076109d457d196f121a6f35abe`).
It contains the corrected terminal reason. Ports/PIDs after startup:
5173/37956, 18092/4076, 19000/34036 and 19001/34036.

Before and after restart the runtime retained 56 Tasks and 56 Attempts, all
terminal, plus 34 results, 35 consumption records, 349 Task events and 141 commands.
All six table content hashes, saved profile, private configuration and original
fixture hashes match exactly. Product source hashes also match the actual-Agent
probe's manifest. No startup ERROR/Traceback/foreign-Context/unsafe-cleanup entry
was found in the new service log at verification time.

Private evidence includes `preflight.log`, `deploy.log`, `runtime-contract.json`,
`served-asset.json`, `predeploy.json` and `postdeploy.json` under the run directory.
Refresh an existing page and re-enable Cascade to use the new browser code and
activation. Full A/B/A2, microphone interruption, startup-acquisition failure,
production and indefinite-uptime acceptance remain unclaimed.
