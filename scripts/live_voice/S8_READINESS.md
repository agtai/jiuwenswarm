# S8 readiness operator assistant

This helper prepares the `S7-04 → S8-01` handoff. It is unsigned, unscored and
not an acceptance authority. A successful automatic preflight means only that
the frozen S7 inputs and current machine declarations are internally consistent.
It never starts S8, fills a human observation, changes a flag or fallback, repairs
source, or produces Alpha PASS.

Authoritative requirements remain
[Alpha acceptance](../../live-voice/validation/ALPHA_ACCEPTANCE.md), the
[Alpha showcase](../../live-voice/demo/ALPHA_SHOWCASE.md) and the
[E2E runbook](../../live-voice/runbooks/E2E_RUNBOOK.md). The preparation audit is
[S8 readiness preparation](../../live-voice/S8_READINESS_PREPARATION_2026-08-13.md).

## Inputs and privacy boundary

Keep every input and generated JSON file outside the source worktree in an
operator-owned private directory. The helper accepts private paths through
arguments or environment variables. Helper-generated outputs contain only exact Git identities,
SHA-256 references, booleans, status/reason enums, ports and sanitized IDs.
It never writes a secret, hostname, raw audio, browser profile or filesystem
path into a report.

The product-trace input is the exception to the hashed-ID output rule: it may
contain canonical Task/attempt/response/round/work IDs exported from the running
product, so it is private input and must never enter Git. `capture-trace` hashes
those IDs into a candidate/runtime/session-bound manifest. Do not hand-author a
product trace or an identity digest. If the reviewed product/observability path
cannot export the required source records, leave the affected observations
`BLOCKED` and return the missing capability to S7.

The helper consumes these S7-owned inputs:

- `live-voice.s7-automation-report.v1`, produced by the candidate's S7 runner;
- `live-voice.s7-a3-handoff.v1`, frozen by the S7 Integration Owner only after
  S7-03 passes and S7-04 binds the exact report/runtime/candidate;
- the exact runtime environment used by that handoff.

`draft-handoff` writes a digest-bound draft with `s7_03_review=BLOCKED` and
`s7_04_status=NOT_FROZEN`. The helper cannot promote those fields. At S7-04 the
Integration Owner reviews the candidate, then explicitly records `PASS` and
`FROZEN_FOR_A3` in the external file, along with stable deviation/reuse IDs.

## Preparation before candidate freeze

Choose one safe session ID and create new isolated resources. The fixture name
is deliberately constrained, and creation requires `--execute`:

```powershell
$s8Session = 's8-<run-label>'
$s8Private = '<operator-private-dir>'
$s8Data = '<new-isolated-runtime-dir>'
$s8Fixture = '<fixture-parent>\live-voice-s8-fixture-<run-label>'
$s8EffectPlan = "$s8Private\s8-fixture-effect-plan.json"
$s8ScopeCorrelations = "$s8Private\s8-scope-correlations.json"
$s8ProductTrace = "$s8Private\s8-product-trace.json"
$s8TraceManifest = "$s8Private\s8-trace-manifest.json"

New-Item -ItemType Directory -Path $s8Data -ErrorAction Stop | Out-Null
$env:JIUWENSWARM_DATA_DIR = (Resolve-Path -LiteralPath $s8Data).Path

uv run --frozen python scripts/live_voice/s8_readiness.py init-fixture `
  --session-id $s8Session `
  --root $s8Fixture `
  --execute

$env:S8_DISPOSABLE_PROJECT_ROOT = (Resolve-Path -LiteralPath $s8Fixture).Path
uv run --frozen python scripts/live_voice/s8_readiness.py resource-refs `
  --session-id $s8Session

uv run --frozen python scripts/live_voice/s8_readiness.py plan-fixture-effect `
  --session-id $s8Session `
  --expected-path '<relative-path-the-showcase-is-authorized-to-change>' `
  --output $s8EffectPlan
```

Use the returned `data_fixture` and `project_fixture` values in the S7 candidate
runtime declaration. The fixture is a standalone Git repository with no remote,
one committed `notes.txt`, and a session-bound ownership marker. Do not add a
remote or use the JiuwenSwarm source worktree as the Executor target.
`plan-fixture-effect` runs while the fixture is clean and immutably records the
baseline HEAD plus only the paths authorized before the journey. Repeat
`--expected-path` for multiple paths; omit it only for a zero-effect journey.

After S7 creates its complete external report, create the non-frozen handoff
draft:

```powershell
uv run --frozen python scripts/live_voice/s8_readiness.py draft-handoff `
  --s7-report "$s8Private\s7-complete.json" `
  --output "$s8Private\s7-a3-handoff.json"
