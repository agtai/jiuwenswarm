# Repository agent guidance

## Live Voice tasks

Before planning, implementing, reviewing, or testing Live Voice work, read these files in order:

1. `docs/zh/live-voice/README.md`
2. `docs/zh/live-voice/HANDOFF.md`
3. `docs/zh/live-voice/STATUS.md`
4. `docs/zh/live-voice/TWO_WEEK_DEMO.md`
5. `docs/zh/live-voice/POST_V0_DELIVERY_ROADMAP.md`
6. `docs/zh/live-voice/POST_V0_STASH_HANDOFF.md`（历史 stash 与额外恢复保险；当前分支已有 foundation 时不要重复 apply）
7. `docs/zh/live-voice/V0_ACCEPTANCE.md`
8. `docs/zh/live-voice/DECISIONS.md`

Before starting services or running real microphone/Agent/tool validation, also read and follow `docs/zh/live-voice/E2E_RUNBOOK.md`.

Before preparing or presenting the fixed showcase, also read `docs/zh/live-voice/DEMO_SHOWCASE.md`.

Read `docs/zh/live-voice/FULL_SOLUTION_2026-07-30.md` completely when the task affects long-term architecture, P1/P2/P3 boundaries, protocols, state ownership, cancellation, presented history, durability, or production acceptance.

The immutable validation baseline is the V0 vertical-slice candidate at the SHA recorded in `STATUS.md`; V0 remains unreleased until `V0_ACCEPTANCE.md` passes. D-030 ended the temporary stash boundary: develop, review, commit, and push Post-V0 work normally, then validate V0 later from a separate checkout/worktree at the immutable SHA. The next accepted slice is the poll-backed non-blocking task monitor in D-031; do not silently expand that slice into full P3. The Demo must send final speech transcripts to the real JiuwenSwarm Agent and tools; it is not an ASR/TTS-only showcase. Do not present Demo shortcuts as production-complete capabilities.

At the start of a resumed Live Voice task, run `git status --short --branch`, `git rev-parse HEAD`, and compare the local branch with its upstream. If a handoff snapshot and Git disagree, treat the pulled remote branch as the implementation fact, report the mismatch, and update the handoff instead of silently using stale text.

Every Live Voice module or logical slice must follow D-032 and the mandatory test-closure gate in section 3.1 of `docs/zh/live-voice/POST_V0_DELIVERY_ROADMAP.md`. Before semantic implementation, re-read the relevant solution, current stage, module contract/decisions, and existing tests, then record the module definition, test inventory, why each test exists, and the complete scenario matrix in `docs/zh/live-voice/STATUS.md`. After implementation, repeat that review against the actual diff and final tests. Positive business scenarios must succeed; negative business scenarios must be rejected or fail closed, with forbidden side effects explicitly asserted as zero, while the test process itself passes. Test counts or line coverage alone never prove module closure. Missing coverage or an unexplained `N/A` means the slice is `PARTIAL` or `BLOCKED`, not `CLOSED`.

After material Live Voice work:

- update `docs/zh/live-voice/STATUS.md` with progress, verification, known issues, and the next concrete actions;
- update the D-032 pre/post review, test inventory, scenario-to-test mapping, exact tested SHA, commands, and remaining gaps for every affected module;
- update `docs/zh/live-voice/DECISIONS.md` when scope or a technical choice changes;
- update the Shortcut Ledger in `TWO_WEEK_DEMO.md` when adding or removing a temporary limitation;
- normally commit and push the documentation with the related code so another machine can resume from Git alone; D-030 ended D-022's temporary pre-V0 stash window, so keep `2c700934` as the immutable unreleased V0 Candidate and commit later Post-V0 work without relabeling it as V0 evidence.

User instructions and newer accepted decisions take precedence. If code and documents disagree, record the gap instead of silently treating the current code as the intended final design.
