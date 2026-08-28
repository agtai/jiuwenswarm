# Test branch assembly plan

Verified against `local/deployed` = `d0a1af08c` (jiuwenswarm) and `80a53799` (agent-core)
on 2026-08-18. Nothing in this document has been assembled; it is a plan only.

Verification method: not subject comparison. Each candidate was checked by
content — patch-id equivalence (`git cherry`), simulated merges
(`git merge-tree --write-tree` and real merges in a throwaway detached
worktree), and, where those were ambiguous, by grepping `local/deployed`'s
actual files for the marker the commit introduces.

## Summary

`local/testing` (`cba187d79`) is a sound base and should be refreshed, not
rebuilt. It already carries eight of the eleven wanted branches, including two
whose standalone branches must *not* be merged. Three feature branches and the
five in-flight ones remain to be added.

Total remaining work on the verified material: three merges, two conflict
hunks, one of which needs real code.

## Include list

Everything below is genuinely absent from `local/deployed` and wanted.

### Already carried by `local/testing` — no action needed

Verified by simulated merge into `local/testing` returning no net change, and
for the cherry-picked ones by diffing the changed lines against the original
commit (identical; only line offsets differ).

| Branch | Evidence |
|---|---|
| `fix/cron-and-log-hardening` | merge into `local/testing` yields no net change; all 3 commits present |
| `work/interrupt` | no net change; `b4d67050c`, `2357519e3` present |
| `work/slack-ack-legacy-mapping` | no net change; `bfa8b8741`, `b6e8ca50a` present |
| the per-channel branch | no net change; `958a4d81f`, `6d61af428` present |
| `chore/reconcile-skill-sources` | no net change; `a9dd2d86b` present |
| `fix/per-session-cwd-propagation` | cherry-picked as `6639afb2a` ≡ `96a951f72` and `ebc8ed939` ≡ `9a06339ca` — changed lines identical |
| `local/venv-path` | cherry-picked as `5c60ee10b` ≡ `e3218d311` — changed lines identical |
| `fix/image-fallback-notice-localisation` | cherry-picked as `cf834cd1e` ≡ `a68c2f502`, plus a follow-up `6fc250db0` the standalone branch lacks |

### To be merged

| Branch | Tip | Content | Conflict |
|---|---|---|---|
| `local/deployed` | `d0a1af08c` | 11 pr-tracker commits `local/testing` predates | none — merges clean |
| `fix/ai-news-gate-hardening` | `5c75eb64b` | 12 files, 5,784 lines, all new paths under `local_skills/ai-news-monitor/` and `tests/unit_tests/local_skills/` | none — merges clean |
| `feat/slack-date-time-pickers` | `084524dc1` | Block Kit input framework: `slack_inputs.py` (1,156 lines) + 2,949 lines total | see below |
| `feat/slack-approval-button-styles` | `cc0b2ee0c` | `_option_button_style()` + 181 test lines | see below |

## Exclude list

Each exclusion names the specific replacement. Assessed per commit, not per
branch.

### `fix/ai-news-recording-gate`, `fix/ai-news-provenance-gate`, `local/ai-news-monitor-hardening`

All three are **ancestors** of `fix/ai-news-gate-hardening`, not divergent
lines. `local/ai-news-monitor-hardening` and `fix/ai-news-provenance-gate` are
literally the same SHA (`d387be3b0`). `git merge-base --is-ancestor` returns
true for all three; `git cherry` emits nothing.

Content check, since an ancestor can still hold something a descendant
reverted: file sets identical except gate-hardening *adds*
`test_ai_news_monitor_run_dir.py`; no test function, no `ledger.py` or
`check_links.py` function is missing; removed lines are rewrites, not losses
(`$RUN`/`mktemp -d` → `<run>`/`ledger.py start-run`). Nothing outside the skill
directory is touched. **Nothing needs cherry-picking.**

### `fix/digest-skill-output` — all 9 commits

`local/deployed` is a strict superset: 5,635 insertions ahead across
`digest.py`, `render_report.py`, `fetch_repository_activity.py` and four test
files. `check_report_language.py` is byte-identical (blob
`ad71ee3a6a0d2a939b396b669d617c282cff2df8` on both). No file exists on the
branch that `local/deployed` lacks — `local/deployed` has three the branch
lacks (`findings-schema.md`, `digest.py`, `render_report.py`).

