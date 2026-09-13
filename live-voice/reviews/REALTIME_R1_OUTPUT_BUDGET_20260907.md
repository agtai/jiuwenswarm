# R1 Native output budget

Scope: [accepted repair packet](REALTIME_ACCEPTANCE_REPAIRS_20260907.md), R1.
Baseline `af6a5bbb0cadd0e260e12961ee33f737db489d31`; Tier 2 configuration and
Native output validation. Removes three 1024 response overrides in favor of the
same validated value used at session setup. Default `inf` uses the selected
model's maximum. `LIVE_VOICE_NATIVE_MAX_OUTPUT_TOKENS` and the controlled
launcher's `-NativeMaxOutputTokens` accept `inf` or canonical integers 1–4096.
Cascade does not read the Native setting; no model/provider change is made.

The official [client event definition](https://developers.openai.com/api/reference/resources/realtime/client-events)
allows `inf` for the model maximum; the [selected model page](https://developers.openai.com/api/docs/models/gpt-realtime-2)
currently lists 32,000 maximum output tokens. This is an upper bound, not a quota
that every response must consume. Existing response validation already permits
`inf`; incomplete/error and playback ownership are separate R2/R3 work.

## Verification

Root Python `.venv/Scripts/python.exe`, `PYTHONPATH` set to this worktree,
isolated `JIUWENSWARM_DATA_DIR=logs/r1-test-data`:

`python -m pytest tests/unit_tests/live_voice/test_native_interaction_config.py tests/unit_tests/live_voice/test_native_output_budget.py tests/unit_tests/live_voice/test_native_endpoint_strategy.py tests/unit_tests/live_voice/test_openai_realtime_native_engine.py tests/unit_tests/test_app_web_handlers.py -q -o addopts='' --no-cov -o log_cli=false`

332 passed. Covers session negotiation, direct default inheritance, three
successor paths including numeric override, argument/turn/stale replay regressions,
Web factory propagation, canonical parsing and rejection before transport creation.

Real selected-Provider probe uses the production Session and closed Engine
response validator with a synthetic 299-character Chinese fee/travel explanation.
No Agent/Task operation, browser playback or user Session mutation is involved.
The selected `gpt-realtime-2` returned `completed`, `max_output_tokens=inf`, all
299 transcript characters and the final sentence; 67.5 seconds of PCM, 1,637
output tokens (1,350 audio and 287 text). Private environment bytes were unchanged.
The private probe/result remain in ignored `logs/r1-real-budget*`. An initial
probe harness used a nonexistent event property and was corrected to `to_dict`;
its failure record is retained. This is not a measured browser-continuity claim.

Independent cold review by the project/authority worker found the launcher's
`.NET $` anchor could admit a trailing LF before Python rejected it. Replaced
it with exact `\A...\z` anchors. No other actionable issue was found in the
configuration/factory/session/override boundary; review did not rerun the suite.
PowerShell AST parsing, exact-boundary validation, scoped Markdown link checks
and `git diff --check` passed. Browser continuity and integrated user acceptance
remain outside this R1 evidence.
