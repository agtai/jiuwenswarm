# JiuwenSwarm current testing and verification guide

This file is the stable repository-level testing entrypoint. Historical test
counts, coverage percentages and CI designs are available from Git history; they
are not current quality evidence.

## Test authority and discovery

Use the checked-out source, [`pytest.ini`](pytest.ini),
[`pyproject.toml`](pyproject.toml), [`tests/README.md`](tests/README.md) and the
actual `tests/` tree as the discovery authority. Do not infer current coverage,
pass counts or workflow availability from a dated review.

Install the test dependencies:

```bash
pip install -e ".[test]"
```

Common Python entrypoints:

```bash
# Complete discovered suite
pytest

# One directory or file
pytest tests/unit_tests/common/
pytest tests/unit_tests/common/test_model_config_validation.py

# One exact test
pytest path/to/test_file.py::TestClass::test_case

# Coverage when it is useful for discovery, not as closure by itself
pytest --cov=jiuwenswarm --cov-report=term-missing
```

Frontend packages own their commands in the applicable `package.json`. Run the
focused Node/TypeScript test files first, then the affected package test/build/
typecheck commands required by the changed surface. A historical test count is
never a substitute for command output from the current worktree.

## General verification rules

- Start with the smallest command that proves the changed behaviour, then run
  affected regressions and broader checks in proportion to risk.
- Positive business scenarios must succeed. Negative scenarios must reject,
  fail closed or produce the explicitly contracted safe no-op.
- Any path that can mutate Agent, Tool, Task, audio/history authority, protected
  state or another scope must assert every forbidden side effect as zero.
- Test count and line coverage help discover gaps; neither proves semantic
  closure.
- Fake, mock and deterministic corpus evidence cannot replace a real boundary
  when that boundary is part of the changed contract or its acceptance.
  Physical Provider, browser/device and human-perception journeys are normally
  candidate-level evidence; require one for a module batch only when that batch
  claims behaviour at the actual physical or Provider boundary.
- Record the exact tested source and relevant private-environment labels without
  credentials. A later source or behavioural-input change invalidates only the
  affected evidence and requires affected reruns.
- An unexplained required failure or flaky result leaves the affected scope
  `PARTIAL` or `BLOCKED`.

## Documentation-only verification

For documentation, routing and mechanical deletion batches:

```bash
git diff --check
```

Also resolve every changed local Markdown link and confirm renamed/deleted files
have no surviving inbound route. Documentation checks do not establish product
behaviour or acceptance.
