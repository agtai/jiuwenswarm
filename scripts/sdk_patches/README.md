# OpenAI Responses SDK dependency

This branch supports API-key authentication for `gpt-5.6` and `gpt-5.6-sol`
at `https://api.openai.com/v1`. Keep the configured provider as `OpenAI`;
the shared Agent model builder and Web model validation select the Responses
adapter automatically. Other model names, providers and endpoints retain their
existing clients. OpenAI account/OAuth and Live Voice are outside this change.

The upstream SDK pinned by this branch's `pyproject.toml` and `uv.lock` is
`691347b97ef5089a0b0caf7861c98cb9ad35aa2b` (`0.1.17`). It carries
`AssistantMessage.metadata`, but stream aggregation and ReAct message copies
still share nested metadata and ToolCall objects with saved history. Responses
reasoning/tool continuation needs independent snapshots in the same Agent
context. This generic fix deep-copies those values; it does not rewrite answers,
tool arguments, prompts, or reasoning content.

`openjiuwen-responses-metadata.patch` is the complete source delta against that
exact upstream commit, including a local package version for deployment identity.
No runtime monkey patch or site-packages edit is used. Remove this carry when an
upstream SDK with the equivalent fix is verified, and update the adapter's SDK
requirement together with its Agent/context regression tests.

Build after installing the project's ordinary dependencies (Python + setuptools
and Git required; the command fetches only the pinned public SDK source):

```powershell
.\.venv\Scripts\python.exe scripts/build_openai_agent_sdk.py --source-dir .codex_tmp/openai-sdk-build --wheel-dir .codex_tmp/openai-sdk-wheels
uv pip install --python .venv/Scripts/python.exe --no-deps '.codex_tmp/openai-sdk-wheels/openjiuwen-0.1.17+jiuwenswarm.responses1-py3-none-any.whl'
```

Use a new empty source directory for each build. The source debug launcher
preserves this exact installed SDK during its dependency sync. A manual `uv sync`
can still replace it; reinstall the wheel afterward. The Responses adapter checks the dependency
version before creating a GPT-5.6 client and gives this installation route if it
is missing. Other configured providers keep their existing path.

Regression ownership: `tests/unit_tests/common/test_openai_agentmodel_compatibility.py`
covers actual SDK ReAct invoke/stream, tool execution and continuation, message
serialization, isolation, incomplete responses, and stream event integrity.
Keep private API keys in environment/private configuration, never here.

The adapter sends stateless `store=false` requests, retains encrypted reasoning
as opaque message metadata, and releases tool calls only after validating the
completed response. Existing token limits and JSON/schema options are translated
to Responses fields; unsupported sampling parameters are omitted when reasoning
is enabled. No new output budget or model configuration is imposed.

This is a standalone extraction of the GPT changes from `91199de78` and
`a424f9395`, based on JiuwenSwarm `develop` commit `90bd1db30`. The SDK patch is
rebased to the dependency already pinned by that baseline; the old
`0.1.16+jiuwenswarm.responses2` wheel is not compatible with this branch.
Historical provider/deployment evidence from the source branch does not validate
this new SDK baseline. Local HTTP fixtures and real SDK ReAct tests establish
request/continuation compatibility, not a new live-provider deployment claim.

Extraction verification on 2026-09-06 used Python 3.12.9 and the wheel built by
the script above, isolated from the existing development environment. The
following focused and affected suites passed **236 tests**, with **5 POSIX-only
skips on Windows**:

```powershell
python -m pytest tests/unit_tests/common/test_openai_agentmodel_compatibility.py tests/unit_tests/gateway/test_app_web_handlers.py tests/unit_tests/test_debug_launcher.py tests/unit_tests/agentserver/test_image_modality_warmup.py tests/unit_tests/agentserver/test_deep_adapter_model_resolve.py tests/unit_tests/common/test_model_config_validation.py --no-cov -q
```

The baseline migration also verifies UI reasoning high/on/off, explicit and
legacy reasoning overrides, SDK-internal context metadata exclusion, and
unchanged non-API-key routing. The regression cases for internal context fields
and authentication routing failed before those migration fixes and passed after.
