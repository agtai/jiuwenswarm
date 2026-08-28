# A template merge deletes any config key the template does not list

First written 2026-08-27. **Superseded in part — read the status section
below before acting on anything here.** The original analysis concluded the
behaviour was dormant on a running install. That conclusion was correct for the
tree it was written against and became false the same week: upstream armed it on
every start, it destroyed live configuration four times, and it is now fixed on
a branch that is not yet merged.

Line numbers throughout have been removed in favour of function and module
names. Every line number in the original had rotted within four days.

## The mechanism

`_deep_merge` (`jiuwenswarm/common/config.py`) built its result by
iterating over the **template's** keys only:

```python
for key, template_value in template.items():
    if key not in user:
        result[key] = template_value
    elif isinstance(template_value, dict) and isinstance(user.get(key), dict):
        result[key] = _deep_merge(template_value, user[key], depth + 1)
    else:
        result[key] = user[key]
return result
```

A key the user has and the template does not is never reached, so it is never
copied into `result`. It is **dropped silently** — no warning, no log line, no
backup. `migrate_config_from_template` then wrote the merged result
over the user's file. Its docstring states the intent outright: *"Remove:
deprecated fields not in template (cleanup)."* This is designed behaviour, not a
bug, and it is the correct design for retiring a key. It is only dangerous
because the template is easy to forget to update.

**One real limit.** `_deep_merge` returns the user's subtree unchanged at
`depth >= 4`, so pruning does not reach keys nested five or more levels deep.
Anything shallower is exposed. Do not rely on this — it protects the deepest
config only, and the nesting depth of a given key is not obvious by eye.

## Status, 2026-08-31

| | |
|---|---|
| the deletion behaviour | **fixed** on `fix/config-template-merge-data-loss`, open as **PR #4365**, issue **#4362** |
| the template's missing keys | branch `pr/template-missing-keys`, issue not yet filed |
| the legacy heartbeat-probe migration | broken, and *worse* once the merge is additive — own fix, not yet filed |
| a test-suite guard | **not built** — see "Outstanding" below |

## When it fires — the original analysis, and why it stopped holding

As first written, `migrate_config_from_template` had exactly one caller,
`prepare_workspace`, and three of the four entry points reaching it carried a
guard, so a normal start with an existing config never merged. Only
`jiuwenswarm-init` merged unconditionally. That is why this deployment carried
retired keys for weeks without losing anything.

Upstream commit `bdfdeaf35` (2026-08-27, the day after this document was
written) removed that property. It added
`ensure_config_migrated_from_template()` and called it at **module scope** in
`jiuwenswarm/app.py`, `gateway/app_gateway.py` and
`server/app_agentserver.py` — on the line immediately *after* the existing
guard, outside it. Two consequences, and the second is the one that caused the
damage:

- every service start merges, rather than only a first run or a migration;
- **importing any of those three modules merges**, so running the test suite
  does it. `tests/conftest.py` has no workspace isolation, and several unit
  tests import those modules at module scope.

It then fired for real, four times: 2026-08-24 (which also took the cron
scheduler down — `prepare_workspace` reaches a `shutil.rmtree` of `agent/home`
while the cron store still resolved there), 2026-08-28, and three times on
2026-08-31 between 00:08 and 00:29. Every occurrence was a test run, never a
service start. Each was silent apart from one INFO line in a module log.

**The template applied is a property of the process, not of the config.** The
merge uses whatever template ships with the tree the running Python came from.
Our template carries 41 `channels.slack` keys; upstream's carries 7. So a test
run from an upstream-based worktree deletes our connector's keys, and a later
run from our own tree re-adds some of them as bare defaults. On a machine with
several checkouts, "is our key in the template?" is not a well-defined question
— it is well-defined only per process.

## What the fix changes