```

The candidate report must already say `automation_status=PASS`,
`real_path_status=VERIFY` and
`s7_readiness=READY_FOR_S7_CUMULATIVE_REVIEW`. Those remain S7 facts; the S8
helper does not reinterpret them as S7-03, S7-04 or Alpha PASS. The report's
production-build row must also contain the S7-frozen bounded `dist` manifest
digest and a successful post-run build-identity check.

## S8-01 automated preflight support

Use the exact environment frozen by S7-04. Every flag declared `true` in the S7
report must exist with the literal raw value `true`; every flag declared `unset`
must be absent, not empty. Set the following A3 comparison variables to the
exact sanitized labels from the S7 runtime declaration:

```text
S8_AGENT_PROVIDER
S8_BROWSER_LABEL
S8_OS_LABEL
S8_INPUT_DEVICE_REF
S8_OUTPUT_DEVICE_REF
S8_NETWORK_REF
S8_SPEECH_PROVIDER
S8_SPEECH_API_ORIGIN
S8_SPEECH_FALLBACK
S8_STT_MODEL
S8_TTS_MODEL
S8_TTS_VOICE
S8_EXECUTOR
S8_DEPLOYMENT_TOPOLOGY
```

Also restore, without printing their values:

```text
LIVE_VOICE_SPEECH_API_KEY
JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN
S7_PRIVATE_ORIGIN
JIUWENSWARM_DATA_DIR
S8_TASK_STORE_PATH
JIUWENSWARM_LIVE_VOICE_P3_DATABASE
S8_DISPOSABLE_PROJECT_ROOT
S8_PRODUCT_SESSION_ID
AGENT_SERVER_PORT
WEB_PORT
GATEWAY_PORT
```

`S8_TASK_STORE_PATH` and the product-authoritative
`JIUWENSWARM_LIVE_VOICE_P3_DATABASE` must resolve to the same isolated SQLite
file. The frozen service values are exact: AgentServer `18092`, WebChannel
`19000`, and Gateway `19001`; alternate or duplicate role declarations block
entry.

Start the exact private same-origin HTTPS/WSS topology recorded by S7-04. Use
the backend procedure in [E2E runbook §6](../../live-voice/runbooks/E2E_RUNBOOK.md#6-启动后端)
and the candidate's reviewed Integrated Web flags from
[E2E runbook §7.1](../../live-voice/runbooks/E2E_RUNBOOK.md#71-按-milestone-选择-cumulative-integrated-或-web-alpha-产品验收).
The reverse proxy/certificate command is environment-owned and must be the one
already verified by S7; do not invent a localhost or fallback replacement in
A3. The frozen topology serves the built frontend directly through the private
HTTPS proxy; it does not require a Vite/`FRONTEND_PORT` listener. Preflight
records the external private-proxy process separately while still requiring the
AgentServer/WebChannel/Gateway listeners to be candidate-rooted.

Run the read-only preflight:

```powershell
uv run --frozen python scripts/live_voice/s8_readiness.py preflight `
  --session-id $s8Session `
  --s7-report "$s8Private\s7-complete.json" `
  --handoff "$s8Private\s7-a3-handoff.json" `
  --report "$s8Private\s8-preflight.json"
```

It verifies the report/handoff digests, exact current HEAD/branch/upstream and
dependency hashes, clean worktree before and after, raw flag semantics,
sanitized route labels, private-origin DNS/address boundary, private input
presence, isolated runtime/Task Store, owned no-remote fixture, candidate-rooted
service processes, certificate-valid HTTPS with CSP, and an actual same-origin
WSS `connection.ack`. It also recomputes the ignored `dist` manifest from disk,
requires an exact match to S7, and reads `/` plus every canonical manifest file
from private 443 with redirects/compression disabled. Every response must be
200 with exact length and content hash; the complete read has a 60-second
deadline. This binds the external proxy's served frontend to the tested build,
instead of trusting its PID or configured root. Port occupancy alone is never
health. Any mismatch returns `BLOCKED`; it never changes the environment.

After the reviewed topology exposes the active `S8_PRODUCT_SESSION_ID`, create
the immutable private product-binding file and immediately create the bound
session before any S8-01 user action:

```powershell
uv run --frozen python scripts/live_voice/s8_readiness.py init-scope-correlations `
  --session-id $s8Session `
  --output $s8ScopeCorrelations

uv run --frozen python scripts/live_voice/s8_readiness.py init-session `
  --session-id $s8Session `
  --s7-report "$s8Private\s7-complete.json" `
  --handoff "$s8Private\s7-a3-handoff.json" `
  --effect-plan $s8EffectPlan `
  --product-binding $s8ScopeCorrelations `
  --output "$s8Private\s8-session.json"
