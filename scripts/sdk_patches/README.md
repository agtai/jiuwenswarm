# AgentCore source dependency

The accepted installation policy is source-first for subsequent development and
deployment. `agentcore-source.json` pins the upstream commit, reviewed Git content
tree, version and ordered patches. `.deps/agent-core` is an independent local Git
checkout; `pyproject.toml` and `uv.lock` use that editable source. Do not replace it
with an AgentCore package downloaded from a package index or a detached wheel.

The installed upstream SDK at `94e10cb6102c36fe78a64547957c0def97299273`
discarded `AssistantMessage.metadata` during stream aggregation and two ReAct
message copies. Responses reasoning/tool continuation needs that metadata in
the same Agent context. Execution rails also mutated ToolCall objects shared
with saved history. This generic fix snapshots metadata and tool calls by deep copy; it
does not rewrite answers, tool arguments, prompts, or reasoning content.

`openjiuwen-responses-metadata.patch` is the complete source delta against that
exact upstream commit, including a local package version for deployment identity.
No runtime monkey patch or site-packages edit is used. Remove this carry when an
upstream SDK with the equivalent fix is verified, and update the adapter's SDK
requirement together with its Agent/context regression tests.

Prepare source before the initial dependency sync (Python 3.11+ and Git required):

```powershell
python scripts/install_agentcore_source.py --prepare-only
uv sync --frozen
.\.venv\Scripts\python.exe scripts/install_agentcore_source.py --check
```

For an existing environment, run its Python with
`scripts/install_agentcore_source.py`; this verifies the source, explicitly
uninstalls the existing AgentCore distribution, then installs directly with
`uv pip install --no-deps --editable`. The build backend may internally produce
installation metadata/a wheel; the retained source checkout is the dependency
origin. `--repository <Git mirror>` can obtain the same pinned base offline.

Preparation refuses to overwrite an existing checkout. On a partial failure it
retains the checkout for inspection. Preserve `.deps/agent-core` and its local
commits when cleaning build artifacts. Source changes require their own review,
tests, local commit and an updated manifest/patch set in JiuwenSwarm. The content
tree permits reconstruction without depending on a local commit timestamp.

The debug launcher requires the project environment, verifies clean source before
build/sync, uses the frozen lock, and verifies editable installation origin before
starting a service. Ordinary `uv sync` now uses the same source; it cannot silently
restore an unpatched VCS package. The Responses adapter's version check remains a
compatibility check, separate from deployment provenance. Other configured
providers keep their existing path.

Regression ownership: `tests/unit_tests/common/test_openai_agentmodel_compatibility.py`
covers actual SDK ReAct invoke/stream, tool execution and continuation, message
serialization, isolation, incomplete responses, and stream event integrity.
Keep private API keys in environment/private configuration, never here.
