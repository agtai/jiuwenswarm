# D100 P3 terminal replay and unsigned validation-ready review — 2026-08-11

## Scope and disposition

This record extends [D99](D99_P3_ORIGIN_ROUTE_RECONCILIATION_REVIEW_2026-08-11.md) through local implementation commit `ebd95ba1e` and records the unsigned validation-ready run against that exact source boundary.

The validation-ready lane passed its source, real-service, one-page browser, repeated-epoch and active-cleanup checks. It created no policy, key, signature, evidence owner, signed runtime artifact or Gate credit. The prepared WAV and retained diagnostic logs are operator diagnostics only; they do not replace physical-Jabra capture, complete user-heard playout or formal evidence. The Replacement Ledger remains `0/100`.

## Terminal replay and successor fencing

The first P3 origin-panel correction in `a0453ff19` exposed one additional restart boundary: a terminal task could complete before the new progress subscriber became active. Commit `ebd95ba1e` closes that boundary by:

1. enabling atomic retained-event replay for the authenticated P3 composition subscriber with bounded live and validation capacities;
2. retaining one exact current progress task target in the origin panel;
3. clearing predecessor progress immediately after a successful successor `task.create`; and
4. rejecting old-task, old-attempt and foreign-task progress or reconciliation responses before they can repopulate the current card or receive a new UI ACK.

The backend replay test covers both completed and failed terminal outcomes that predate subscription activation and asserts that validation creates no Task Store side effect. The mounted Web test covers successor task B replacing task A and proves that late task-A progress cannot repopulate the card or create a query/ACK.

## D-053 review and deterministic verification

- Implementation self-review: PASS with no remaining finding after the terminal-before-subscription and successor-target cases were added.
- Cold complete-diff review: PASS against the original request, repository rules, prior behavior and actual tests. It included `1cc0e9cb2`, `bf6873596`, `a0453ff19` and `ebd95ba1e`, with no remaining P0/P1/P2 finding.
- Independent `/review`: unavailable because the user prohibited delegation and no separate `/review` entry is exposed. The substitute is the recorded fresh complete-diff cold pass plus the strict affected suites below. This record does not claim that an independent semantic reviewer ran and does not convert that limitation into Gate credit.
- Focused P3 backend suite: `284/284` PASS.
- Integrated Web strict compilation, bundled unit and mounted suite: `247/247` PASS.
- Tier-3 affected Python regression: `1482/1482` PASS in 219.87 seconds.
- Frontend production build, Ruff, Prettier and `git diff --check`: PASS.
- A generic `npm test` probe was inapplicable because this package defines no such script; the repository's actual bundled frontend command passed as reported above.

## Unsigned validation-ready runtime

The run used one isolated Chrome profile and one page target at the exact persisted `/chat/<session_id>` route. The selected project was shown as `Live Voice W2 Fixture`, the selected Agent model was `deepseek-v4-flash`, and both remained bound across two consecutive AgentServer epochs. Switching the existing page into Code mode temporarily changed its route; the same single page was immediately returned to the exact Session URL before route validation continued. No second page was opened.

Real-service observations on epoch 1 and epoch 2 were:

- P3 completed: `task-02e8c9a76e25452db11576bf87ab588e` advanced `accepted → running → completed`; terminal sequence 5 was authoritative and acknowledged. The exact one-line fixture mutation was restored to the clean checkpoint.
- P3 failed: successor `task-165945806f5946c4aa4177256f529a87` immediately replaced the old completed card, advanced `accepted → running → failed`, retained the authoritative terminal ACK and made no fixture change.
- Refresh/reconnect retained exactly one page and exact Session URL. An observed `live_voice.composition.p2.close` completed successfully before the next activation, closing the prior signed-diagnostic timeout question on the corrected environment.
- A short real-Agent P2 returned `P2_R4_SHORT_OK` and was acknowledged.
- A forced read-only Terminal Tool P2 invoked real `bash` with `git rev-parse HEAD` in the disposable fixture and returned exact checkpoint `167ca949320f195afa2dbff86f1f31b4cd042ddd`; the fixture remained clean.
- Deterministic-WAV P1 reached `recognized`, committed the recognized text to the real Agent, presented and acknowledged `语音连调成功。✅`, entered TTS `playing`, and started successor capture. The successor failed closed after 30 seconds as `AUDIO_CAPTURE_DURATION_EXCEEDED` with no new Speech or Agent submission.

One recoverable operator error delayed the first recognized-turn commit beyond the 300-second voice-receipt TTL. Gateway correctly replaced the expired receipt with a closed `invalid` claim and P2 failed without dispatch. The immediately repeated turn completed the positive P1/Agent/TTS journey above; no source repair was required.

Codex Chrome control was unavailable in the isolated profile and Computer Use initialization failed because its desktop kernel assets were absent. Existing-page CDP control completed the repeatable work without changing the single-page, Session or authority boundary. These automation channels were not used as fault or evidence owners.

## Cleanup and remaining Gate boundary

Before shutdown the scratch P3 database contained exactly two terminal tasks and attempts, completed and failed respectively; both outbox rows were `delivered`, with zero nonterminal task/attempt/project-attempt, zero pending outbox and zero retained owner/lease fields. Chrome, Gateway, AgentServer epoch 2 and Vite were stopped; all five dedicated ports were closed, no isolated Chrome process remained, the source worktree was clean and the disposable fixture was clean at `167ca949320f195afa2dbff86f1f31b4cd042ddd`.

The Vite controller reported Windows termination code `3221225786` during teardown, but its subsequent process and port oracle was empty/closed. A later attempt to remove the isolated r1–r4 diagnostic directories and the r2/r4 scratch SQLite files was rejected by the execution policy before deletion. Those inactive diagnostics remain isolated and must never be reused as candidate, policy, database or evidence roots.

The next allowed step is to freeze one fresh clean descendant, create new candidate-specific profile/database/policy/key/evidence roots and issue the rehearsal policy once. Pair 1, Pair 2, Pair 3 and A4 must then run continuously before findings are batched. Formal policy remains forbidden until all four rehearsal experiments pass; physical Jabra capture, complete audible playout and the user's receipt remain required in the final assisted run.
