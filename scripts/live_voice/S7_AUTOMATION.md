# S7 Alpha automation runner

Execution packet: S7/A2 Shared/X-E2E verification automation,
Tier 3 because it interprets cumulative security, privacy and authority evidence.
Scope is the candidate-bound runner, its tests and frontend matrix discovery.
It also includes the five canonical real-probe entrypoints and their closed
observation contracts. Real Provider/device/deployment execution, S7 entry,
acceptance decisions, production scope and remote updates are excluded.

`s7_alpha_verification.py` prepares and runs the unsigned S7/A2 verification
matrix. It is not the retired evidence Gate, does not sign or score artifacts,
and does not replace S7-03 review or S8 human acceptance.

The runner requires an explicit comparison base, a clean source tree and, for a
candidate result, a configured upstream. Fetch the upstream immediately before
freezing the candidate. A local preparation branch can inspect the plan with
`--allow-no-upstream`:

This implementation was selectively adapted from `d2727f20` onto the final S6
tree. It accepts only comparison base
`2a69c2b87d0ee080a4a30421cbcbcdf93183f340`, preserves the repository pytest
configuration (including `--asyncio-mode=auto`), records the frontend generated-
artifact exclusion/digest state, freezes a bounded content manifest for the
actual ignored production `dist`, and requires the final S6 speech/browser source
and regression inventory before building the matrix. The frontend registry must
cover every tracked `tests/liveVoice*.test.mjs`, the three declared compatibility
tests, and the post-S6 `productP1VoiceRoute.test.mjs` owner.

```powershell
uv run --frozen python scripts/live_voice/s7_alpha_verification.py plan `
  --comparison-base '2a69c2b87d0ee080a4a30421cbcbcdf93183f340' `
  --allow-no-upstream
```

After the preparation code is committed, run the complete automatic matrix from
the candidate worktree. Keep the JSON report outside the source tree:

```powershell
uv run --frozen python scripts/live_voice/s7_alpha_verification.py run `
  --comparison-base '2a69c2b87d0ee080a4a30421cbcbcdf93183f340' `
  --report '<private output directory>\s7-automation.json'
```

The built-in matrix covers the Live Voice backend unit/integration set, the
explicit Live Voice-owned AgentServer/Gateway/channel/Web regressions and the
formal Task Store/Executor seam, every dynamically discovered
frontend `test:live-voice-*` script plus the speech-recognition lifecycle,
TTS-output ownership and chat-store streaming compatibility suites, the
production build, Ruff/compile checks for all changed Python and format checks
for S7-owned Python,
`git diff --check`, Markdown links and source/privacy hygiene. `uv sync
--frozen --check` binds the installed Python environment to `uv.lock`; `uv pip
check` additionally checks package consistency without assuming that the clean
project environment installs the `pip` Python package.
Frontend dependencies come from `package-lock.json` through
`npm ci --ignore-scripts`. Package commands must cover the exact dynamically
discovered set of tracked `tests/liveVoice*.test.mjs` files. A frontend test
command must emit at least one passing TAP test and zero failed TAP tests, and
the production build must report at least one Vite-transformed module and create
a non-empty `index.html` build. The runner records a bounded file count, byte
count, complete path/size/content manifest digest and entrypoint digest; each
backend matrix must report at least one passed pytest case and zero
failures/errors.
Exit zero or an all-skipped suite is insufficient. Pytest keeps
`--asyncio-mode=auto` and ignores `SyntaxWarning` only to cross the locked
third-party `pysbd` invalid-escape incompatibility already recorded by prior
Live Voice review. Changed repository Python receives an explicit Ruff `W605`
invalid-escape check, so this compatibility exception cannot hide the same
defect in candidate source.

The cumulative Ruff check runs without ignores or per-file waivers and requires
its unfiltered JSON diagnostic set to equal the exact 21-item pre-existing S6
fingerprint (path, rule, row, column and message). Any added, removed or moved
diagnostic fails the candidate. The compile check still covers every Python
file changed from the comparison base. The formatter check is intentionally
limited to the S7-owned runner/probes and their tests: rewriting the broad S6
Python set merely to satisfy the current formatter is explicitly outside the
selective-port boundary.

Reports contain only placeholder-safe argv, repository-relative cwd, exit
status, duration, test counts and bounded failure identifiers. Captured output is
bounded to 2 MiB; truncation is explicit, and it invalidates a real-probe
summary. Automatic output is displayed but not persisted. Real-probe output is
neither echoed nor persisted. On timeout or interruption the runner terminates
the spawned process tree. A post-run identity check fails the run if a check
changes HEAD, a dependency input, the upstream relation, tracked/untracked
worktree content or the ignored production build after its digest was frozen.
The build walk rejects links/reparse points and special files and is capped at
512 files, 512 directories, 64 MiB per file and 128 MiB total.

Automatic commands receive a minimal OS/tool environment plus the declared
Live Voice feature flags. They never inherit the Speech API key, P3 bearer or
other unrelated parent variables, so verification cannot accidentally activate
a real Provider and failure output cannot echo inherited credentials. Real
checks use the separate explicit `required_env` boundary below.

