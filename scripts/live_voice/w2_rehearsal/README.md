# W2 rehearsal portable toolkit

> **Retired acceptance path (D-071):** this toolkit is optional diagnostic and historical-forensics support only. Do not create or repair policies, keys, signatures, 38-slot manifests or Gate artifacts for W2/Alpha acceptance. Current milestone closure uses automated verification plus one complete human product acceptance. The commands below are retained only to explain existing artifacts and to support an explicitly reinstated audit-grade certification request.

This directory carries the candidate-independent tooling and deterministic audio
needed to resume the W2 discarded rehearsal on another Windows machine or in a
new Session. The authoritative procedure and safety boundary remain
[`live-voice/runbooks/E2E_RUNBOOK.md`](../../../live-voice/runbooks/E2E_RUNBOOK.md#w2-portable-toolkit).

The toolkit creates no Gate or Replacement Ledger credit by itself. It does not
contain Provider credentials, P3 bearer values, private keys, root signatures,
runtime databases, browser profiles, policies bound to an old SHA, or evidence
from a prior attempt.

## Included

- `new_w2_rehearsal_attempt.ps1`: one entry point for a fresh detached candidate,
  fresh roots, 12 leaf keypairs, the seven runtime slots and the 38-slot static
  plan. It never reads the Speech key or starts an evidence owner.
- `start_w2_rehearsal.ps1`: one entry point for policy/runtime preflight, the
  interactive controller, isolated Chrome and the real Speech/WAV probe.
- `build_*`, `complete_*`, `derive_*`, `finalize_*`: exclusive-create scaffolds
  for rehearsal policy, runtime configuration and the later formal policy.
- `w2_rehearsal_runtime_controller.py`: graceful lifecycle controller for
  `G1/A1`, `G2/A2`, `G3/A3` and restart successor `A4`.
- `w2_fault_runner.py`: policy-bound companion that drives the nine P1/P2/P3
  product fault probes through the real Gateway while observing the stock
  Chrome page through read-only CDP Network events. It does not write evidence.
- `w2_d069_runtime_diagnostic.py`: no-evidence diagnostic for the same-task
  A→B→C topology and the bounded P2/P3 fault probes.
- `validate_*` plus the candidate-unbound choreography and manifest-wiring
  contracts.
- `assets/voice-command-48k-mono-pcm16.wav`: deterministic 4.523-second Chinese
  command; its exact metadata and SHA-256 are in `assets/manifest.json`.

The synthetic Speech Provider used during early local investigation is
deliberately excluded. W2 real-path evidence must use the selected real Provider.

## Requirements restored outside Git

Before preparation, independently restore:

1. Windows PowerShell, Git, Node, Google Chrome and a repository `.venv` whose
   dependencies match the candidate.
2. One isolated `JIUWENSWARM_DATA_DIR`, a persisted Session, and one registered
   disposable Git project with repository-local `core.autocrlf=false`.
3. Real Agent and Speech Provider settings. Prefer the strict, ACL-protected
   machine-private JSON described below, stored outside the candidate, evidence
   and runtime-log roots. The launcher passes only its absolute path; values must
   never enter a command line, public runtime config, policy, evidence, Git,
   logs or chat. The hidden Speech-key prompt remains the fallback when no
   private file is supplied.
4. Browser permission/device state. The bundled WAV and isolated fake-audio
   Chrome are repeatability diagnostics only; final microphone and complete
   audible playout still require the user.

### Machine-private Provider file

Create one ACL-protected UTF-8 JSON file outside the repository candidate,
evidence roots and rehearsal log root. Its shape is closed; replace every
angle-bracket placeholder locally and never paste the resulting values into Git,
policy, evidence, command lines, logs or chat:

```json
{
  "schema": "machine-private.live-voice-no-evidence-smoke.v1",
  "agent": {
    "provider": "<agent-provider>",
    "api_base": "<agent-api-base>",
    "api_key": "<agent-api-key>",
    "model": "<agent-model>"
  },
  "speech": {
    "provider": "<speech-provider>",
    "api_base": "<speech-api-base>",
    "api_key": "<speech-api-key>",
    "stt_model": "<speech-stt-model>",
    "tts_model": "<speech-tts-model>",
    "voice": "<speech-voice>"
  }
}
```

The controller accepts only these exact keys and requires the non-secret Speech
metadata to match the signed runtime configuration. It routes the Agent key only
to AgentServer and the Speech key only to Gateway. The Gateway receives only the
Agent provider, API base and model name needed for truthful stock-Web display;
its normal dotenv initialization cannot replace those values or introduce an
Agent key. The shared data-directory `.env` must not contain credentials.

If the persisted Session does not yet exist, create it before preparing an
attempt. The model remains an explicit machine choice rather than a value frozen
by this toolkit:

```powershell
$env:JIUWENSWARM_DATA_DIR = '<absolute isolated data directory>'
& .\.venv\Scripts\python.exe `
  scripts/live_voice/w2_rehearsal/prepare_w2_bound_sessions.py `
  --project-id '<registered project id>' `
  --project-dir '<absolute clean disposable project>' `
  --session-id '<new persisted sess_ id>' `
  --model '<configured model id>'
```

## Validate this checkout

From the repository root:

```powershell
& .\.venv\Scripts\python.exe -m pytest scripts/live_voice/w2_rehearsal/tests --no-cov
& .\.venv\Scripts\python.exe -m ruff check scripts/live_voice/w2_rehearsal
& .\.venv\Scripts\python.exe -m py_compile `
  scripts/live_voice/w2_rehearsal/*.py
```

<a id="validation-ready-before-signing"></a>
## Validation-ready before signing

Do not use a root-signed rehearsal as the first integration or environment test.
Consult `live-voice/STATUS.md`, close its source/review blockers, and then complete
the unsigned validation-ready lane in
[`E2E_RUNBOOK.md` section 7.1.a](../../../live-voice/runbooks/E2E_RUNBOOK.md#validation-ready-before-signing).
At minimum, prove all of the following before `new_w2_rehearsal_attempt.ps1`:

- the private-config reference, persistent Session, registered project, selected
  Agent model, real Speech provider and disposable fixture are complete;
- a second AgentServer epoch retains the same complete Agent configuration;
- isolated Chrome opens the exact `/chat/<session_id>` URL with exactly one page,
  the expected model/project, and the correct device for the selected lane;
- the operator distinguishes the Live Voice control from the separate Integrated
  Web route-facts panel;
- deterministic-WAV P1, short P2, a forced read-only Terminal Tool turn, P3
  completed and failed terminal UI, reconnect/late-response handling, restart
  reconciliation and graceful `p2.close` all pass; and
- every owner, task, lease, port and disposable project is clean afterward.

Codex Chrome control and Computer Use may automate the repeatable operator work
when available: existing-tab navigation, clicks, text entry, bounded timing,
screenshots and status polling. Install/authorize the Chrome extension in the
exact isolated profile before the run and constrain it to the existing page;
the fault runner's one-page/CDP oracle remains authoritative. These tools do not
replace backend/task/outbox oracles, fault probes, physical Jabra capture,
complete audible playout or the user's assisted receipt. The prepared WAV is a
diagnostic input, not physical-microphone Gate evidence.

Use short, deterministic utterances and P2 prompts. A Tool-forcing prompt must
explicitly require a terminal lookup and a short answer; do not infer a Tool call
from a plausible model response. Keep the exact P3 mutation instruction and
expected clean baseline from the current candidate scaffold rather than inventing
a read-only task that cannot produce the required Git-visible effect.

## Prepare a fresh attempt

Use a reviewed exact SHA that already contains this toolkit. Do not use a dirty
checkout or reuse any prior candidate, policy, key, profile, database or evidence
root.

```powershell
$repo = 'D:\path\to\jiuwenswarm'
$candidateSha = '<reviewed 40-character SHA>'
$dataDir = 'D:\path\to\fresh-or-intentionally-retained-w2-data'
$sessionId = 'sess_<persisted-id>'
$projectId = 'proj_<registered-id>'
$projectDir = 'D:\path\to\disposable-clean-project'

& "$repo\scripts\live_voice\w2_rehearsal\new_w2_rehearsal_attempt.ps1" `
  -SourceRepository $repo `
  -CandidateSha $candidateSha `
  -DataDir $dataDir `
  -SessionId $sessionId `
  -ProjectId $projectId `
  -ProjectDir $projectDir
```

Use `-Python`, `-Node`, `-Chrome`, `-RootParent`, `-KeyParent` or
`-PreparedWav` when the new machine does not use the documented Windows
defaults. Every override is resolved and validated before candidate-bound
outputs are created.

The command prints `W2_FRESH_ATTEMPT_READY_FOR_ROOT_SIGNING` and the paths to the
candidate, staging root, generated signing script and static plan. Preserve that
JSON. A partial failure is never resumed under the same label; inspect it, then
start again with a fresh label/root.

During an already started four-experiment rehearsal, a nonfatal observation does
not require an immediate rebuild. Record it, continue collecting the remaining
safe observations, close every owner gracefully, and batch the findings at the
end. The failed evidence set remains invalid and cannot derive formal policy; a
new candidate is created only after the batched repair/review is complete. Stop
immediately for identity/authority/credential/policy mismatch, wrong or dirty
candidate, wrong Session/project/model, multiple Chrome pages, required-route
loss, unsafe residual side effects, or inability to establish required terminal
truth.

Run the generated `sign-rehearsal-policy.ps1` in a visible PowerShell window.
Independently compare and type the complete expected-root fingerprint. Send only
the three non-secret result lines (`candidate_sha`, `policy_sha256`,
`expected_root_sha256`) to the coordinating Session.

Then finalize the runtime config:

```powershell
$bundle = "$repo\scripts\live_voice\w2_rehearsal"
$staging = '<staging_root printed above>'
$expectedRoot = '<acknowledged 64-character fingerprint>'
$config = Join-Path $staging 'rehearsal-runtime-config.json'
$privateConfig = '<absolute ACL-protected live-voice-smoke.private.json>'

& "$repo\.venv\Scripts\python.exe" `
  "$bundle\finalize_w2_rehearsal_runtime_config.py" `
  --scaffold (Join-Path $staging 'attempt-scaffold.json') `
  --expected-root-sha256 $expectedRoot `
  --output $config

& "$bundle\start_w2_rehearsal.ps1" -Action Preflight -Config $config -PrivateConfig $privateConfig
```

Preflight validates a referenced private file without starting an owner. It must
return `W2_REHEARSAL_RUNTIME_PREFLIGHT=PASS` before the hidden Speech-key fallback
is entered (when no private file is used) or before any owner starts.

## Run the controller without popup ambiguity

Use one visible PowerShell window and keep it open:

```powershell
& "$bundle\start_w2_rehearsal.ps1" -Action Controller -Config $config -PrivateConfig $privateConfig
```

At the `w2-rehearsal>` prompt:

```text
start ui
start 1
start faults 1
status
wait faults 1
stop 1
start 2
start faults 2
wait faults 2
stop 2
start 3
start faults 3
wait faults 3
stop 3
start 4
stop 4
stop ui
quit
```

After `UI_READY`, open a second PowerShell and start isolated Chrome exactly
once. For automatic rehearsal and repeatability diagnostics, use prepared WAV:

```powershell
& "$bundle\start_w2_rehearsal.ps1" -Action Chrome -Config $config
```

For the final physical intervention window, use the separate physical command:

```powershell
& "$bundle\start_w2_rehearsal.ps1" -Action Chrome -Config $config -PhysicalAudio
```

It must print `audio_mode=physical`. That mode omits
`--use-fake-device-for-media-stream`, `--use-file-for-fake-audio-capture` and
`--use-fake-ui-for-media-stream`; verify the marker before granting microphone
permission. A profile already created by the prepared-WAV command cannot be
reused for the physical attempt.

`PAIR_READY=n` means only that the ports are listening. It does not mean the
journey passed. For each pair, start the fault runner after the stock page and
pair are ready with `start faults n`. The runner uses the direct Gateway socket
only for active fault RPCs and observes the stock page's same-origin Vite-proxy
socket through read-only CDP. Refresh the existing single stock page after the
runner starts, and do not begin P1 until its log contains the sanitized
`W2_FAULT_RUNNER_STOCK_SOCKET_OBSERVED` marker. The complete assisted journey is
bounded to 15 minutes.

Complete the UI journey and gracefully disconnect its P2/P3 routes, then run
`wait faults n`. The Live Voice control panel and the Integrated Web route-facts
diagnostic panel are distinct: close the actual Live Voice control after the
journey; collapsing the route-facts panel does not close the composition routes.
Only the exact `W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS ... routes=closed` marker
permits the normal `stop n` success path. Before each stop, both the Gateway and
AgentServer must also have performed at least one policy-authorized operation;
otherwise the pair is invalid. Never hard-kill a runtime owner: only graceful
stop creates the closed footer and runtime signature.

## Runtime matrix

Each of the first three pairs must independently complete the full seven-step
journey. Faults are embedded, not separate Gate runs.

| Runtime | Required class | Additional obligation |
|---|---|---|
| `G1/A1` | retriable | full real Speech→Agent→Tool→TTS journey; leave no nonterminal task |
| `G2/A2` | non-retriable | same complete journey; leave no nonterminal task |
| `G3/A3` | `STALE` zero-effect | same journey; create exact A cancelled→B completed→C nonterminal |
| `A4` | restart successor | reconcile only exact C to terminal `interrupted`/`unknown` |

The 12 fault claims are four planes (`P1`, `P2`, `P3`, observability) × three
classes. The 38-slot mapping is frozen in `w2_manifest_wiring.v1.json`.

## Current readiness

This toolkit is an operating procedure, not a mutable status source. Consult
[`live-voice/STATUS.md`](../../../live-voice/STATUS.md) before creating a signed
attempt. Prior policies, keys, browser profiles, databases and evidence roots
remain non-reusable after their attempt closes or is discarded.

## Speech probe

The real Provider probe is separate from Gate credit:

```powershell
& "$bundle\start_w2_rehearsal.ps1" -Action SpeechPreflight
```

It prompts for the key through `SecureString`, uses the bundled WAV and restores
the caller's process environment afterward. A pass confirms only that this
machine can perform the selected STT/TTS call and parse canonical WAV output.

## Formal run after a discarded rehearsal

After all seven rehearsal artifacts close and verify, use
`derive_w2_policy_scaffold.py` with the signed rehearsal import and the static
plan. Sign and validate the resulting formal policy before any formal owner
starts. Formal evidence uses new IDs, roots, leaf keys and browser profile; it
must never reuse rehearsal files. The complete derivation/evaluation procedure
is in the runbook linked above.
