# Repository agent guidance

## Live Voice tasks

Before planning, implementing, reviewing, or testing Live Voice work, read the current-state set in this order:

1. `docs/zh/live-voice/README.md`
2. `docs/zh/live-voice/STATUS.md`
3. `docs/zh/live-voice/HANDOFF.md`
4. `docs/zh/live-voice/DECISIONS.md`
5. `docs/zh/live-voice/POST_V0_DELIVERY_ROADMAP.md`
6. `docs/zh/live-voice/TWO_WEEK_DEMO.md`

For V0 validation, also read `docs/zh/live-voice/V0_ACCEPTANCE.md`, `docs/zh/live-voice/E2E_RUNBOOK.md`, and `docs/zh/live-voice/DEMO_SHOWCASE.md`, and run them against the detached V0 candidate specified there. Before any other service start or real microphone/Agent/tool validation, read and follow `docs/zh/live-voice/E2E_RUNBOOK.md`.

Read `docs/zh/live-voice/POST_V0_STASH_HANDOFF.md` only for historical forensics or disaster recovery. A fresh clone is not expected to contain its machine-local stash, and normal development must never reconstruct, apply, pop, or drop that stash. Read `docs/zh/live-voice/FULL_SOLUTION_2026-07-30.md` completely when the task affects long-term architecture, P1/P2/P3 boundaries, protocols, state ownership, cancellation, presented history, durability, or production acceptance; it is a dated immutable source snapshot, not the current task list.

The immutable validation baseline is the V0 vertical-slice candidate at the SHA recorded in `STATUS.md`; V0 remains unreleased until `V0_ACCEPTANCE.md` passes. D-030 ended the temporary stash boundary: develop, review, commit, and push Post-V0 work normally, then validate V0 later from a separate checkout/worktree at the immutable SHA. The next accepted slice is the poll-backed non-blocking task monitor in D-031; do not silently expand that slice into full P3. Apply D-033/D-034: current Web owner/project scope is single-user request consistency, not authentication; D-031 only promises same-page reconnect recovery, not full-page reload, and must preserve real terminal/error fields without inventing outcomes. The Demo must send final speech transcripts to the real JiuwenSwarm Agent and tools; it is not an ASR/TTS-only showcase. Do not present Demo shortcuts as production-complete capabilities.

At the start of a resumed Live Voice task, run `git status --short --branch`, `git rev-parse HEAD`, and compare the local branch with its upstream. If a handoff snapshot and Git disagree, treat the pulled remote branch as the implementation fact, report the mismatch, and update the handoff instead of silently using stale text.

On a fresh clone, use the clone/bootstrap commands in `docs/zh/live-voice/README.md`. Source, decisions, tests, and continuation state come from Git; model credentials, user configuration, project registration, browser permission, audio-device selection, and network availability do not. Do not claim full runtime parity until those private conditions have been re-established and the relevant E2E gate has passed.

Every Live Voice module or logical slice must follow D-032 and the mandatory test-closure gate in section 3.1 of `docs/zh/live-voice/POST_V0_DELIVERY_ROADMAP.md`. Before semantic implementation, re-read the relevant solution, current stage, module contract/decisions, and existing tests, then record the module definition, test inventory, why each test exists, and the complete scenario matrix in `docs/zh/live-voice/STATUS.md`. After implementation, repeat that review against the actual diff and final tests. Positive business scenarios must succeed; negative business scenarios must be rejected or fail closed, with forbidden side effects explicitly asserted as zero, while the test process itself passes. Test counts or line coverage alone never prove module closure. Missing coverage or an unexplained `N/A` means the slice is `PARTIAL` or `BLOCKED`, not `CLOSED`.

After material Live Voice work:

- update `docs/zh/live-voice/STATUS.md` with progress, verification, known issues, and the next concrete actions;
- update the D-032 pre/post review, test inventory, scenario-to-test mapping, exact tested SHA, commands, and remaining gaps for every affected module;
- update `docs/zh/live-voice/DECISIONS.md` when scope or a technical choice changes;
- update the Shortcut Ledger in `TWO_WEEK_DEMO.md` when adding or removing a temporary limitation;
- normally commit and push the documentation with the related code so another machine can resume from Git alone; D-030 ended D-022's temporary pre-V0 stash window, so keep `2c700934` as the immutable unreleased V0 Candidate and commit later Post-V0 work without relabeling it as V0 evidence.

User instructions and newer accepted decisions take precedence. If code and documents disagree, record the gap instead of silently treating the current code as the intended final design.
