# OpenAI AgentModel integration — 2026-09-05

## Authorized boundary

The user requests adding the exact `gpt-5.6` model with the provided private
API-key file, diagnosing OpenAI format failures, and selecting it as the local
JiuwenSwarm AgentModel. Preserve the existing model entry, Speech configuration,
Task/result/notification state and user preferences. Credentials remain in the
machine-private configuration, never in Git or diagnostic output.

Initial scope was a Tier-2 parameter repair. Real tool continuation then failed:
the official API requires Responses for GPT-5.6 function tools with reasoning.
The authorized format integration is therefore re-scoped to **Tier 3**, owning
Responses request/event mapping and opaque reasoning continuation through the SDK
Agent context. The parameter-only candidate is not accepted or deployed.

The configured single-Agent builders,
formal foreground clone, semantic calls and background Code Agent use the same
request compatibility boundary. No answer rewriting, new output limit, semantic
classifier, Task authority, retry policy or dependency monkey-patch is included.
Other model families/endpoints retain their existing request behavior. Broader
team/evolution/provider acceptance and performance tuning are not claimed.

Acceptance: actual OpenAI invoke/stream, JSON and tool-result continuation;
the real configured Agent reads and writes only a disposable test fixture;
negative configuration has no HTTP/tool effects; same-model clones, cancellation,
request/config isolation and existing providers retain their behavior. Verify the
private default and controlled deployment without consuming rehearsal notices.
Complete scoped checks and an independent adapter review before closure.

## Reproduced cause

Baseline `77008a184`: the official API accepts a minimal `gpt-5.6` request and
returns `gpt-5.6-sol`. The same request with JiuwenSwarm/SDK's `temperature=0.95`
returns HTTP 400 `unsupported_value`; Live Voice's `temperature=0` also returns
400. The API reports that only default temperature 1 is supported. `max_tokens`
returns HTTP 400 `unsupported_parameter`, requiring `max_completion_tokens`.
JSON mode with compatible sampling succeeds. These are request-parameter
incompatibilities, not evidence that Chat Completions or the response parser is
entirely unsupported.

