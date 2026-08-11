# Alpha Wave A+B integration review — 2026-08-07

> Frozen review, environment-preflight and verification record for tested local implementation `dd637e604939cef7200d4ff5d30acf55a89d62f2`. Mutable route, Git and next-action facts belong only in [STATUS.md](STATUS.md).

## Candidate identity and integration method

The local candidate branch is `codex/lv-alpha-ab-integration`, created from pushed baseline `7876e1ae9caad28535abcc674d6b02f72553fe4f`. It has no configured upstream. The local and remote-tracking `hx/0803_live_voice` refs remained at the baseline throughout this batch, and no Wave A+B commit was pushed.

Main applied the accepted D-060 local-operation exception and integrated the reviewed Task commits in dependency order. The source branches remain audit pointers; the commits in the third column are the linear candidate history:

| Role | Source branch and reviewed source commit | Commit on integration branch | Bounded scope |
|---|---|---|---|
| Main kickoff | `codex/lv-alpha-ab-integration` | `c187b38d0a5d56b4bd07165539161887c2542d8d` | freeze execution start without changing product truth |
| T3 P3alpha | `codex/lv-alpha-ab-t3-p3` at `a562adaff84489cab2017dccdb58f534ea2896b7` | `a2ac57722a01e4964133dce9754c5c1d82602dea` | bounded durable trusted-confirmation issuer |
| T4 X-OBS | `codex/lv-alpha-ab-t4-x` at `875810765c20f62a38bbab09be650fdf451514b4` | `e42878aab25a7a6da568d1419409649986576fea` | deterministic bounded observability fault harness |
| T1 P1 | `codex/lv-alpha-ab-t1-p1` at `6e041b18ed8c758bc32a7f191aee71d75efe2327` | `b1361572a913048cf592e568d734316566aa30a4` | bounded Media and browser-transport activation/startup/cleanup owners |
| T2 P2 | `codex/lv-alpha-ab-t2-p2` at `b2b6a08eb414eff206b8bb24d1419a8951cb44a3` and final `79450a3dd6f4a1ceb8325483798568a2d22bcc1d` | `913bb3f24b2ae2bcb129095b27cfa53daac84c1b` and `5005aecf40d74dd67962c7ba1b1be459b5ca7ba3` | retained committed-turn submission and completed-presentation acknowledgement/history |
| Main integration | `codex/lv-alpha-ab-integration` | `dd637e604939cef7200d4ff5d30acf55a89d62f2` | stock-Web UI/owner, shared RPC, Gateway/AgentServer registry and P2/P3alpha product glue |

T5 performed independent review without a code commit. T6 performed read-only environment/E2E preflight. No semantic conflict was delegated outside the owning lane; Main-owned integration semantics and regressions are isolated in `dd637e60`.

## Actual integrated product paths

### P2 committed text to real Agent and exact presentation history

- Stock Web owns one exact default-off activation binding and submits only committed final text as a stable TurnCommit operation. The route reaches the existing AgentManager/Harness/Conversation Runtime owner rather than an ASR/TTS-only or fake backend.
- Final notifications retain stable request and response identities across response loss, disconnect and reconnect. Stock Web pauses a second semantic turn while submit or presentation truth is unknown.
- Exact PresentationAck writes only the selected presented final to the existing history owner. Completed acknowledgements remain replayable after cleanup; conflicting or evicted operations fail closed.
- Gateway and Web preserve nested product errors. AgentServer replacement serializes prior-owner cleanup before a successor connection becomes current.
- One runtime admits at most 256 committed turns. There is no stock-Web automatic rollover in this candidate; this is a documented bounded limit, not an availability claim.

### P3alpha trusted confirmation and bounded mutation

- A durable bounded confirmation owner issues exact current-owner receipts and one-use forwarding permits. Direct legacy verifier access cannot mint a product permit.
- Stock Web exposes distinct confirmation and mutation actions for the currently bound task command. Create/cancel mutation is triple-gated, uses stable operation IDs and rechecks current authority for retained replay.
- Denied requests allocate no operation capacity. Conflict information is not disclosed before reauthentication; stale owner/generation, mismatched binding, stopped registry and consumed permit all fail closed.
- Formal task-progress voice remains unavailable because no atomic TaskEvent/projection authority handoff exists. Alpha bearer/Session/Project authority is not production authorization.

### P1 and X-OBS remain truthful dependency boundaries

- P1 package and browser transport now own bounded activation/startup, partial-start rollback, exact generation/track/epoch state, payload ownership and retained cleanup. The central product registry still returns Media unavailable because there is no selected real Provider/transport deployment or registered route-to-disk zero-persistence evidence.
- X-OBS adds a deterministic bounded harness for saturation, exporter timeout, late result and cleanup ownership. It is not a product exporter or backend and remains unregistered.

### Main stock-Web/Gateway/AgentServer glue

- Shared request methods, Gateway credential injection and Web response parsing cover only the reviewed default-off P2/P3alpha product operations. Browser-supplied credentials never become authority.
- Product ledgers, tombstones and generation fences are bounded. Oversized JavaScript-safe integer fields reject before fingerprinting, admission, authority, Agent or history effects.
- Reconnect recovery settles an exact closed notification, closes the old activation generation, verifies its fence and creates one successor generation. Unknown mutation/submit outcomes preserve their exact retry owner.
- The UI truthfully separates unavailable P1/X-OBS facts from integrated P2/P3alpha text controls and does not label this route Alpha-accepted or production-complete.

