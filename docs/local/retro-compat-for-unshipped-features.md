# Retro-compatibility for features that never shipped

**A task to do before the next round of upstream PRs, not now.** Recorded
2026-08-27 with one worked example; the sweep itself has not been run.

## The rule

A compatibility shim exists to carry *somebody else's* existing state across a
change. If a feature has never been merged upstream, nobody outside this
deployment has that state, so the shim carries nothing. Every iteration we make
on an unmerged branch is invisible to the outside world: what upstream will see
is one squashed commit introducing the final design, with no history of the
shapes it passed through on the way.

**So: a migration between two of our own unpublished iterations is boilerplate,
and should be dropped when the work is squashed for filing.** It is not merely
unnecessary — it is actively misleading, because it documents an "old format"
that no reviewer has ever seen and no user has ever written.

The test is not "did we change this?" but **"could anyone outside have the old
value?"** If the old key never existed in a released version, the answer is no.

## The worked example

`channels.slack.render_tables` replaced `channels.slack.blockkit_tables` and
`channels.slack.data_table_row_threshold`, and
`_migrate_legacy_slack_render_tables` (`jiuwenswarm/common/config.py:1865`) maps
the old pair onto the new key.

Measured against `upstream/develop`:

```
blockkit_tables             0 files
data_table_row_threshold    0 files
render_tables               0 files
```

**All three keys are ours.** The migration translates between two iterations of
our own design, neither of which was ever public. It ships a deprecation path,
a warning at startup, a second warning on every reply, and template comments
documenting a retired key — for a population of one config file.

The contrast in the same module makes the distinction concrete:
`_migrate_legacy_agent_submode_memory` (`:1837`) **is** in `upstream/develop`.
That one is legitimate — upstream has real installs with the old shape. Same
file, same pattern, opposite verdict. The line is publication, not authorship.

Sharpening it further: this shim cannot even do its job here. It is reached only
through `prepare_workspace`, which `app.py:43` and `app_gateway.py:68` guard with
`if not _config_file.exists() or …`, so it never runs on an install that already
has a config — which is every install that would need it. It is dead weight that
also does not work.

**What to do instead**, when the affected population is this deployment: edit the
one config file by hand and delete the shim. A one-line manual edit beats
permanent code carrying a permanent warning.

## Where to hunt, when the time comes

Not yet run. Starting points, in rough order of likely yield:

- **Config migrations.** `jiuwenswarm/common/config.py` — the `_migrate_*`
  family. Two exist today; check each against `upstream/develop` before touching
  it.
- **Deprecation warnings.** Grep the tree for `deprecated`, `no longer read`,
  `has been replaced by`. Each one names a key; each key gets the publication
  test.
- **Alias and fallback tables.** Any `or legacy_name` / `get(new, get(old))`
  chain reading a second spelling of the same setting.
- **Template comments documenting retired keys.** These outlive the code that
  read them and are the cheapest to miss, since nothing warns about a stale
  comment.
- **Schema fields kept "for compatibility".** A field nothing writes any more.

## Before deleting anything

The publication test has to be **measured, not remembered**. Ours-versus-upstream
was wrong twice in this repository on other questions, in both directions, and
the working checkout sits on a branch whose files differ from both. Check with
`git grep <key> upstream/develop` against an explicit ref, never a bare grep of
the working tree — see [[verify-pr-claims-against-the-branch]] in the session
memory for how that has gone wrong before.

Two cases that look like this rule but are not:

- A shim for a key that **was** released upstream, even briefly. Publication is
  the test, not how long ago or how few users.
- A shim protecting **runtime** state rather than config — a stored session, a
  cached artefact, a persisted job. Our own deployment has those, and dropping
  the shim breaks this machine even if it breaks nobody else's.

## Why it is worth the pass

Three costs, in ascending order: reviewer time spent on a path they cannot place;
a permanent warning in the logs of every operator who never had the old key; and
a template that teaches a setting which does not exist. The first is paid once,
the other two forever.