```

Run `init-scope-correlations` exactly once at this point. Its output is
non-overwritable; preserve the same file for capture, validation and cleanup.

Copy `S8_PRODUCT_SESSION_ID` from the active product composition context before
`init-session`. For every identity-bearing Showcase action, activate/invoke the
reviewed product composition route with that scope's pre-generated correlation
from the private binding. The canonical product observation must carry that exact
correlation. The helper stores only SHA-256 references and requires every scope
to use a distinct value. The binding file's exact bytes are hashed into the
session and reloaded by trace capture, validation and cleanup, so later edits to
the operator record cannot rebind evidence. If the final S7 product route cannot preserve these
caller-provided correlations, leave the journey `BLOCKED` and return that
capability gap to the S7 Integration Owner; do not label an older event. Changing
the session or map requires a new S8 session/fixture/effect plan.

The operator must then perform both S8-01 user actions. For the text/Tool smoke,
use the prompt in
[E2E runbook §8](../../live-voice/runbooks/E2E_RUNBOOK.md#8-先做文字工具冒烟再做语音)
and verify the real `tool_call → tool_result → final` sequence. For the minimum
Provider/device probe, use the declared physical microphone and output device,
speak a short fixed critical-token request, commit it, and hear the declared
streaming route. Neither action is inferred from an exit code.

## S8-02 observation session

The template starts every human check as `BLOCKED` with
`USER_OBSERVATION_REQUIRED`. Run the complete
[Alpha showcase](../../live-voice/demo/ALPHA_SHOWCASE.md), then record each
check as `PASS`, `FAIL`, `BLOCKED` or `NOT_APPLICABLE`. A reason code is required.
The helper accepts `NOT_APPLICABLE` only for a non-PASS outcome; complete Alpha
PASS requires every modeled Showcase observation to be a user-recorded `PASS`.
After the journeys, export the selected canonical
`live-voice.observability.v1` records from the reviewed product observability
collector into `$s8ProductTrace`. Each trace row contains only its Showcase
scope plus one complete, unmodified observability record. The helper validates
the existing closed product schema and event semantics, derives task, attempt,
response and round IDs from its binding, derives `work` from the canonical
`source_record_id` or `source_event_id`, and requires source sequence plus
strictly increasing product monotonic time. Every observation must match its
unique per-scope product correlation frozen by `init-session`, and every scope
has an explicit allowed
event/segment/source-component/route-class tuple. The product-owned
correlation is the pre-action journey discriminator; the event/segment pair is
also mutually exclusive across scopes. Changing only the operator-authored scope
therefore cannot relabel a same-session record. The export must bind the same
candidate, runtime declaration and session ID as the initialized session. Then
create the sanitized manifest:

```powershell
uv run --frozen python scripts/live_voice/s8_readiness.py capture-trace `
  --s7-report "$s8Private\s7-complete.json" `
  --handoff "$s8Private\s7-a3-handoff.json" `
  --product-binding $s8ScopeCorrelations `
  --record "$s8Private\s8-session.json" `
  --product-trace $s8ProductTrace `
  --output $s8TraceManifest
```

Copy the manifest's complete `identities` object into the session and use only
its aliases in each observation's `identity_bindings`. The helper recomputes the
manifest from the private trace during validation, so a stale/tampered manifest,
cross-scope reuse, future capture or session-edited identity is rejected. Every
referenced task/attempt pair must also have one exact settle row. For an early
`BLOCKED` run, export the available records (possibly none) and capture an empty
or partial manifest; never fabricate the missing identities. A selected product
record must carry every identity kind required by its scope; otherwise that
journey remains `BLOCKED`.

The platform refresh/reconnect row binds the response and round that must not be
duplicated or resurrected; it does not invent a Task before the later P3alpha
journey. Each later task-bearing scope uses its own safe isolated Task/attempt
unless two observation rows deliberately share the same scope alias.

An identity entry has this shape; use the exact scope already implied by the
observation template and the sequence at which the product trace was captured:

```json
{
  "p3.natural.task": {
    "kind": "task",
    "ref": "task_ref:sha256-<sanitized-digest>",
    "scope": "p3.natural",
    "captured_sequence": 21,
    "source_sequence": 1042,
    "source": "PRODUCT_TRACE",
    "source_record_ref": "trace_record_ref:sha256-<sanitized-digest>"
  }
}
```

All human-required `PASS` rows must retain `observer=USER`. `AUTOMATION`, fake,
audio-file or programmatic observations cannot pass physical permission,
microphone, heard playout or product-usability rows.

Before a final decision, record:

- the SHA-256 of the actual tracked binary Git diff plus untracked file state;
  expected paths and baseline HEAD remain locked to the pre-journey effect plan;
- one or more sanitized Task/attempt settle rows with outbox settled and
  owner/lease released; the helper then verifies those claims against the
  product-authoritative Task Store and Direct Executor journal;
- private artifact references and whether each is preserved or deleted manually;
- a preliminary `BLOCKED` decision until automated cleanup has been verified.

Read the current sanitized fixture effect without changing it. Confirm its
`observed_changed_paths` match the predeclared plan, then copy only
`diff_sha256` into `project_effect` (leaving the locked baseline/expected paths,
decision and cleanup action unchanged):

```powershell
uv run --frozen python scripts/live_voice/s8_readiness.py fixture-effect `
  --session-id $s8Session
```

