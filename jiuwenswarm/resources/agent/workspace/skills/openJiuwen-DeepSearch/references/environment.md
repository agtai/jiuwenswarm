# Environment and configuration

Read for first setup, a missing environment, or a configuration error. Run from
the absolute skill directory. Reuse an existing working environment.

```text
uv venv --python 3.11
uv pip install openjiuwen-deepsearch==0.1.8 python-dotenv pypandoc markdown markdown_mermaid_cli -i https://pypi.tuna.tsinghua.edu.cn/simple --prerelease=allow
```

If `uv` is missing, `pip install uv` is the documented prerequisite. Install
within the existing task/host authority; do not change account, Provider or
security settings as an installation workaround.

The user creates/edits `.env` locally from `.env.example`. PowerShell:
`Copy-Item .env.example .env`; Unix: `cp .env.example .env`. Preserve any existing
file. The required configuration names are:

- `LLM_MODEL_NAME`, `LLM_MODEL_TYPE`, `LLM_BASE_URL`, `LLM_API_KEY`
- `WEB_SEARCH_ENGINE_NAME`, `WEB_SEARCH_API_KEY`, `WEB_SEARCH_URL`

Check only presence, nonempty values and absence of example placeholders; do not
print the values. If missing/invalid, state which configuration names need local
attention and the `.env` path. Do not request API keys in the conversation or
write them on the user's behalf. Reuse valid existing configuration without
asking the user to set it up again.

Optional settings: `MAX_WEB_SEARCH_RESULTS` defaults to `5`;
`EXECUTION_METHOD` defaults to `parallel` and also supports `dependency_driving`.
Changing these is not required for an ordinary run.

Logs are under `output/logs/`; exported research artifacts are under
`output/reports/`. Keep logs private and quote only necessary sanitized errors.