Sources: [model/alias](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
[migration guidance](https://developers.openai.com/api/docs/guides/upgrading-to-gpt-5p6-sol).
Private bounded probes are under ignored `logs/openai-agentmodel-20260905/`.

## Implementation and verification

The complete fix uses `OpenAIResponsesClient`, registered through the existing
SDK client registry, for the official endpoint and verified `gpt-5.6` /
`gpt-5.6-sol` names. Stored provider configuration remains `OpenAI`. The common
single-Agent builder and Web model-validation handler choose the same adapter;
formal model clones retain that choice. Existing other providers/endpoints keep
their original clients. Reasoning remains enabled; unsupported sampling fields
are omitted, existing token budgets are translated to `max_output_tokens`, and
JSON/schema options map to Responses `text.format`. No new output budget is added.

Stateless `store=false` requests carry ordered Provider output items, including
encrypted reasoning, in AssistantMessage metadata. This metadata stays outside
visible text/tool arguments. Model/endpoint/message binding is checked before
replay. Tools are emitted once from the validated completed response, never from
intermediate item events. Incomplete tools, duplicate call identities, missing
terminal events and inconsistent text fail before tool execution. Cancellation
closes the response stream while preserving the shared HTTP client.

Real full-Agent testing exposed an additional SDK defect after the initial
metadata repair: execution rails stripped `call_goal` and reserialized arguments
on ToolCall objects shared with saved history. The final SDK repair deep-copies
metadata during stream aggregation/message copies and ToolCalls when saving the
model message. Execution rails retain their existing semantics; model history
keeps the original Provider call. The regression failed in both invoke and stream
before this last repair, then passed on the final installed SDK.

The complete dependency delta is tracked in
[the SDK patch/install guide](../../scripts/sdk_patches/README.md), against
upstream `94e10cb6102c36fe78a64547957c0def97299273`. The reproducible build creates
`openjiuwen==0.1.16+jiuwenswarm.responses2`; the adapter rejects an unrepaired SDK
with the installation route. No in-place site-packages edit or runtime monkey
patch is used. Reinstall the wheel if a dependency sync replaces it.

### Evidence on the final implementation

Baseline: `77008a184ba0c802919bc4d522b67077428f31c8`; scoped source and SDK patch
are the change containing this report. Local raw outputs and source hashes are
under ignored `logs/openai-agentmodel-20260905/`, without committed credentials.

- **42 focused tests passed:** actual SDK HTTP serialization and ReAct execution,
  invoke/stream, JSON, multiple tools, execution-rail argument changes, ordered
  reasoning replay, serialized messages, wrong bindings, unsupported SDK,
  cancellation/shared-client lifetime, protected input, optional tool arguments,
  refusal/text ordering, duplicated/reordered/missing item events and malformed
  terminal paths. Includes the real Web validation handler with simulated HTTP.
- **91 affected regressions passed:** image-modality warmup, semantic reasoning
  options and task semantics. An earlier run failed at temporary-directory setup
  (`pytest-of-XGG` permission); rerun used a new workspace `--basetemp` and passed.
- **Real official API:** JSON, cloned-model streaming, function call/result
  continuation. Chat-with-reasoning tool rejection is preserved as failed evidence.
- **Real configured Agent seams:** isolated synthetic inventory project; formal
  foreground read returned the correct total, then the background Code Agent
  read the input and wrote `result.md` with both source counts and their total.
  Original input remained unchanged. Final run `real-agent-205537` measured
  6.766 s foreground and 12.719 s background execution; these are single samples,
  not a performance comparison or SLO claim.
- **Independent review:** initial findings repaired; 28 surrounding tests and
  then 7 newly affected scenarios passed independently. The reviewer also used
  actual `SessionModelContext.save_state`, the SDK pickle serializer, and a fresh
  context's `load_state`; reasoning/function-call replay survived unchanged.
  No unresolved blocker was reported for this bounded integration.

Focused command (isolated config/data environment):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/common/test_openai_agentmodel_compatibility.py tests/unit_tests/test_app_web_handlers.py -k 'openai_agentmodel or actual_compatible_sdk' --no-cov -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/agentserver/test_image_modality_warmup.py tests/unit_tests/common/test_semantic_reasoning_options.py tests/unit_tests/live_voice/test_task_semantics.py --basetemp logs/openai-agentmodel-20260905/regression-temp-1 --no-cov -q --tb=short
```

P/N/B/S/T/C/R/I/F/K/X applicability: positive real file-tool flow; rejection and
zero tool effects; parameter/content limits and schemas; response terminal/close
state; event order; concurrent request options; cancel/partial-stream and persisted
context recovery; bound replay isolation; unpatched-SDK/old-provider paths;
existing consumer regressions; and actual API/Agent seams are covered above.
This change does not own Task scheduling/authorization, background adjustment,
notification recovery, browser playback or service crash recovery.

### Configuration and scope

The authorized local default entry is `gpt-5.6`, provider `OpenAI`, official
`https://api.openai.com/v1`, reasoning effort `medium`. The original DeepSeek
entry is retained. Only the dedicated `JIUWENSWARM_OPENAI_AGENT_API_KEY` environment
reference is added; Speech settings and other configuration sections remain
unchanged, with a private pre-change backup. The change script checked zero
nonterminal tasks and retained all 66 existing task rows. Runtime deployment
identity comes from the controlled launcher manifest, not this source document.

This is API-key authentication, not OpenAI account/OAuth authentication. Broader
team/evolution constructors, all Chat-specific options, and physical microphone /
speaker or full A/B/A2 rehearsal acceptance are not claimed. Unknown native server
fields retain `extra_body` support, but Agent-owned input/tools cannot be replaced.
