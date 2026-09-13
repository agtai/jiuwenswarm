# Semantic retirement oracle migration — working verification record

Baseline: `478102789de5d24c1702c896fae81f68e405fb9a`, atop the user's current
W3 baseline. This record does not grant final-candidate or audio acceptance.
Historical evidence and the old fixed corpus keep their original meaning.

## Additional real-audio findings (2026-09-03)

- User-directed closeout: at 06:56:45 UTC the user requested a 30-minute
  review-only handoff, without further tests, model probes or audio replay.
  The facts below are readings of existing results, not new validation. No
  complete-candidate, production-readiness or physical-audio PASS is granted.
- Original-audio attempt 16 used the real browser capture/STT/semantic/Agent
  path. `analysis` and `accept_proposal` passed their then-loaded oracles;
  `confirm_A` failed at `formal-commit-and-semantics`, with
  `SEMANTIC_OUTPUT_INVALID` in the authoritative committed-input result.
  No Task was created and there is no A/B/A2 artifact or full journey credit.
  The failing model output was not retained by that runtime path, so the exact
  decoder condition is unknown; this must not be presented as a diagnosed
  single-field defect. Report: `semantic-audio-journey-attempt16.json`.
- Model-only v13 passed 11/11 under its earlier weaker constraint oracles.
  Strengthened v14 selected three cases: detailed equipment continuation and
  explicitly independent work on the same underlying problem passed; the
  recorded audio-15 continuation failed. Its exact proposal reference was
  retained, but the instruction omitted the earlier meeting time and retained
  spoken `MD` instead of the expected `.md` filename. Its report includes the
  expected fields, loaded raw-record SHA and actual required/forbidden patterns:
  `semantic-model-probe-strengthened-v14/model-probe-20260903T065623754171.json`.
  Do not upgrade the full suite or silently discard this retained failure.
- A subsequent read of attempt 16 exposed two overly narrow test patterns:
  its real instruction said `明早9:30到会场赶上10点客户会议` and
  `酒店不要改动`. These are not lost date/hotel constraints. The test-only
  oracle now recognizes them and contains a paired hotel-reversal assertion;
  this addition is **NOT RUN** following the user's stop. The original failed
  review observation is not rewritten into a passed rerun.
- Existing scoped automation recorded 150 passed in
  `semantic-model-migration-formatted.log`; the nine earlier constraint-oracle
  cases passed separately in `semantic-constraint-oracles.log`. The later full
  legacy Registry diagnostic still recorded 57 failed / 160 passed in
  `semantic-registry-after-native-migration.log`. Web's earlier diagnostic
  recorded 562 passed / 12 failed / 1 skipped and is not current cumulative
  candidate credit. Remaining failures have not all been retired or explained;
  no tests/skips/assertions are removed to manufacture a pass.
- Review-only follow-up found a remaining contradictory purchase/installation
  hole in the fixed-corpus oracle. Required prohibitions could coexist with
  an appended immediate purchase/install instruction. Added contrary patterns
  and three regression cases are a definite test-side correction, **NOT RUN**
  under the user's stop. They do not change production semantics or authority.
  Independent fix-only reread confirms the source correction addresses this
  exact finding, without a test/Gate PASS. The same reviewer confirmed recorded
  expected/SHA/loaded-pattern reporting and the explicit independent-work case;
  no new production hardcode or confirmation bypass was found in the prompt
  refinement. This is scoped review, not cumulative integration review.
- Automated browser a15 received the ordinary Exit Live Voice click and then
  its owned stop request. Its cleanup record reports
  `owned_browser_stopped: true`; no further automated capture is active. The
  isolated Cascade services remain available on loopback ports
  18192/19100/19101/6173 for manual intervention. Product files match the
  runtime's recorded source manifest; later changes here are test/evidence only.
  The original user services/configuration and failed attempts remain untouched.

- Attempt 15 again passed actual browser/STT/Agent analysis and non-silent
  playback, but failed proposal continuation. No Task was created; the exact
  recognized final and preceding real proposal are frozen in test support as
  `audio_journey/recorded_proposal_refinement.json`, not production input.
  Model-only v10 reproduced the missing reference. V11 preserved the reference
  but failed the written filename expectation; v12 fixed that recorded case but
  dropped an unrevised constraint in the separate equipment case. All remain
  retained failures. The subsequent generic instructions prioritize underlying
  work continuity, preserve every unrevised constraint, and interpret clear
  spoken spelling without changing the committed transcript. No keyword,
  business-name or fixed-file mapping is introduced.
- The unused production `demo_fixture_contract.py` constant is removed.
  A repository-wide import/symbol scan found no executable consumer. Historical
  retirement-manifest path/symbol entries remain unchanged as historical data;
  the removed file owns no unique current test oracle.

- The preparation started at 07:10 local was interrupted before service launch
  after TypeScript exposed a missing local helper in the new typed projection.
  Read-only checks found no owned Python/Node processes or listeners on the four
  test ports; both source configuration hashes were unchanged. The cleanup
  marker was reconstructed from those checks before a fresh owned restart.
  This aborted preparation is not an executed audio case or a passing build.

- Attempts 9 and 10 retained their actual audio, transcripts, failures and full
  source manifests under the isolated test output. Neither created a Task.
  Attempt 9 exposed an early proposal-observation race and an overly narrow
  extraction instruction. Attempt 10 failed exact-source extraction settlement;
  it is not a positive proposal acceptance.