## Candidate runtime declaration

A run with real probes requires `--candidate-record` pointing to an external
JSON file with schema `live-voice.s7-candidate-runtime.v1`. It binds the exact
candidate HEAD and comparison-base SHA, the complete feature-flag set and these
sanitized labels: Agent Provider, browser, OS, HTTPS origin, input/output
devices, network profile, official OpenAI Speech origin/models/voice, the
Streaming-to-W2-Batch-to-browser/text fallback, Executor, disposable
project/data fixture and private same-origin HTTPS/WSS topology.
Every recorded flag must equal its process-environment value and the accepted
candidate profile: the formal Integrated Web/P1/P3 and backend/Gateway flags are
`true`, while the superseded frontend Task Demo and Streaming Speech entry flags
remain `unset`. The runner enforces D-078's JiuwenSwarm Agent, official OpenAI
Speech, frozen STT/TTS models, `marin`, Direct Project Executor and private
deployment labels. It also requires an exact Chrome four-part version and
Windows build, hash-derived `device_ref` (or `system_default`), `network_ref`,
`disposable_git_ref:...:no_remote` and `data_ref` labels, plus a
`private_origin_ref:sha256-...` derived from the exact private HTTPS FQDN in
`S7_PRIVATE_ORIGIN`. The origin must be a canonical non-loopback DNS name; the
deployment observer additionally requires every resolved address to be private.
Credentials, host filesystem paths, the private hostname and raw observations
do not belong in this file.

The runner calculates a `sha256:...` digest over this complete sanitized
declaration. It passes the digest to every real child and requires the same
binding in each artifact-backed observation and sanitized result. Candidate
HEAD equality alone is therefore insufficient to mix results from another
browser/device/network/fixture declaration.

## Operator-observed real probes

Real probes are described by a second external JSON file with schema
`live-voice.s7-real-checks.v1`. It provides exactly one check for each of
`speech-media`, `agent-executor`, `benchmark-fault`, `secure-deployment` and
`privacy`. Check ID, entrypoint and required environment are an exact mapping;
an alternative tracked Python file is rejected. Arbitrary binaries, `python
-c`, absolute paths, non-root cwd, positional probe arguments and environment
interpolation into argv are rejected.

Private values stay in the probe process environment. List only their names in
`required_env`; the candidate-owned probe reads them directly. Each real child
receives a minimal OS environment, the exact declared Live Voice feature flags,
those explicitly named variables, and the runner-provided `S7_CANDIDATE_HEAD`,
`S7_RUNTIME_DECLARATION_SHA256` and `S7_CHECK_ID`. The parent environment is not
copied wholesale.

A probe emits one sanitized aggregate line prefixed with
`S7_SANITIZED_RESULT`. The JSON must bind `candidate_head`,
`runtime_declaration_sha256` and `check_id` and may contain `sample_count`,
`failure_count`, `p50_ms`, `p95_ms`, `max_ms`,
`zero_forbidden_effects` and `outcome`. It needs at least one sample, zero
failures, zero forbidden effects and `outcome=PASS`; speech/media and
benchmark/fault also require ordered p50/p95 latency. Valid summaries are marked
`VERIFY`, not `PASS`: they are operator-observed inputs for S7-03 cumulative
review, not self-certifying acceptance.

The canonical entrypoints are now implemented:

| Check | Entrypoint | Exact private inputs | Verification performed |
|---|---|---|---|
| `speech-media` | `s7_probe_speech_media.py` | `S7_SPEECH_MEDIA_OBSERVATION` | Requires 5–20 complete private-route rounds on the official D-078 Provider/models/voice; recomputes end-to-end p50/p95/max and rejects missing ACKs, degradation, receipt gaps, credential hits or forbidden effects. |
| `agent-executor` | `s7_probe_agent_executor.py` | observation plus completion/cancellation fixture roots | Requires formal structured and natural-language facts, then directly verifies two distinct no-remote Git roots: one exact `notes.txt` marker diff for completion and a clean cancellation fixture with zero write. |
| `benchmark-fault` | `s7_probe_benchmark_fault.py` | `S7_BENCHMARK_FAULT_OBSERVATION` | Requires all 13 declared route targets with at least five raw latency samples and the closed 13-case fault/degradation/cancel set; recomputes route p50/p95/max. |
| `secure-deployment` | `s7_probe_secure_deployment.py` | `S7_PRIVATE_ORIGIN` | Actively performs the bounded trusted-TLS HEAD, CORS OPTIONS and dedicated-media WebSocket upgrade observation against the hash-bound private FQDN; loopback, public, mixed-address and rebinding targets fail closed. |
| `privacy` | `s7_probe_privacy.py` | external surface manifest/capture root and the two Gateway-only secret values | Scans all 19 closed Alpha surfaces, bounded to 512 files/128 MiB, for the actual credentials and encoded forms; complete-corpus raw PCM16 and authoritative 48 kHz `pcm_f32le` sentinels, aligned base64 PCM16 960/1920-byte slices and 3840-byte f32le media frames, and the corpus hash; WAVE headers; and persisted audio filenames. |

