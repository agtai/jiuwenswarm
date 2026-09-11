# AgentCore source used by the slimming integration

The Host dependency is the immutable AgentCore commit
`ffeb1abcc5cc0bc72b5c813a3316d4334d39e15f` from
`https://github.com/agtai/agent-core.git`. `pyproject.toml` and `uv.lock` are the
installation authority. This is the audited twelve-commit Live Voice source,
with tree `6f3826983ea8c15eb182ec7761705fd5058c1235`.

For a checkout/environment being prepared to run this source:

```powershell
uv sync --frozen --inexact
```

The debug launcher uses the same command. The fixed lock prevents an accidental
return to floating GitCode develop; `--inexact` keeps unrelated local packages.
The old version-only installation exemption has been removed: both the former
Responses-only build and this source use `0.1.16+jiuwenswarm.responses2`, so that
version cannot prove the source identity. Inspect `openjiuwen.__path__` and the
installed distribution's `direct_url.json` when distinguishing environments.

The source declaration/lock change does not install packages or restart services.
The execution record identifies which SDK environment was actually tested or
adopted. A process already running the older `.deps/agent-core-w3` source is not
claimed to use the new SDK merely because the repository lock changed.

No twelve-patch mirror is kept inside Live Voice. The former Responses patch
builder is historical reconstruction tooling, not the current install path.
AgentCore owns SDK execution settlement, model-call guards and source/output
binding. JiuwenSwarm owns configured facade execution and durable project Tasks;
Live Voice owns speech input, media and presentation adaptation. Enabling new
Goal/Team/Workflow voice operations is outside this behavior-preserving change.
