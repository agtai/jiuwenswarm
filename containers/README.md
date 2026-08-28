# Containerised test runs

Runs the jiuwenswarm suite inside a rootless podman container so that a test
run cannot reach the operator's live configuration.

This is **ours and stays ours** — it is not upstreamed. It is unrelated to
`docker/`, which builds the deployable product and is asserted on by
`tests/unit_tests/test_dockerfile_claw.py`. Do not merge the two.

## Why

Importing `jiuwenswarm.app`, `jiuwenswarm.gateway.app_gateway` or
`jiuwenswarm.server.app_agentserver` calls
`ensure_config_migrated_from_template()` **at module scope**. Merely importing
any of them rebuilds `~/.jiuwenswarm/config/config.yaml` from whichever
template that tree ships, deleting every key the template lacks. Several unit
tests import those modules, and this has destroyed the operator's config more
than once.

The previous mitigation was env-var discipline — setting `HOME`,
`JIUWENSWARM_HOME`, `JIUWENSWARM_DATA_DIR` and `TMPDIR` on the pytest process,
because those paths are cached at import and a conftest fixture runs too late.
It works, but it depends on every person and every agent remembering.

A container makes the host config **unreachable** rather than merely
unreferenced: `~/.jiuwenswarm` is not mounted, so no forgotten variable and no
import-time path caching can find it.

## Usage

```bash
# the common case — current worktree, agent-core from a local checkout
containers/run-tests.sh -w /path/to/jws-worktree --ac /path/to/agent-core

# a single file
containers/run-tests.sh -w . --ac ../agent-core -- \
    pytest -q tests/unit_tests/test_app_agentserver.py

# reproduce CI's interpreter and plugin versions
containers/run-tests.sh -w . --ac ../agent-core --ci-pins

# poke around inside
containers/run-tests.sh -w . --ac ../agent-core --shell
```

The first run builds the venv (minutes). Later runs reuse it (seconds of
overhead). `--refresh-venv` discards it.

## The three code combinations

One image serves all three; the combination is resolved at run time from the
arguments, so there is no image per combination.

| Want | Invocation |
|---|---|
| custom jiuwenswarm + stock/pinned openjiuwen | `-w <worktree>` (optionally `--ac-ref <sha>`) |
| stock/pinned jiuwenswarm + custom agent-core | `-w <worktree at the pinned ref> --ac <path>` |
| custom both | `-w <worktree> --ac <path>` |

jiuwenswarm is always a bind-mounted worktree installed with
`pip install -e "<worktree>[test]"`, so "stock versus custom" is just which
commit the worktree sits at — no separate mechanism needed.

openjiuwen is always resolved as a post-step, which keeps the three cases
symmetric:

- `--ac PATH` → `pip install --no-deps --force-reinstall PATH`
- `--ac-ref REF` → the same, from `git+https://gitcode.com/openJiuwen/agent-core.git@REF`
- neither → the requirement `pyproject.toml` declares, reinstalled if the venv
  currently holds something else, so switching back from `--ac` genuinely
  reverts instead of quietly keeping the custom build

That last case has a real limit. The declared requirement is
`openjiuwen @ git+…@develop`, a moving branch, and the stamp hashes the
*declaration*, not the commit it resolves to. Two runs days apart can read as
the same identity while installing different commits — `develop` moved from
`798c3c95` to `4139e10a` during a single afternoon of this work. Pass
`--ac-ref <sha>` when a run has to be reproducible.

### The `[test]` extra is load-bearing

`pip install -e <worktree>` without `[test]` lets `a2a-sdk` resolve
transitively and drift to 1.1.2. The extra pins `a2a-sdk[http-server]==1.0.0`
and supplies pytest, coverage and asyncssh. The entrypoint always uses it.

### `--no-deps` is checked, not assumed