`fix/config-template-merge-data-loss` (PR #4365) makes `_deep_merge`
**additive by default**: pruning becomes an opt-in `prune` parameter that no
caller enables, every pruned key is logged at WARNING with its dotted path plus
a count, the merge mutates in place so ruamel round-trip data survives, and the
`depth >= 4` bound becomes a plain recursion guard.

That bound was incoherent in both directions and the second direction was
missed for months: it blocked *additions* as well as deletions, so 69 keys in
the shipped template could never reach a user config at all.

Note also that rebuilding the mapping into a fresh `dict` discarded **every
comment, quote style and anchor** on each write. The `# restored 2026-08-24`
annotations this deployment used to guard hand-added keys were never going to
survive.

## Why this matters for the machine migration

Copying `config.yaml` to a new machine and then running `jiuwenswarm-init` to
set the workspace up is the obvious sequence, and it is exactly the sequence that
prunes. The keys most likely to be lost are the ones a local feature added
without a matching template entry — precisely the settings that make this
deployment work, and precisely the ones nobody will notice missing until the
feature silently stops behaving.

**Practical rule for the migration:** copy the config, and do **not** run
`jiuwenswarm-init` against it. If init must be run, diff the file before and
after and restore anything dropped.

## The inventory, now run

The key set was reconstructed from every borg archive and merged against the
shipped template: **70 subtree roots** would be lost, and exactly **one** was
ours — and that one needs no template entry, because a pre-merge migration
already translates it. Our connector had added its keys to the template
alongside the code that reads them, since 2026-08-13.

The other 69 are upstream's own: keys upstream's code reads and upstream's
template never shipped, which makes them unconfigurable on any fresh install.
`permissions.owner_scopes` is the sharpest case — upstream ships it as `{}`
"empty by default", upstream's own settings page writes into it, and the merge
then empties it. An empty mapping is *worse* than an absent key here: `{}` is
treated as the complete set of allowed sub-keys, so it deletes every child.

Two exclusions are worth recording because they look like omissions:
`modes.team.jiuwen_team.enable_permissions` was deliberately removed upstream in
merged PR #3162, and the legacy heartbeat probe keys are a separate defect.

## The rule this implies for our own work

**Any branch that adds a config key must add it to
`jiuwenswarm/resources/config.yaml` in the same commit.** Not the deployment's
config — the shipped template. A key that works locally because it was hand-added
to the live file will be deleted the first time a merge runs, and the failure
will surface long after the change that caused it, as a feature quietly
reverting to its default.

An open-ended map — one whose keys are operator-chosen, like a per-channel
override table — must ship as a **bare key**, not as `{}` and not only as a
commented example. `{}` is read as the complete set of allowed sub-keys and
deletes every child the operator added; a bare key preserves them.

**These rules protect us only against our own build.** They do nothing about a
test run or a worktree on a different base, which carries a different template.
That is what the outstanding item below is for.

## Outstanding: a test-suite workspace guard

**Not built.** The suite can still rewrite the operator's configuration, and the
only thing preventing it is discipline — every person and every agent
remembering to set `HOME`, `JIUWENSWARM_HOME`, `JIUWENSWARM_DATA_DIR` and
`TMPDIR` on the pytest process. That discipline has failed repeatedly, including
by people who had just finished reading about the hazard.

The paths freeze at import — `get_user_home()` and `get_user_workspace_dir()`
cache into module globals on first call, and `common/config.py` binds its config
path at module scope — so **a fixture cannot move them**. It can, however,
*refuse to run*:

> At collection time, before any `jiuwenswarm` module is imported, resolve where
> the workspace would land. If it is under the real home, abort the session with
> a message naming the four variables. Do not attempt to repair it.

Cheap, engine-independent, and it converts a silent corruption into a refusal to
start. It is deliberately **not** part of PR #4365: it takes effect before every
import, so it changes every test's environment and needs its own parity
evidence, and bundling it would give a reviewer reason to stall a narrow fix.

Two related notes for whoever builds it. Detection must compare the live file's
**mtime and sha256** before and after a run — grepping output for the migration
log line is not sufficient, because these loggers do not propagate and the line
is often absent from captured output. And a container gives a stronger guarantee
than any fixture, because it makes the file *unreachable* rather than merely
*unreferenced*; that work is tracked separately.

See [[retro-compat-for-unshipped-features.md]] for the neighbouring question of
which legacy keys are worth carrying at all.
