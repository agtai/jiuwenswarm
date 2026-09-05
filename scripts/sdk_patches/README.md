# OpenAI Responses SDK dependency

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

Build after installing the project's ordinary dependencies (Python + setuptools
and Git required; the command fetches only the pinned public SDK source):

```powershell
.\.venv\Scripts\python.exe scripts/build_openai_agent_sdk.py --source-dir .codex_tmp/openai-sdk-build --wheel-dir .codex_tmp/openai-sdk-wheels
uv pip install --python .venv/Scripts/python.exe --no-deps '.codex_tmp/openai-sdk-wheels/openjiuwen-0.1.16+jiuwenswarm.responses2-py3-none-any.whl'
```

Use a new empty source directory for each build. Reinstall this wheel after a
dependency sync that replaces it. The Responses adapter checks the dependency
version before creating a GPT-5.6 client and gives this installation route if it
is missing. Other configured providers keep their existing path.

Regression ownership: `tests/unit_tests/common/test_openai_agentmodel_compatibility.py`
covers actual SDK ReAct invoke/stream, tool execution and continuation, message
serialization, isolation, incomplete responses, and stream event integrity.
Keep private API keys in environment/private configuration, never here.
