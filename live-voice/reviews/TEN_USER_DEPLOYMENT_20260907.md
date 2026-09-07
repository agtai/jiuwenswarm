# Ten-user Native Live Voice deployment

## Authorized boundary

The user requested deployment of `hx/0812_live_voice_w3` on `164.30.6.242` for
up to ten browser testers. Agent model configuration must start empty; the
development `deepseek-v4-flash` configuration must not be copied. Native Realtime
must use `gpt-realtime-2` and the development Speech API credential through a
private channel. The available encrypted sudo credential authorizes the required
server setup without repeated password entry. No remote Git push is authorized.

This packet owns the Linux/container launcher, immutable build, per-tester
configuration and project bootstrap, HTTPS/WSS authentication and isolation,
deployment checks and operating instructions. It is Tier 3 at the deployment,
security and recovery boundary; existing product semantics remain unchanged.
The existing co-scribe service, data and Tailscale route must remain available.

## Intended behavior and acceptance

- Ten separately authenticated browser entries use ten isolated data/project/
  process/network contexts with the same source and frontend build.
- First use shows empty Agent model settings and the existing configuration UI.
  Missing Agent credentials must fail clearly without falling back to the
  development Agent model. Real Agent/tool acceptance requires a user-configured
  model; standalone Speech checks cannot claim that complete boundary.
- Native model is explicitly `gpt-realtime-2`, independent of newer source
  defaults. Provider keys remain server-side and outside source/image layers.
- HTTPS is trusted; `/ws` returns real readiness and dedicated media routes
  preserve the existing authenticated protocol. Each tester can only enter their
  assigned instance. Missing/wrong credentials and wrong Origin fail closed.
- Build, configuration, real Speech connectivity, 1/3/10 connection tests,
  cross-instance isolation, process restart/data retention and prior-service
  preservation have recorded evidence before handoff. Physical microphone/Agent/
  speaker and model-dependent concurrency remain explicit if not exercised.
- Restart and deployment procedures preserve already-initialized user models,
  projects and task data. Rollback identifies image/source and retains data.

## Dependencies and exclusions

Use the [server assessment](../evidence/TEN_USER_SERVER_ASSESSMENT_20260907.md),
[runtime contract](../runbooks/E2E_RUNBOOK.md#75-当前受控-live-voice-启动与预演),
root [TESTING](../../TESTING.md), and the owning source for each touched surface.
Provider account quota and public cloud ingress may impose external limits.
The ten accounts are a controlled test cohort, not a new production tenancy
implementation. No new Agent model default, classifier, task authority,
application protocol, external IM channel or shared project is introduced.

## Execution evidence

Application baseline is `cdd1ca6d9c30b86a76830b2b1ef6835f4bba13c0`. The deployment
module adds no changes to application Agent, voice, Task or protocol semantics.
Its [operating instructions](../../deploy/live_voice/README.md) own setup,
credentials, restart and migration procedures.

Candidate checks on 2026-09-07:

- Frozen Python dependency installation and `npm ci` / `build:live-voice` pass
  inside the image build. Seven focused bootstrap/runtime cases pass: empty Agent model,
  real registered Code/Git project, restart preservation of user configuration
  and files, and zero-write rejection of foreign/unidentified data, expired
  authorization, another instance's hostname and unexpected Agent key input.
- All ten instances are healthy. Each performs a real TTS/STT round trip,
  Gateway receipt/identity checks and `gpt-realtime-2` session creation. These
  checks produce zero Agent/tool business effects and retain no probe audio or
  transcript. User Agent credentials remain absent.
- Public HTTPS and authenticated WSS pass at 1/3/10 concurrent connections,
  including real readiness ACK, isolated project IDs, empty model responses and
  ping/pong. Unauthenticated UI/control/media paths and cross-account credentials
  return 401; cross-instance Origin upgrades return 403.
- Ten separate headless Chrome contexts load the real UI concurrently, use
  trusted secure contexts and display empty model fields with incomplete save
  disabled and zero JavaScript page errors. The guide can already be dismissed,
  so the check enters the existing configuration UI directly when necessary.
- Container-to-container TCP is rejected, other instance volumes and the Docker
  socket are absent, and each service has a private bridge, loopback host port,
  non-root UID, dropped capabilities and bounded CPU/memory/PIDs.
- A forced startup-supervisor failure in lv10 triggers an automatic restart and
  healthy recovery, preserving all six hashed model/config/registration/project
  files. Local bootstrap tests additionally preserve a deliberately changed
  synthetic user model without inserting one into the deployed environment.
- Trusted HTTPS covers the portal and ten instance names. Certificate renewal
  dry run succeeds. Systemd startup is enabled. The existing co-scribe service
  remains HTTP 200 with unchanged PID 13854 and restart count zero.

The applicable D-032 dimensions are P (first use/connectivity), N/B (missing
model and invalid auth), S/R (durable initialization and fault restart), I
(account/project/network separation), C (1/3/10 sockets), T (expiring runtime
authorization and bounded retries), F (startup failure stays unavailable), K
(existing service preserved), and X (real public ingress and Speech Provider).
Agent task scheduling, interruption, playback and model-dependent concurrency
are unchanged and excluded from this deployment's completion claim.

## Review and limitations

A cold complete deployment diff review was performed against the baseline.
Findings repaired in this boundary: the SDK's relative logging directory must
be writable in `/data`; internal Gateway/Agent traffic requires loopback Origin
in addition to the assigned public hostname; seeded Code projects require the
existing Git snapshot initialization; health probes should consume HTTP bodies.

No callable independent code-review tool was available in this session. The
unavailable-tool substitute under root TESTING is the recorded cold complete
diff review plus actual host, Provider, security and recovery checks. This does
not claim independent reviewer evidence or full product-candidate acceptance.

An existing Web UI tunnel can forward a 403 response header without its complete
error body. The public negative probe verifies the real HTTP rejection status;
successful WSS readiness is separately exercised. This adjacent proxy diagnostic
issue does not admit a rejected handshake and is not silently counted as a
successful voice connection.

Agent model fields must stay empty until testers supply their own settings. The
mandatory first-model form prevents saving incomplete settings. A complete real
microphone → Native → configured Agent/tools → artifact → speaker journey, ten
concurrent model workloads, and subjective latency/audio quality remain untested.
This controlled cohort does not establish production tenancy or adversarial
isolation of the shared Speech key from code executed by authorized testers.

The final clean deployment source, immutable image and exact served assets are
recorded in the closing evidence after rebuilding from the deployment commit.
