# Repository agent guidance

## Live Voice tasks

Before planning, implementing, reviewing, or testing Live Voice work, read these files in order:

1. `docs/zh/live-voice/README.md`
2. `docs/zh/live-voice/HANDOFF.md`
3. `docs/zh/live-voice/STATUS.md`
4. `docs/zh/live-voice/TWO_WEEK_DEMO.md`
5. `docs/zh/live-voice/V0_ACCEPTANCE.md`
6. `docs/zh/live-voice/DECISIONS.md`

Before starting services or running real microphone/Agent/tool validation, also read and follow `docs/zh/live-voice/E2E_RUNBOOK.md`.

Before preparing or presenting the fixed showcase, also read `docs/zh/live-voice/DEMO_SHOWCASE.md`.

Read `docs/zh/live-voice/FULL_SOLUTION_2026-07-30.md` completely when the task affects long-term architecture, P1/P2/P3 boundaries, protocols, state ownership, cancellation, presented history, durability, or production acceptance.

The current implementation milestone is the two-week V0 vertical-slice candidate unless the user explicitly changes it. A commit is a recoverable candidate, not evidence that V0 acceptance passed. The Demo must send final speech transcripts to the real JiuwenSwarm Agent and tools; it is not an ASR/TTS-only showcase. Do not present Demo shortcuts as production-complete capabilities.

At the start of a resumed Live Voice task, run `git status --short --branch`, `git rev-parse HEAD`, and compare the local branch with its upstream. If a handoff snapshot and Git disagree, treat the pulled remote branch as the implementation fact, report the mismatch, and update the handoff instead of silently using stale text.

After material Live Voice work:

- update `docs/zh/live-voice/STATUS.md` with progress, verification, known issues, and the next concrete actions;
- update `docs/zh/live-voice/DECISIONS.md` when scope or a technical choice changes;
- update the Shortcut Ledger in `TWO_WEEK_DEMO.md` when adding or removing a temporary limitation;
- commit and push the documentation with the related code so another machine can resume from Git alone.

User instructions and newer accepted decisions take precedence. If code and documents disagree, record the gap instead of silently treating the current code as the intended final design.