The three route/task/benchmark observation files use strict versioned schemas,
must be outside the candidate, bind the candidate and runtime-declaration
digest, reject unknown fields, and contain closed facts rather than free text.
The privacy manifest likewise names exactly every closed surface using only
relative files below one external capture root. Private paths and values never
enter argv, reports or source.

These entrypoints do not manufacture the private observations that only the
controlled environment and operator can produce. Artifact-backed checks still
establish `VERIFY`, not semantic proof that an observation was honestly
captured; S7-03 must inspect the exact entrypoint, private-harness invocation and
operator-observed run. Physical microphone, permission, device and heard-audio
facts remain human observations. Missing environment is `BLOCKED`, not a fake
sample or an automation PASS.

The external `real-checks.json` contains names, never values, and must use this
exact mapping:

```json
{
  "schema_version": "live-voice.s7-real-checks.v1",
  "checks": [
    {
      "id": "speech-media",
      "argv": ["<python>", "scripts/live_voice/s7_probe_speech_media.py"],
      "required_env": ["S7_SPEECH_MEDIA_OBSERVATION"]
    },
    {
      "id": "agent-executor",
      "argv": ["<python>", "scripts/live_voice/s7_probe_agent_executor.py"],
      "required_env": [
        "S7_AGENT_EXECUTOR_OBSERVATION",
        "S7_EXECUTOR_COMPLETION_FIXTURE_ROOT",
        "S7_EXECUTOR_CANCELLATION_FIXTURE_ROOT"
      ]
    },
    {
      "id": "benchmark-fault",
      "argv": ["<python>", "scripts/live_voice/s7_probe_benchmark_fault.py"],
      "required_env": ["S7_BENCHMARK_FAULT_OBSERVATION"]
    },
    {
      "id": "secure-deployment",
      "argv": ["<python>", "scripts/live_voice/s7_probe_secure_deployment.py"],
      "required_env": ["S7_PRIVATE_ORIGIN"]
    },
    {
      "id": "privacy",
      "argv": ["<python>", "scripts/live_voice/s7_probe_privacy.py"],
      "required_env": [
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN",
        "LIVE_VOICE_SPEECH_API_KEY",
        "S7_PRIVACY_CAPTURE_ROOT",
        "S7_PRIVACY_SURFACE_MANIFEST"
      ]
    }
  ]
}
```

Observation producers must use the closed source schemas rather than copy a
previous aggregate:

- All manifests contain their exact `schema_version`, `candidate_head`,
  `runtime_declaration_sha256`, `capture_source=controlled_private_route_v1`
  and `capture_complete=true`; unknown or missing fields fail.
- `live-voice.s7-speech-media-observation.v1` contains the frozen Provider
  profile and 5–20 distinct rounds. Each round records its hash-derived ref,
  frame/ACK counts, attach/EOT/timing facts, recognition and synthesis status,
  playout receipt, leak/effect counts and raw STT/TTS/end-to-end latencies.
- `live-voice.s7-agent-executor-observation.v1` contains the formal-route facts
  and separate completed/cancelled Task results. The completed disposable root
  must have exactly one tracked modification: `notes.txt` changes from
  `baseline` to include `alpha-s7-agent-executor-marker`; the cancelled root
  stays clean. Both roots retain their declared HEAD and have zero remotes.
- `live-voice.s7-benchmark-fault-observation.v1` contains the 13 target IDs and
  each target's 5–50 raw millisecond samples plus failure count. Its fault list
  must match the complete closed case/outcome vocabulary in
  `s7_real_probe_support.py`; summaries supplied by the observation are not
  trusted.
- `live-voice.s7-privacy-capture.v1` lists every value in
  `ALPHA_PRIVACY_SURFACES` exactly once, with one or more unique relative files
  below `S7_PRIVACY_CAPTURE_ROOT`. The manifest and root stay outside Git.

```powershell
uv run --frozen python scripts/live_voice/s7_alpha_verification.py run `
  --comparison-base '2a69c2b87d0ee080a4a30421cbcbcdf93183f340' `
  --candidate-record '<private input directory>\candidate-runtime.json' `
  --real-config '<private input directory>\real-checks.json' `
  --require-real `
  --report '<private output directory>\s7-complete.json'
```

Exit code `0` means only `READY_FOR_S7_CUMULATIVE_REVIEW`: all automatic checks
passed, all five bound real summaries reached `VERIFY`, the sanitized runtime
record matched, and upstream was present/current. `1` means a check failed, `2`
means blocked/configuration error, and `3` means a valid but incomplete or
preparation-only run (including `--only`, no real probes, no upstream or a
behind candidate). Physical microphone, permissions, device behavior and heard
playout remain user-observed even after the automation is ready for review.