Validate the completed record without changing it:

```powershell
uv run --frozen python scripts/live_voice/s8_readiness.py validate-session `
  --s7-report "$s8Private\s7-complete.json" `
  --handoff "$s8Private\s7-a3-handoff.json" `
  --effect-plan $s8EffectPlan `
  --product-binding $s8ScopeCorrelations `
  --product-trace $s8ProductTrace `
  --trace-manifest $s8TraceManifest `
  --record "$s8Private\s8-session.json"
```

After dry-run cleanup succeeds, the user records the final `PASS`, `PARTIAL`,
`BLOCKED` or `FAIL` decision and runs this validator. It binds the record back
to the exact report/handoff, then checks
completeness and internal consistency only. It does not decide whether an
observation was honestly performed and does not issue Alpha PASS.

## S8-03 cleanup

Exit Live Voice, stop the exact external private proxy/Gateway/AgentServer
processes recorded in the session, and update the S8-03 user observations. The
helper never kills a process. It only verifies that each recorded PID is gone,
all exact ports are released, and the authoritative SQLite snapshot proves
trace-bound Task and attempt terminal state, delivered/suppressed unclaimed
outbox, terminal Direct Executor journal, released owner/lease and acquirable
ownership lock. It also
requires exclusive trace ownership of every Direct Executor row for the
fixture, then checks fixture effects and candidate HEAD/worktree identity.
Cleanup remains available after an early `BLOCKED`/`PARTIAL` run: missing planned
effects are allowed, while every observed path must still be a subset of the
predeclared plan. A claimed `PASS` requires the complete expected effect.

Always run cleanup in dry-run mode first:

```powershell
uv run --frozen python scripts/live_voice/s8_readiness.py cleanup `
  --s7-report "$s8Private\s7-complete.json" `
  --handoff "$s8Private\s7-a3-handoff.json" `
  --effect-plan $s8EffectPlan `
  --product-binding $s8ScopeCorrelations `
  --product-trace $s8ProductTrace `
  --trace-manifest $s8TraceManifest `
  --record "$s8Private\s8-session.json" `
  --report "$s8Private\s8-cleanup.json"
```

After setting the user's final decision and validating the record, repeat this
dry-run once so the final record and cleanup facts are checked together.

Dry-run preserves the fixture. To delete it, first set
`project_effect.cleanup_action=DELETE` in the user record, rerun dry-run, then
repeat with `--execute`. Deletion is allowed only for the exact session-marked,
no-remote fixture reference. Candidate roots, HOME, filesystem roots, ancestors,
unknown paths and identity mismatches are rejected. Fixture deletion is
permanent; preserve it instead if recovery or manual inspection is still needed.
Private artifacts are never deleted automatically; `DELETE_MANUALLY` entries are
reported for the operator.

## Shortest S7-04 to S8-01 sequence

1. S7 owner finishes S7-03, freezes the external handoff as `FROZEN_FOR_A3`, and
   changes no candidate bytes afterward.
2. Restore the exact flags, route labels, secrets-by-presence, isolated paths,
   private origin, private scope-correlation map and service ports; start the
   reviewed private topology.
3. Run `preflight`; stop on any `BLOCKED` result.
4. Run `init-session` with the pre-journey effect plan.
5. Perform each S8-01/Showcase action under its frozen scope correlation; the
   user completes the text/Tool, physical Provider/device and remaining
   Showcase journeys once.
6. Export the product trace, run `capture-trace`, bind its manifest identities
   into the observation record, then stop Live Voice/services.
7. Leave the decision `BLOCKED`, finish the available record and dry-run
   `cleanup` (this also works for an early failed journey).
8. The user records the final Alpha decision, runs `validate-session`, then
   repeats dry-run `cleanup`. Use `cleanup --execute` only if permanent fixture
   deletion is wanted.