## D-046/D-053 review closure

This coherent Tier 2/3 batch completed implementation self-review, repeated cold complete-diff review and an independent read-only reviewer pass. A literal `/review` entry was unavailable, so the independent T5 agent is the recorded equivalent; no claim that `/review` ran is made.

The review cycle found and closed issues in four groups:

- authority and mutation ordering: authority-before-capacity, retained replay reauthorization, conflict secrecy, P3 stop/admission serialization and independent safe-integer negative cases;
- bounded/idempotent truth: retained response-loss outcomes, fixed-capacity ledgers, fail-closed evicted replay, non-resurrecting activation generations and stable notification sequencing;
- lifecycle/concurrency: AgentServer connection replacement cleanup, queued-final ordering, idle-poll reconnect recovery, exact old-generation close and construction-time owner callback safety;
- Web/error semantics: nested product-error promotion, definitive-versus-unknown operation classification, editing locks, bounded presented-response ownership and generation cleanup.

Affected tests were rerun after every material fix. The final independent verdict was `PASS`; its final scoped rerun recorded 3/3 safe-integer negatives and 43/43 product-registry tests. The reviewer retained the explicit 256-turn/no-rollover limit and did not treat it as a hidden production capability.

## Verification at immutable code commit

| Verification | Result |
|---|---|
| affected Gateway/registry/P3/AgentServer five-file batch with coverage addopts disabled | `132/132 PASS` |
| `.venv\Scripts\python.exe -m pytest -q -o addopts= --asyncio-mode=auto tests/unit_tests/live_voice tests/unit_tests/gateway/test_app_gateway_acp.py tests/unit_tests/channel/test_web_channel_symphony_status.py tests/unit_tests/gateway/test_live_voice_speech_rpc.py tests/unit_tests/agentserver/test_live_voice_p3_route.py` | `965/965 PASS in 30.68s` |
| `npm run test:live-voice-integrated-web` | `83/83 PASS` |
| `npm run test:live-voice-task-bridge` | `49/49 PASS` |
| `npm run test:live-voice-task-client` | `17/17 PASS` |
| `npm run test:live-voice-task-adapter` | `19/19 PASS` |
| `npm run test:live-voice-task-monitor` | `23/23 PASS` |
| `npm run test:live-voice-core` | `9/9 PASS` |
| `npm run build` | PASS: TypeScript + Vite, 4507 modules transformed |
| scoped Ruff over affected Python source/tests | PASS with only the repository's known unrelated `E402`, `F841` and `F821` classes excluded |
| scoped Mypy over four core Live Voice sources with `--follow-imports=skip --ignore-missing-imports` | `Success: no issues found in 4 source files` |
| `git diff --check` | PASS; Git emitted only Windows LF/CRLF conversion notices |

The first cumulative attempt intentionally disabled the repository-wide coverage addopts but accidentally also removed the configured `--asyncio-mode=auto`; it produced 930 passes and 35 async-fixture configuration failures. D-061 recovery identified the command error, changed no code, and reran the identical selection with explicit async-auto to the 965/965 result above. A non-isolated Mypy invocation similarly traversed the wider repository and reported 1137 pre-existing cross-module errors; the documented isolated command is the applicable affected-source check.

The build retained existing non-blocking warnings for duplicate `empty` locale keys, stale Browserslist data and large Vite chunks. Test counts are software evidence only and do not replace a real browser/device/Provider/service run or an acceptance Gate.

## Read-only environment and E2E preflight

- No Live Voice Speech Provider environment was configured. The installed adapter advertised batch behavior only; no real streaming provider route was available.
- Chrome `150.0.7871.187` was installed, but expected local service ports were closed. No physical microphone/device, autoplay, background/reconnect, secure-origin, TLS/WSS, CSP/CORS or enabled origin-check run was performed.
- No disposable registered P3 Code project, matching model configuration or runtime service was available for a real mutation journey.
- X-OBS had no exporter/backend configuration. Only the deterministic in-memory fault harness was runnable.

These are machine-private dependency facts, not Git-restored guarantees. They explain why T6 could complete preflight but could not truthfully execute Wave C or acceptance evidence.

## Retained boundaries and Wave C inputs

1. Select and configure a real Speech Provider and media transport/codec, supply network access and a secure desktop-Chrome device path, and prove registered route-to-disk zero audio-payload persistence.
2. Supply an X-OBS exporter/backend plus retention and SLO policy, then reconcile truthful Composition registration.
3. Supply a disposable registered Code project, real model/configuration and runtime services for P3alpha create/cancel/progress; design the remaining atomic voice authority handoff separately.
4. Run real P1, P2 and P3alpha verticals, then the joint non-blocking browser/service journey and Immutable Alpha Gate on one candidate.

Until those inputs exist, P1 remains product-unavailable, X-OBS remains unregistered, formal task voice remains fail-closed, the Integrated Demo remains not runnable, the Alpha Gate remains unrun and the Replacement Ledger remains `0/100`.
