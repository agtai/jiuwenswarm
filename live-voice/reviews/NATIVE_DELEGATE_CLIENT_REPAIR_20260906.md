# Native delegate client contract repair

Baseline: `e825327a17ea34c0ef33bf0fefbfa2826986717f`. User authorized repair
after diagnosis of Session `web_1a0775e5f48_ad181b23eb48`. Existing controlled
local Demo deployment authority applies. Preserve model/project configuration,
Task state and files; no remote update or broad performance work.

## Root cause and owned scope

At 17:38:47 the Agent completed normally, but Registry's `prepared` result was
rejected by GatewayNativeInteractionRuntimeClient, which still required
`completed`. The resulting fatal media close produced a generic input-consumer
failure. UI classified it as activation because no audio response was active.
Separate Provider/Engine and Runtime/Agent checks and a fake Gateway client missed
the actual serialized return boundary. Private logs and the isolated actual
validator reproduction are in `logs/native-incident-173847/`.

Tier 3: synchronize the existing strict Native delegate result protocol with the
accepted two-phase preparation and ordered SPEAK design. Successful results must
be `prepared`; obsolete/arbitrary status and malformed/foreign output still fail
closed. No early response allocation, fake ACK or extra Agent/Task execution.
Own the Gateway client and its integration tests through actual Registry results
to the media consumer. Preserve failure/interrupted Task settlement variants.

Tier 2: publish exact current Native foreground failure before fatal media close,
retain the first authoritative terminal reason across secondary P1 detach, and
classify an admitted processing turn as response generation. Own Gateway failure
notification and integrated Web diagnostic projection; reuse existing contracts.
Stale/foreign activation or turn must not alter current display or protected state.

Acceptance: reproduce before fixing; complete actual client module, affected
Gateway/Registry integration and mounted UI checks, typecheck/build, one independent
scoped review, and real return-path evidence. Applicable TESTING.md dimensions
P/N/B/S/T/C/R/I/F/K/X apply to these surfaces. Physical headset acceptance and the
five documented adjacent baseline failures remain separate. Deployment requires a
clean commit, matching served assets/readiness and unchanged Task/project data.

## Results

Implemented strict `prepared` acceptance without accepting the obsolete `completed`
variant. A delayed proposal result revalidates its activation capability; a closed
media session emits no Provider result. One bounded terminal notification lives on
the existing authenticated activation's sequence fence, so media cleanup destroys
audio queues without destroying the first failure reason. Existing forwarded-request,
sequence, expiry and replacement checks remain in front of consumption.

The panel retains exact failed Native state through P1 detach and a cancelled
notification-poll continuation. It classifies a processing turn as response generation.
Independent review found a reachable Task-to-Native handoff race: Native was already
playing while Task settlement kept polling open, allowing the precise terminal to
arrive before media cleanup overwrote it. A shared exact-activation terminal check
now protects cleanup, failed-status and playback-catch exits. No polling policy,
timeout, model, prompt classifier or business phrase was added or changed.

### Verification

Private outputs are under `logs/native-incident-173847/`. Tests used Python's existing
venv, `PYTHONUTF8=1`, an isolated `JIUWENSWARM_DATA_DIR`, `-o addopts=''` and separate
`--basetemp` directories. Frontend commands ran in its existing package.

- Red: actual Registry -> AgentWebSocketServer wire encoder -> client parser/validator
  failed with `NATIVE_RUNTIME_RESPONSE_INVALID` (`red-registry.txt`). Prepared/obsolete
  status validation, post-close terminal delivery, delayed activation replacement,
  mounted failure ordering and the Task-to-Native handoff each reproduced before its
  repair (`red-client.txt`, `red-fatal2.txt`, `red-stale-client.txt`, `red-mounted.txt`,
  `red-mounted-handoff.txt`). Earlier harness construction failures are retained too.
- `pytest tests/unit_tests/gateway/test_native_interaction_runtime_client.py
  tests/unit_tests/gateway/test_dedicated_media_registration.py`: **161 passed**.
- Registry module with `-k '(native or p3_status or task_notification) and not
  native_available_result_uses_toolless_agent_delegate and not
  native_background_delegate_clarifies_or_rejects_without_task_effect'`:
  **31 passed**, 204 deselected. Integration uses actual Registry, server dispatcher,
  wire encoder/decoder, client and media consumer; the deterministic Agent/Provider
  endpoints are explicitly fixtures. Replay causes one Agent execution, and wrong
  call/interaction/generation or closed media causes zero Provider delivery.
- `node --test --test-name-pattern='mounted Native|mounted.*(Task notification|
  terminal-response|reconnect preserves|stale TTS)'` on the mounted panel file:
  **15 passed**, including **9 Native lifecycle scenarios**. Invalid/late identities
  cannot produce Agent/Task writes, audio receipts or presentation ACKs. Ordinary
  already-playing failure and Task-to-Native handoff use actual mounted audio owners.
- Panel unit file with `--test-skip-pattern='actual Live Voice product entry selects'`:
  **68 passed**. `npx tsc --noEmit`: passed. `npm run build:live-voice -- --outDir`
  with the existing runtime flags and an isolated output directory: passed
  (`production-build.txt`, existing bundle-size warnings only). Controlled deployment
  repeats the build from clean source.
- Read-only independent module review and affected handoff re-review: no remaining
  blocking findings. `git diff --check`: passed.

The scoped matrix covers P/K/X through strict real serialization and delivery;
N/B/I through closed fields, bounds, capability, call/generation and notification
ownership; S/T/C/R through closure, replacement, queue saturation, first-reason
retention, forwarding/replay and mounted ordering; F through fatal cleanup and
existing disabled-provider/feature-off cases. No new durability or physical-device
contract is claimed.

### Configured real return path

`real_return_probe.py` created a disposable project/runtime and used actual production
P3 authority/semantics, AgentManager and product Registry. The configured Agent
successfully invoked `read_file` on its project material, returned 328 characters,
and the real server encoder, client decoder/validator and media consumer delivered
one exact function output with `status=prepared`. Delegate-through-consumer time was
25.328 seconds; exact request replay returned the same result, with zero background
Tasks and unchanged project files. Evidence: `real-return-183436/result.json` and
`real-return-probe2.txt`. Input Provider events and the outgoing Provider recorder
are synthetic; network transport, Realtime audio and human hearing are not claimed
by this probe. This closes the changed return seam with real Agent output rather
than crediting separate disconnected Provider and Agent probes as an end-to-end run.

### Exclusions and deployment

The previous lifecycle packet's five proven baseline exclusions remain. The additional
adjacent Cascade test `mounted TTS failure and ACK transport loss keep text visible,
replay one ACK identity, and resume one capture` failed on current source and with
the exact baseline `e825327a` panel injected through an esbuild test-only override,
with the same missing text-ACK assertion and request sequence. This is routed to
the Cascade presentation owner, not changed in this Native return-contract repair.
Evidence: `mounted-affected.txt`, `baseline-mounted-tts.txt`. No full-suite pass or
physical headset/business-journey acceptance is claimed.

Use the existing controlled launcher with the original `formal-web-validation`,
`openai-realtime-native`, `gpt-realtime-2`, generation interruption and verified-headset
profile. Private before/after state fingerprints, deployment log and runtime contract
own the actual deployed source/readiness/bundle result. Keep the user's project/model
configuration and all Task/project data; no remote-ref update is authorized.