Per commit: eight reverse-apply cleanly against `local/deployed`;
`9a818222d` ("resolve the digest fetcher's state file independently of the
cwd") is confirmed by its marker `_runtime_data_dir`, present in
`local/deployed:local_skills/repository-activity-digest/scripts/fetch_repository_activity.py`.
The claim holds for all nine.

### `work/slack-trio` and `work/fullv2-deploy`

Between them, 8 commits lack a patch-equivalent. Per commit:

| Commit | Verdict | Replacement on `local/deployed` |
|---|---|---|
| `7c57da8f3` port probe | superseded | `155c7cdef` — two-stage `_bind_listen_probe()` + `_reuseaddr_bind_probe()`. Also carries the `_FAMILY_UNAVAILABLE_ERRNOS` fix that `7c57da8f3` lacks entirely (the old code used `getattr(socket, "EADDRNOTAVAIL", 99)`, always falling back to the Linux value and misreading macOS's 49). **Replaying ours would conflict on exactly the comment block `155c7cdef` rewrote, and resolving toward ours reverts the errno fix.** The operator's regression warning is correct. |
| `2d82d1264` permission tokens | superseded | `5878c065f` — `resolve_permission_action()` over `PERMISSION_OPTION_ALIASES` in `permission_options.py`. All 19 tokens the commit adds are covered; `local/deployed` additionally accepts `accept`, `接收`, `接受`, `reject_once`, `keep_planning` and all case/separator variants. |
| `965df889c` fallback option value | superseded | `5a200dcad` — `_DEFAULT_INTERRUPT_OPTION_TEXT` / `_default_interrupt_options()` taking values from `permission_options` |
| `3d2898bb4` buttons in configured language | superseded | `71095f2c9` — `_resolve_interrupt_ui_language()` + `cn`/`en` table |
| `9e519df0c` acknowledge with a reaction | superseded | present on `local/deployed`; `work/slack-ack-legacy-mapping` (already on `local/testing`) carries the newer `off` mapping on top |
| `43dea126e` free-search env opt-in | superseded | same content as `49c122403`, present |
| `b3bdd1952` English cron strings | superseded | present |
| `2217208b4` unquoted `blockkit_tables` mode | superseded | present |

`6afaa52eb`, `4ee4d4bd6`, `8b231edfd` on `work/fullv2-deploy` are byte-identical
duplicates of `2d82d1264`, `965df889c`, `3d2898bb4`. The operator's guess that
some absent commits were merge commits from the old workflow was wrong — all
eight are real commits, and all eight are superseded.

**Neither branch may be merged in any case**: both are based on `3270b5f3a`, so
a merge re-adds ~1,000 lines of pre-rebase formatting alongside the current
code.

### Branches whose one wanted commit is already carried — do not merge

These sit on stale or upstream bases. Merging any of them drags in thousands of
lines. Their wanted content is already on `local/testing` (see the include
list).

- `local/venv-path` — 47 commits, 5 without a patch-equivalent, only
  `e3218d311` wanted, already carried as `5c60ee10b`. A merge would add 1,053
  duplicate lines across 19 files.
- `fix/image-fallback-notice-localisation` — 20 commits absent, 19 of them
  upstream. Only `a68c2f502` is ours, already carried as `cf834cd1e`. A merge
  would drag 75 files / 4,373 lines of upstream.
- `fix/per-session-cwd-propagation` — based on `upstream/develop`; a merge
  drags 492 files / 38,732 lines. Both its commits are already carried.

### Superseded singles

| Commit | Replacement |
|---|---|
| `97fab08962` pinned port relocation | `c839dbaa3` — `pinned_port_types()`, `_reject_pinned_port_conflicts()` |
| `507da0627` fallback tests, no real probe | `3658c15b0` — the three `TestStartServicesFallback` fakes |
| `e284f778e` permission prompt wiring | `46a6e0957` — `_resolve_permission_prompt_texts()` |
| `fdf3d79f3` permission option decode | `5a200dcad` |
| `bc87557c05` + `c89209013` cron store after migration | `e69b21b49` + `dc2176d63` |
| `2da497a1c` symphony index cache per user | present — `_current_user_tag()` at `storage.py:153`, `user_cache_root()` at `:164` |
| `1954630ab` gateway log out of shared temp | present |
| `384470c58` interrupt envelope dedup | present (exact reverse-apply) |
| `49c122403` free-search runtime defaults | present |
| `132f27fa7`, `87d3d5e5f`, `743aec7df`, `ee8493475`, `1dcedfb68`, `0ff20a2e4`, `ea17f8051`, `3c7e4880c` | all present (exact or 3-way reverse-apply) |

### Deferred

**`fix/systemd-unit-staging` (`0cff9f4b6`) — defer, claim confirmed.**
`local/deployed:deploy/yuanrong/gateway_handler.sh` contains **zero**
occurrences of the string `systemd`. The section it hardens arrives only with
upstream `700cb7db3`. The commit replaces `/tmp/${svc_name}.service.$$` with
`mktemp` plus an EXIT trap — sound, but it has nothing to apply to until the
upstream rebase. Defer to the rebase; do not include.

### Not ours

`pr-1426` (`20c01986d`), `pr-2480` (`c96550f42`) — third-party upstream PR
refs. Exclude. Confirmed: neither is authored by us.

## Merge order

Base: `local/testing`.

```
1. merge local/deployed                  clean
2. merge fix/ai-news-gate-hardening       clean  (all-new paths)
3. merge feat/slack-date-time-pickers     clean at this point
4. merge feat/slack-approval-button-styles  2 conflict hunks
```

Steps 1–3 were run for real in a throwaway detached worktree and merged
cleanly. Step 4 is the only conflict, both hunks in
`jiuwenswarm/gateway/channel_manager/im_platforms/slack/slack_connect.py`:

**Hunk A — adjacency, mechanical.** The per-channel branch (already on
`local/testing`) and `feat/slack-approval-button-styles` inserted module-level
definitions at the same point. No name collides: ours defines
`SlackChannelOverride`, `_resolve_override_mode()` and a per-channel resolver;
theirs defines `_option_button_style()`. **Resolution: keep both.**

**Hunk B — semantic, needs code.** The two Slack branches widened the same
structure incompatibly:

- `feat/slack-date-time-pickers`: `options: list[tuple[str, str, str]]`
  (label, value, description) and adds `inputs: list[QuestionInput]` to
  `_SlackPendingQuestion`.
- `feat/slack-approval-button-styles`: `options: list[tuple[str, str, str, str]]`
  (label, value, description, intent) and adds `withdrawn_at: float | None`.

The merged form needs a 4-tuple carrying description *and* intent, plus both new
dataclass fields, and the four call sites updated (branch lines 1384/1397/1407/1615
against 1360/1374/1386/1459). Reversing the order does not avoid this — verified
by simulating both orders with a union resolution; either way it is one
mechanical hunk plus this one. **Both branches' test suites must be re-run after
the reconciliation** — this is the only step in the assembly that is not
mechanical.

### Note on rerere

`rerere.enabled` is true with 77 pre-existing entries. The simulation recorded a
union resolution for Hunk A, which will auto-apply during the real assembly.
That resolution is correct, but it was produced by a simulation rather than
reviewed at the time — check it rather than accepting it blind.

### The five in-flight branches

Merge last, after they are finished. Current state (tips move as they are
written):

| Branch | State | Files |
|---|---|---|
| `feat/slack-approval-button-styles` | **ready** (`cc0b2ee0c`) | `slack_connect.py`, `test_slack_approvals.py` |
| `feat/structured-inputs-wiring` | in flight | `interrupt_helpers.py`, 2 test files |
| `feat/cron-status-record` | in flight | `cron/scheduler.py`, `routing/agent_client.py`, 1 test file |
| `feat/slack-rich-blocks` | not started (tip = `local/deployed`) | — |
| `fix/pr-tracker-report-polish` | not started (tip = `local/deployed`) | — |

The file-ownership partition is holding so far: the two branches with commits
touch disjoint files and neither has touched `slack_connect.py` yet. The
predicted collision is `feat/slack-rich-blocks` against the pickers/styles
reconciliation in `slack_connect.py`, and `feat/structured-inputs-wiring`
against `feat/slack-date-time-pickers` — the wiring branch is built on the
pickers framework, so it should be merged after it, not in parallel.

## agent-core

**No assembly work is needed. `local/deployed` (`80a53799`) carries everything.**

The reported straggler `f9ddc3b0` "local: tell the model the absolute directory
of every skill" is a **false positive of a SHA-based check**. Its behaviour is
present on `local/deployed`, in a strictly better form, via a three-commit
split: `9cba243e` (list each skill's absolute directory in the prompt),
`bd051b21` (keep the skill directory in the skill_tool result text),
`7b0a3c49` (list the skill directory for skills added mid-session).

`f9ddc3b0` was the rough hand backport onto an older base — its own message says
so. The split series is the polished rework that landed. Evidence:

- `openjiuwen/harness/tools/skills/skill_tool.py:283` has
  `SKILL_DIRECTORY_HEADING = "## Skill directory"` byte-identical to `f9ddc3b0`.
- `openjiuwen/harness/prompts/sections/skills.py:142` renders
  `"\n   Directory: {skill_directory}"`; the CN and EN header paragraphs are
  verbatim at `:47` and `:57`.
- `openjiuwen/harness/rails/skills/skill_use_rail.py` passes `skill_directory=`
  at **four** call sites (483, 641, 664, 689); `f9ddc3b0` has only two.

**Taking it would regress three things**: it drops the mid-session render sites,
drops the guard in `_skill_directory()` (`skill_use_rail.py:849`) that returns
`""` for an empty or `"."` directory instead of resolving to the process CWD and
advertising a path the skill is not in, and reverts the newer `language`
separator parameter. It also carries no tests, against ~294 lines on the
resident version. A cherry-pick onto `local/deployed` conflicts in two files,
and resolving toward HEAD yields an empty commit.

Two further apparent stragglers were checked and are the same false positive:

| Reported | Actually |
|---|---|
| `24cd3952` on `work/agentcore-full` etc. | changed lines **identical** to `6e878cf2` on `local/deployed` |
| `5786330261` on `fix/subagent-skill-sandbox` | changed lines **identical** to `6e878cf2` |

`git cherry local/deployed <branch>` returns zero non-equivalent commits for
`work/agentcore-v4`, `-v5`, `-v6`, `work/interrupt`, `work/skillpath` and
`fix/skill-directory-in-prompt`.

**Process note:** the straggler check that produced `f9ddc3b0` compares SHAs, so
it will re-flag these three on every future assembly. Suppress them explicitly,
or switch the check to `git cherry -v`, which gets all three right.

## Base recommendation

**Refresh `local/testing`. Do not rebuild.**

- It already carries 8 of the 11 verified-wanted branches, and does so
  *correctly* — the cherry-picked commits were diffed against their originals
  and the changed lines are identical.
- It carries two things a rebuild would get wrong: the `local/venv-path` and
  `fix/image-fallback-notice-localisation` fixes exist there as clean
  cherry-picks. Rebuilding by merging those branches would drag in 1,053 and
  4,373 lines of stale or upstream content respectively.
- It carries `6fc250db0`, a follow-up to the image notice that exists on no
  standalone branch. Rebuilding from branches alone would silently lose it.
- `local/deployed` merges into it cleanly, so the refresh is free.
- It also holds all the docs/design commits, so nothing is lost by keeping it.

Branching fresh off `local/deployed` costs three extra cherry-picks, risks the
two stale-branch traps above, and gains nothing.

## Docs and design branches

`docs/*` and `design/*` carry no code. All but four are already fully contained
in `local/testing`. The stragglers are one commit each of genuine design
material plus, in one case, only `local/deployed` commits:

- `docs/rebuild-validation-checklist` — 1 own commit (`fc78ba51c`); the other 11
  are `local/deployed`'s pr-tracker commits
- `design/cron-status-record` — `89a96bed4`, `da19279f5`
- `design/structured-user-inputs` — `29d898e4f`, `120bed14b`
- `design/rich-block-rendering` — `ee09c1e6f`

**Recommendation: fold them in.** They are the design documents for three of the
five in-flight branches, they cannot conflict with code, and keeping the design
next to the implementation on the test branch is worth more than the tidiness of
leaving them out.

## Open decisions — operator judgement, not fact

1. **Hunk B reconciliation.** Whether the merged `options` tuple should carry
   intent as a fourth positional element or whether this is the moment to
   replace the tuple with a small dataclass. The tuple has now been widened
   twice independently by two branches, which is evidence for the dataclass, but
   it is a design call and it enlarges the change.

2. **`fix/systemd-unit-staging`.** Confirmed it has nothing to apply to until
   the upstream rebase brings `700cb7db3`. Deferring is the safe reading, but if
   the rebase is imminent the commit could be held with it rather than parked
   separately.

3. **`7c57da8f3`'s TIME_WAIT test.** `local/deployed` has no literal TIME_WAIT
   probe test; `test_is_port_available_ignores_lingering_connection_sockets`
   covers the FIN_WAIT_2 variant of the same mechanism. Porting the one test is
   cheap and independent of the superseded commit. Worth doing or not — a
   coverage judgement.

4. **Rebasing `fix/ai-news-gate-hardening`.** It merges cleanly as-is, but its
   base (`66235fc1d`) is 116 commits behind `local/deployed`, so any tree-level
   `git diff` against it is unreadable. Rebasing before merging costs little and
   makes the branch reviewable; merging as-is is faster.

5. **Whether the skill running in production matches `fix/ai-news-gate-hardening`.**
   The brief states the ai-news skill is live but absent from git. This plan
   verifies the branch is a superset of the other three ai-news branches; it
   does **not** verify the branch matches what is deployed under
   `~/.jiuwenswarm/`, which was out of scope. That comparison should happen
   before the test branch is treated as authoritative for this skill.
