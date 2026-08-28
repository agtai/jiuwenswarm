# Rebundle map — where everything is

**Transient.** Written to stop a mistake during the rebundle, not to last. Delete
it when the exercise finishes.

Updated 2026-08-28.

## Refs that matter

| ref | sha | what it is |
|---|---|---|
| `local/deployed` | `0e17f61e1` | **what the running venv is built from.** Still live, still the revert target, still moves on every deploy |
| `local/rebundled` | `48514ee1f` | stage 1 output. Tree was **identical** to `local/deployed@0e17f61e1` before this note was added |
| `3f3cdbb7f` | — | the upstream commit both branch from. Stage 1's base |
| `upstream/develop` | moves | 244+ commits ahead of the base. **Not used until stage 3** |

Off-machine, on remote `private`:

```
hr/2026-08-28-15h20-pre-rebundle      local/deployed before stage 1
hr/2026-08-28-16h10-rebundle-stage-1  local/rebundled after stage 1
```

`local/deployed` on `private` is stale (2026-08-13); the dated snapshots are the
real record.

## The stages

```
[done] 1  local rebundle       327 commits -> 68, against the OLD base, no upstream
       2  make bundles separable   extract entangled hunks/commits
       3  rebase onto upstream
       4  PR texts, pr-review, filing
```

Stage 1 deliberately did **not** apply the drop decisions (D1 `23be6adf6`,
D2 the `acknowledge_requests` shim) — dropping them would have broken tree
equality, which was the only mechanical check. They apply at stage 2. `23be6adf6`
sits in the `X-LOCALONLY` bundle for that reason.

## What stage 1 produced

68 commits: 12 local material, 38 single-concern, 18 shared-file.

- **6 bundles are separable now.** The 12 local-material commits are final.
- **38 bundles are not** — their changes sit inside files another bundle landed
  whole. `GW-20` holds hunks for 69 other bundle-file pairs, `GW-21` for 31,
  `GW-22` for 27. Splitting those three unblocks most of the rest.
- 8 files carry 8-19 bundle claims each; `slack_connect.py` alone is 9,700 lines
  of the diff and is claimed by 19.

Each shared-file commit says so in its own message, so `git log` is honest about
which commits are entangled.

## Artefacts, and the fact that they are not backed up

Everything the rebundle was planned from lives under
`/tmp/claude-1003/<session>/scratchpad/rebundle/`:

```
SHARED.md               definitions, constraints, four addenda of decisions
MAP-gateway.md          23 bundles
MAP-runtime.md          17 bundles
MAP-skills-docs.md      local verdicts + 1 upstreamable find
LEAK-SWEEP.md
inventory.psv           one row per commit
file-to-bundle.psv      126 files -> bundle
split-files.psv         37 entangled files and what distinguishes their hunks
bundle-order.txt        52 ids, topologically ordered
commit-to-bundle.psv    (being built) commit -> bundle, the key stage 2 needs
```

**`/tmp` does not survive a reboot or the migration.** Copy this directory
somewhere durable before either.

## Traps already paid for

- **Identity.** The repo config carries the right one. Do not export
  `GIT_AUTHOR_EMAIL` in a commit loop — it silently stamped the wrong address on
  68 commits before anyone read `%ae`.
- **`local/deployed` has 13 docs commits with that wrong address.** Left alone:
  they are superseded on `local/rebundled` by one commit with the right identity.
- **Attribution.** `research-material-analysis` is authored by
  `hongxing <hongxing1227@gmail.com>` outright; `repository-activity-digest` and
  `slack-channel-digest` carry `Co-authored-by` for the same person.
- **Branch noise.** 225 local branches, 133 worktrees, ~100 of them under `/tmp`.
  All 49 `worktree-agent-*` branches were checked by patch-id: every commit is
  already on `local/deployed`. Safe to delete; not yet done.