- Model-only target-schema v2 probe: 6/8 passed. Chinese create omitted the
  required operation provenance entry; concrete-offer extraction timed out at
  45 seconds. Keep both failures; model-only probes are not digital audio proof.
- Business input v2 removes the future A2 request (additional 20 minutes) that
  had accidentally been included in source facts. The prior a4 project's initial
  Git commit preserves v1; test-project commit `279efcf` records the exact edit.
  The unchanged audio corpus still supplies that requirement only in the later
  successor request. No expected final plan or selected Task ID is in v2 facts.

## Replacement ownership before removal

| Retired test responsibility | Current owner / retained oracle |
|---|---|
| Bridge committed create, partial/uncommitted, scope, precise cancel | The original four `test_voice_task_bridge.py` groups stay unchanged. |
| Keyword grammar, fixed itinerary/checkpoints, current/latest Task targeting | Intentionally retired behaviour, not the new language contract. New real-model and digital corpus use natural, cross-domain input. |
| Strict semantic output, bounds, provenance, no tools/fallback | `test_task_semantics.py`: exact schema, source/digest, malformed/duplicate/unknown fields, expiry, scope and zero model/tool escalation. |
| Structured controls, unknown/missing/authority fields | `test_production_task_intent_classifier.py`: keep exact structured schema and the 14-operation corpus groups; no natural classifier exists. |
| Natural origin accepted-ledger binding and lost authority | `test_p3_production_intent_composition.py`: same authority assertions, proposal supplied by the sole model boundary instead of a retired phrase parser. |
| Confirmation, related/unrelated target changes, no cross-Task mutation | Existing `test_production_multi_task_resolver.py` and `test_semantic_registry.py` real Store/Core normal-confirmation tests; controlled model is not language evidence. |
| Multi-turn analysis/proposal, CAS, replay, refresh, corruption | `test_semantic_continuity.py`, `test_semantic_registry.py`, `test_unified_committed_input.py`; actual presentation is required, retained state grants no authority. |
| Old Web natural operation-hint/target form | Retire that input surface. `unifiedCommittedInputOwner`, exact formal controls and mounted audio-origin progress own the surviving duplicate/unknown/stale/DOM-before-ACK assertions. Mounted migrations remain in progress. |
| Old display-only natural status formatter | Formal Task control/status/progress and mounted A/B terminal projection; add explicit absent-old-UI/sole-entry reachability test. |

## Mutation sensitivity already observed

- Four old Native create/status/event functions are replaced by the new
  `test_native_two_voice_turns_create_once_and_bind_real_origin` and three
  `test_native_exact_task_reads_use_authoritative_receipt_without_business_tools`
  cases. They use normal semantic confirmation and real Core/Store, with a
  test Executor and controlled model. The first confirmation has exactly one
  Task/Attempt/Command, accepted/not-cancelled state and no Executor dispatch;
  exact replay/conflict, native origin/response, completed/running status,
  requested/applied events and B isolation remain explicit. Test-only injected
  lost origin/wrong query receipts fail all four oracles; the normal source
  passes all four (`semantic-native-oracle-red-v3.log`,
  `semantic-native-migration-reviewed.log`). Independent review's missing
  first-confirmation side-effect assertion was fixed and reviewed C0/I0/M0.
  Native result/late-ACK/capability and other adjacent tests remain present.
  This migration grants no actual ASR, file, audio or physical credit.

- The retired synthetic-context test is replaced by
  `test_task_notice_is_not_dialogue_and_control_ack_is_not_work_proposal`.
  Real confirmed creation preserves acknowledged user/control dialogue; a
  separately presented server notice is excluded and never yields a proposal.
  Removing the runtime's server-source eligibility check produces the exact
  forbidden notice in context (RED, `semantic-task-context-oracle-red.log`);
  restored source passes (`semantic-task-context-migration-v3.log`). This
  intentionally retires the bypass-specific expectation of no conversational
  control replies; D-107 records why real dialogue is retained.
- The two old canonical-create receipt test functions (11 cases) are replaced
  by normal confirmed real-Store creation and the new 10 malformed receipt
  cases. The new set includes the old running-versus-accepted rejection and
  every missing/blank/unexpected/nonmapping receipt case, with exact replay,
  no duplicate Task and no false voice-origin association; it no longer
  requires a fixed Chinese receipt string. Its previously recorded RED proves
  permissive receipts fail the new oracle before removing the old functions.

- Malformed create receipts: the existing new 10-case regression failed under
  the old permissive receipt path; it now rejects unknown effects without an
  origin association, duplicate Task or unintended target control.
- Mixed timestamp precision: the retained-context boundary failed at the
  actual sub-microsecond future discrepancy; UTC timestamp precision is now
  consistent without widening the future/expiry bound.
- Ready-frame starvation: two backlog tests failed before the scheduling
  repair and passed afterward. Post-review five same-tick terminal cases
  preserve zero EOT/claim on malformed, sequence/cursor, consumer or detach.
- Capture limits: the actual 61.5-second 48 kHz input and Provider lifetime
  checks both failed with the old 4 MiB/35-second values, then passed with
  aligned bounds. The current Python capability is decoded by the actual TS
  client; oversized input makes zero RPC calls.

Raw red/green logs and all digital attempts remain in the task's isolated
temporary evidence directories. Exact final commands, source digests, remaining
failures, independent review and digital reports will be recorded at closure;
neither this mapping nor test counts substitute for that work.
