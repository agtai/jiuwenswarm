# W2 rehearsal portable toolkit

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
3. The real Provider key. Enter it only into the hidden prompt; never put it in a
   command line, config file, policy, evidence, Git or chat.
4. Browser permission/device state. The bundled WAV and isolated fake-audio
   Chrome are repeatability diagnostics only; final microphone and complete
   audible playout still require the user.

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

& "$repo\.venv\Scripts\python.exe" `
  "$bundle\finalize_w2_rehearsal_runtime_config.py" `
  --scaffold (Join-Path $staging 'attempt-scaffold.json') `
  --expected-root-sha256 $expectedRoot `
  --output $config

& "$bundle\start_w2_rehearsal.ps1" -Action Preflight -Config $config
```

Preflight must return `W2_REHEARSAL_RUNTIME_PREFLIGHT=PASS` before entering a
Provider key or starting any owner.

## Run the controller without popup ambiguity

Use one visible PowerShell window and keep it open:

```powershell
& "$bundle\start_w2_rehearsal.ps1" -Action Controller -Config $config
```

At the `w2-rehearsal>` prompt:

```text
start ui
start 1
status
stop 1
start 2
stop 2
start 3
stop 3
start 4
stop 4
stop ui
quit
```

After `UI_READY`, open a second PowerShell and start the isolated deterministic
Chrome exactly once:

```powershell
& "$bundle\start_w2_rehearsal.ps1" -Action Chrome -Config $config
```

`PAIR_READY=n` means only that the ports are listening. It does not mean the
journey passed. Before each `stop n`, verify that both the Gateway and AgentServer
performed at least one policy-authorized operation; otherwise one producer may
correctly have no artifact and the pair must be discarded. Never hard-kill a
runtime owner: only graceful stop creates the closed footer and runtime signature.

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

## Current diagnostic blockers (2026-08-10)

Do not start a new signed rehearsal merely because the toolkit is portable. The
discarded `a7de738d69` run found source/runtime blockers that require a reviewed
descendant first:

1. repeated P3 progress ACK rejection generated no canonical progress/UI success
   and inflated AgentServer observations;
2. `product.voice_task_origin` lacked the full interaction/response/generation
   binding required by the observer;
3. refresh during Pair1→Pair2 left the browser P2 activation journal in
   `result_unknown`, so every formal route stayed unavailable even though server
   logs showed activate and close completion;
4. P3 UI state made cancel/retry controls inaccessible or incorrectly
   `ineligible`, preventing the exact A→B→C journey.

The candidate-unbound choreography validator also keeps two production probes
explicitly unresolved: P2 non-retriable presentation rejection and P3
non-retriable mutation rejection. They must pass in the same short no-evidence
smoke after the four source/runtime fixes and before any new policy is signed.

Until those findings are fixed, reviewed, integrated and both probes pass, use
this bundle only for static validation or explicitly discarded diagnostics. The
prior Pair1/Pair2 artifacts and all prior policies/keys/evidence roots remain
discarded.

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