openjiuwen's dependencies are installed during the jiuwenswarm resolve, not by
the override, so the override runs `--no-deps`. That is only safe while the
override declares nothing new. `pip check` runs immediately afterwards and the
run aborts with exit 3 if it fails, rather than surfacing as an ImportError
somewhere in the middle of the suite.

## Caching and invalidation

Two layers, because they change at very different rates.

**The venv** lives in a named volume `jws-venv-<key>`, where the key hashes
everything that changes the resolved dependency closure and nothing that does
not: image ID, Python version, the selected extras, the `--ci-pins` flag,
`--venv-tag`, and the sha256 of `pyproject.toml`.

The worktree path is deliberately **not** in the key. The source is mounted at
a fixed `/src/jws`, so one venv serves every branch whose dependency
declaration is identical — which is most of them.

**openjiuwen is not in the venv key.** It is reconciled per run instead,
against a stamp file in the volume. Putting it in the key would mean a full
~900-package rebuild every time you switch agent-core branch; reconciling means
reinstalling one 6 MB wheel, which takes seconds.

Reuse is therefore never *silent*. The stamp is compared on every run before
any test is collected, and a mismatch forces the reinstall. A volume populated
for "custom jiuwenswarm + stock openjiuwen" cannot be used for "custom both"
without the swap actually happening.

The identity is the commit **plus a hash of uncommitted changes**:

```
local:<ac_head[0:12]>:<sha256(git diff HEAD + untracked)[0:12]>
```

The version number cannot be used. openjiuwen is `0.1.17` both on upstream
`develop` and on our integration branch, so a version comparison would see two
different trees as identical — exactly the invisible-staleness failure this is
meant to prevent. The dirty-tree hash matters because openjiuwen is installed
as a **built wheel**, so uncommitted edits genuinely change the installed bytes.

The pip and npm caches share a single `jws-cache` volume. They are pure
caches — wrong contents cost time, never correctness — so they are not keyed.

### Concurrency

Provisioning is serialised on a `flock`. Two runs with *different* agent-core
trees against the *same* venv volume would otherwise reinstall openjiuwen over
each other; they are correct but will thrash. Use `--venv-tag` to give a run a
private volume when running such combinations in parallel.

## Matching CI

CI runs Python 3.11.5 / pytest 9.0.3 / pluggy 1.6.0; host venvs have Python
3.12 / pytest 9.1.1. The image defaults to **Python 3.11** (`--python` to
change it) and `--ci-pins` pins pytest and pluggy to CI's versions.

This gap has bitten before: pytest attaches `caplog` to non-propagating loggers
only from 9.1, and this project's `setup_logger()` sets `propagate=False`, so a
log assertion can pass locally and see nothing on CI. `--ci-pins` reproduces
that locally.

## What it isolates

- `~/.jiuwenswarm` — not mounted; the module-scope template migration cannot
  find it. This is the point of the exercise.
- `$HOME` generally — no `~/.gitconfig`, no `~/.claude`, no `~/.netrc`, no
  ambient git identity.
- Installed Python and system packages — the venv volume and the image, never
  the host interpreter.
- The interpreter version, independently of what the host happens to have.

## What it does **not** isolate

- **The worktree.** It is bind-mounted read-write on purpose, so an editable
  install works. Tests that write into the tree still write into the real tree,
  and the default `pytest.ini` `addopts` write `htmlcov/`, `coverage.xml` and
  `.coverage` there.
- **The network.** On by default, because a cold venv build needs PyPI and
  gitcode, and because switching it off changes which branch some tests take.
  Use `--no-network` for a run that must not reach out.
- **The main repo's `.git`.** Mounted read-only so git resolves inside a linked
  worktree. Read-only protects the shared index, but it also means tests that
  try to *write* git state will fail differently than on the host.
- **The kernel.** Containers share it; this is not a VM.
- **Anything the host runs concurrently** — CPU and I/O contention still apply,
  so timing-sensitive tests are no more reliable than on the host.
