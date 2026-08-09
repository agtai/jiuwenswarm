[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $SourceRepository,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string] $CandidateSha,
    [Parameter(Mandatory = $true)][string] $DataDir,
    [Parameter(Mandatory = $true)][string] $SessionId,
    [Parameter(Mandatory = $true)][string] $ProjectId,
    [Parameter(Mandatory = $true)][string] $ProjectDir,
    [string] $RootParent,
    [string] $KeyParent,
    [string] $Python,
    [string] $Node = 'C:\Program Files\nodejs\node.exe',
    [string] $Chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe',
    [string] $PreparedWav
)

$ErrorActionPreference = 'Stop'

function Resolve-ExistingDirectory {
    param([Parameter(Mandatory = $true)][string] $Path, [Parameter(Mandatory = $true)][string] $Label)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (-not $item.PSIsContainer -or $item.PSProvider.Name -ne 'FileSystem') {
        throw "$Label must be an existing filesystem directory: $Path"
    }
    return $item.FullName
}

function Resolve-ExistingFile {
    param([Parameter(Mandatory = $true)][string] $Path, [Parameter(Mandatory = $true)][string] $Label)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item.PSIsContainer -or $item.PSProvider.Name -ne 'FileSystem') {
        throw "$Label must be an existing filesystem file: $Path"
    }
    return $item.FullName
}

$source = Resolve-ExistingDirectory -Path $SourceRepository -Label 'Source repository'
$data = Resolve-ExistingDirectory -Path $DataDir -Label 'Runtime data directory'
$project = Resolve-ExistingDirectory -Path $ProjectDir -Label 'Disposable project'
$Node = Resolve-ExistingFile -Path $Node -Label 'Node executable'
$Chrome = Resolve-ExistingFile -Path $Chrome -Label 'Chrome executable'

if (-not $Python) {
    $Python = Join-Path $source '.venv\Scripts\python.exe'
}
$Python = Resolve-ExistingFile -Path $Python -Label 'Python interpreter'
if (-not $RootParent) {
    $RootParent = Split-Path -Parent $source
}
$RootParent = Resolve-ExistingDirectory -Path $RootParent -Label 'Attempt root parent'
if (-not $KeyParent) {
    $KeyParent = Join-Path $env:LOCALAPPDATA 'JiuwenSwarm\live-voice\w2-keys'
}
New-Item -ItemType Directory -Path $KeyParent -Force | Out-Null
$KeyParent = Resolve-ExistingDirectory -Path $KeyParent -Label 'Key parent'

$resolvedCommit = (git -C $source rev-parse "$CandidateSha^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $resolvedCommit -cne $CandidateSha) {
    throw 'Candidate SHA is not an exact commit in the source repository'
}

$label = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $CandidateSha.Substring(0, 10)
$candidateRoot = Join-Path $RootParent "jiuwenswarm-w2-gate-$label"
$stagingRoot = Join-Path $RootParent "jiuwenswarm-w2-gate-staging-$label"
$rehearsalRoot = Join-Path $RootParent "jiuwenswarm-evidence-live-voice-w2-rehearsal-$label"
$formalRoot = Join-Path $RootParent "jiuwenswarm-evidence-live-voice-w2-$label"
$keyRoot = Join-Path $KeyParent $label
$externalRoot = Join-Path (Join-Path $env:LOCALAPPDATA 'JiuwenSwarm\live-voice\w2-external-root') $label
$chromeProfile = Join-Path $data "browser-profile-w2-rehearsal-$label"

foreach ($path in @($candidateRoot, $stagingRoot, $rehearsalRoot, $formalRoot, $keyRoot, $externalRoot, $chromeProfile)) {
    if (Test-Path -LiteralPath $path) { throw "Fresh attempt path already exists: $path" }
}

