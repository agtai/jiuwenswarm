# D117 post-9b8 commit audit and merge decision

> Frozen review record for `9b8ede225dcc0c421c253a71358ffd676c4aad1b..dc6464bd1b6bcdaeac0b63a225e4f32961f86df2`
> on 2026-08-13. Current state remains authoritative in
> [STATUS.md](STATUS.md). This review prepares S7 but does not execute or pass
> S7/A2.

## 1. Scope and result

- Stage boundary: completed S6/A1, preparing S7/A2.
- Review scope: every commit after the W3 rebaseline commit `9b8ede22` through
  the S6 physical-closure commit `dc6464bd`.
- Range shape: 36 linear commits, zero merge commits, 115 changed files,
  48,763 insertions and 1,617 deletions.
- Upstream relation at review: 27 range commits were already in
  `origin/hx/0812_live_voice_w3`; the current branch was nine linear commits
  ahead. No remote update was performed.
- Claude attribution: 21 commits carry
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`; all 21 are ancestors
  of the configured upstream and of current HEAD.
- Result: no actionable correctness, authority, privacy or merge-blocking
  finding was located in the reviewed current result. The commits are already
  integrated and must not be merged or cherry-picked again.

This conclusion combines commit-by-commit diff inspection, current-source seam
review, the existing S6 Tier 2/3 review, current regression reruns and the user's
physical S6 observations. It is not the S7-03 cumulative candidate review.

## 2. Complete range inventory

| Group | Commits | Review result |
|---|---|---|
| Baseline and S6 integration | `2d2499eb`, `2a69c2b8`, `d659c2c8`, `cf67bbc2` | The accepted Alpha plan/baseline and the coherent 87-file S6 integration are present. The integration remains covered by [the S6 review](S6_ALPHA_INTEGRATION_REVIEW_2026-08-12.md) and the current reruns below. |
| Claude code/test commits | `07cd6df8`, `82b2cc5f`, `31ee31ab`, `44b275d5`, `3583c0fe`, `39870d85`, `3fddbd54` | All seven repairs are still present and their affected seams pass. No repair was later reverted. |
| Claude documentation/evidence commits | `d662f81b`, `31844cd9`, `305acd8b`, `18514089`, `bf17828b`, `1f1ed863`, `974bfb11`, `3775224e`, `f689acd3`, `c8b64fc8`, `93093eb6`, `333ab2ca`, `19a1f788`, `e83d4d85` | The records are explicitly frozen snapshots and route current state back to STATUS. Later records correctly supersede their then-open gaps. The private run root was replaced by `<RUN_ROOT>`. |
| Later S6-02 repair and closure | `10062c3e`, `af3dbec4`, `2e4cfeb0`, `70dcc563`, `5b99acc9`, `fe3656ca`, `adb55f30`, `0a495620`, `e6ccb3e9`, `df1abd2c`, `dc6464bd` | Event-scoped synthesis timeout, cold EOT, long playout, scheduled ACK and breath-pause behavior remain in current source; automated and physical evidence close S6-02/S6. |

## 3. Claude code review

The seven code/test commits have distinct, still-valid responsibilities:

1. `07cd6df8` selects the route traceback frame by exact basename, preventing
   the privacy test from inspecting its own canary locals.
2. `82b2cc5f` opens Realtime recognition with `intent=transcription` while the
   transcription snapshot remains in `session.update`.
3. `31ee31ab` accepts the GA transcription item lifecycle and lets a slow socket
   close finish without permanently consuming cleanup capacity.
4. `44b275d5` uses the exported module-level model builder instead of a nonexistent
   adapter attribute.
5. `3583c0fe` awaits `ensure_instance()` for formal Task dispatch instead of
   reading an uninitialized Agent accessor.
6. `39870d85` aligns the P2 Agent profile, fixed media path, GA server-VAD echo
   and Provider-open/EOT arbitration while retaining fail-closed authority.
7. `3fddbd54` gives a full synthesis-event queue bounded backpressure instead of
   truncating ordinary real-time playout.

The later timeout, queue-capacity, browser scheduling and VAD commits refine
different bounds. They do not contradict or undo these seven repairs.

## 4. Documentation review

D110, D111 and D112 intentionally preserve the candidate, upstream and browser
facts observed at their own freeze time. They are not current-state documents.
The configured remote now resolves through `origin`, and Chrome reported
`151.0.7922.137` during this audit rather than the earlier physical-run
`151.0.7922.77`; S7 must freeze the actual browser again rather than rewrite the
historical records.

One later record, D113, still contained absolute worktree/run-root paths. The
content-neutral redaction already prepared on `codex/s7-automation` was applied
separately during this audit. No historical result, command outcome or source
identity changed.

The production build still reports duplicate `empty` i18n-key warnings. Git
blame locates both keys before `9b8ede22`, so they are not a finding against this
range. Existing large-chunk/import warnings are likewise warnings, not a failed
build.

## 5. Verification rerun

- Affected WebChannel, streaming synthesis/recognition, dedicated media, OpenAI
  Adapter, P3 composition, Direct Executor, product registry and D90 integration
  files: `457 passed, 2 skipped` in 190.68 seconds. The two Windows symlink cases
  were the declared skips; no test failed.
- Frontend Browser Audio I/O, device selection, Web lifecycle, integrated Web
  and streaming-speech groups: 102 + 21 + 12 + 318 + 18 = `471 passed`.
- Frontend production build: PASS, 4,640 modules transformed.
- `git diff --check` for the reviewed range: PASS.
- S6 physical observations: PASS as recorded in
  [D116](D116_S6_02_PHYSICAL_CLOSURE_2026-08-13.md).

The automation-only tests on `codex/s7-automation` were also rerun in that
branch's clean worktree: `53 passed`. No real probe or S7 candidate run was
started.

## 6. Merge decision

### Current 36 commits

No merge, cherry-pick, squash or rebase is needed. All 36 commits already form
the current branch's first-parent history. Reapplying any of them would duplicate
changes. Rewriting the first 27 would also rewrite commits already present in the
configured upstream. The nine local commits form a useful defect/evidence chain
and have no technical need to be squashed.

### `codex/s7-automation`

This is the only unmerged local branch whose merge base is after `9b8ede22`. Its
single commit `d2727f20` forks from `2e4cfeb0`; current HEAD has eight later
commits. The branch adds useful S7 runner/probe entrypoints and tests, but its
39-file patch also carries 9,347 insertions, 2,014 deletions and broad formatting
rewrites across 25 existing source/test files. It also predates the long-playout
and breath-pause repairs.

Therefore `d2727f20` must **not** be merged or cherry-picked wholesale. S7-01
should selectively port the S7 runner, five probe entrypoints, shared probe
support, package scripts and their two owned test files onto current HEAD; broad
format-only rewrites and stale copies of existing files stay excluded. The D113
path redaction is the only part consumed before S7.

No other unmerged local branch has a merge base after `9b8ede22`; the many older
task branches are historical inputs, not missing S6 returns.

No remote ref was updated.