git -C $source worktree add --detach -- $candidateRoot $CandidateSha
if ($LASTEXITCODE -ne 0) { throw 'Detached candidate worktree creation failed' }
if ((git -C $candidateRoot rev-parse HEAD).Trim() -cne $CandidateSha) {
    throw 'Detached candidate HEAD mismatch'
}
if (git -C $candidateRoot status --porcelain=v1 --untracked-files=all) {
    throw 'Detached candidate is dirty'
}
$candidateBundle = Join-Path $candidateRoot 'scripts\live_voice\w2_rehearsal'
$candidateScaffoldScript = Resolve-ExistingFile `
    -Path (Join-Path $candidateBundle 'build_w2_fresh_attempt_scaffold.py') `
    -Label 'Candidate-bound scaffold script'
$candidatePlanScript = Resolve-ExistingFile `
    -Path (Join-Path $candidateBundle 'complete_w2_gate_plan.py') `
    -Label 'Candidate-bound plan completion script'
if (-not $PreparedWav) {
    $PreparedWav = Join-Path $candidateBundle 'assets\voice-command-48k-mono-pcm16.wav'
}
$PreparedWav = Resolve-ExistingFile -Path $PreparedWav -Label 'Prepared WAV'

foreach ($path in @($stagingRoot, $rehearsalRoot, $formalRoot, $keyRoot)) {
    New-Item -ItemType Directory -Path $path -ErrorAction Stop | Out-Null
}
New-Item -ItemType Directory -Path (Split-Path -Parent $externalRoot) -Force | Out-Null
foreach ($scope in @('rehearsal', 'formal')) {
    $scopeRoot = Join-Path $keyRoot $scope
    New-Item -ItemType Directory -Path $scopeRoot -ErrorAction Stop | Out-Null
    foreach ($role in @('runtime-gateway', 'runtime-agentserver', 'automated', 'independent-review', 'fault-injection', 'human-observation')) {
        $private = Join-Path $scopeRoot "$role.private"
        $public = Join-Path $scopeRoot "$role.public"
        $previousPythonPath = $env:PYTHONPATH
        try {
            $env:PYTHONPATH = $candidateRoot
            Push-Location $candidateRoot
            try {
                & $Python -m jiuwenswarm.server.live_voice.w2_gate_cli keygen --private-key $private --public-key $public
                if ($LASTEXITCODE -ne 0) { throw "Leaf key generation failed: $scope/$role" }
            } finally {
                Pop-Location
            }
        } finally {
            $env:PYTHONPATH = $previousPythonPath
        }
    }
}

& $Python $candidateScaffoldScript `
    --label $label `
    --candidate-root $candidateRoot `
    --candidate-sha $CandidateSha `
    --staging-root $stagingRoot `
    --rehearsal-root $rehearsalRoot `
    --formal-evidence-root $formalRoot `
    --key-root $keyRoot `
    --external-root $externalRoot `
    --chrome-profile $chromeProfile `
    --data-dir $data `
    --session-id $SessionId `
    --project-id $ProjectId `
    --project-dir $project `
    --python $Python `
    --node $Node `
    --chrome $Chrome `
    --prepared-wav $PreparedWav
if ($LASTEXITCODE -ne 0) { throw 'Fresh attempt scaffold generation failed' }

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $candidateRoot
    Push-Location $candidateRoot
    try {
        & $Python $candidatePlanScript `
            --input (Join-Path $stagingRoot 'candidate-plan.incomplete.json') `
            --output (Join-Path $stagingRoot 'candidate-plan.static-complete.json')
        if ($LASTEXITCODE -ne 0) { throw 'Static 38-slot plan completion failed' }
    } finally {
        Pop-Location
    }
} finally {
    $env:PYTHONPATH = $previousPythonPath
}

[ordered]@{
    status = 'W2_FRESH_ATTEMPT_READY_FOR_ROOT_SIGNING'
    label = $label
    candidate_sha = $CandidateSha
    candidate_root = $candidateRoot
    staging_root = $stagingRoot
    rehearsal_root = $rehearsalRoot
    formal_evidence_root = $formalRoot
    key_root = $keyRoot
    chrome_profile = $chromeProfile
    sign_rehearsal_policy = (Join-Path $stagingRoot 'sign-rehearsal-policy.ps1')
    attempt_scaffold = (Join-Path $stagingRoot 'attempt-scaffold.json')
    static_plan = (Join-Path $stagingRoot 'candidate-plan.static-complete.json')
} | ConvertTo-Json -Depth 4
