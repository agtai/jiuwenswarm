[CmdletBinding()]
param(
    [ValidateRange(20, 100)]
    [int]$SuccessfulRounds = 20,
    [ValidateRange(20, 150)]
    [int]$MaxAttemptsPerTemperature = 25,
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$MachineSelection = Join-Path $env:USERPROFILE '.jiuwenswarm\config\live-voice-formal-web-validation.json'

function Fail([string]$Text) {
    throw $Text
}

function Get-DotEnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $escaped = [regex]::Escape($Name)
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match "^\s*$escaped\s*=\s*(.*)$") {
            $value = $Matches[1].Trim()
            if ($value.Length -ge 2 -and (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            )) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }
    return $null
}

function Import-PrivateValue([string]$Name, [string]$PrivateEnvPath) {
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, 'User')
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [Environment]::GetEnvironmentVariable($Name, 'Machine')
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = Get-DotEnvValue -Path $PrivateEnvPath -Name $Name
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        Fail "Missing private Speech setting $Name; Provider baseline was not run."
    }
    [Environment]::SetEnvironmentVariable($Name, $value, 'Process')
}

$scriptExitCode = 1
try {
    Write-Host 'L0_PROVIDER_BASELINE_STAGE environment'
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        Fail "Repository virtual environment is missing: $Python"
    }
    if (-not (Test-Path -LiteralPath $MachineSelection -PathType Leaf)) {
        Fail "Formal Web machine selection is missing: $MachineSelection"
    }
    $selection = Get-Content -Raw -LiteralPath $MachineSelection -Encoding UTF8 | ConvertFrom-Json
    $dataDir = [System.IO.Path]::GetFullPath([string]$selection.data_dir)
    $privateEnv = Join-Path $dataDir 'config\.env'
    foreach ($name in @(
        'LIVE_VOICE_SPEECH_API_KEY',
        'LIVE_VOICE_SPEECH_API_BASE',
        'LIVE_VOICE_SPEECH_STT_MODEL',
        'LIVE_VOICE_SPEECH_TTS_MODEL'
    )) {
        Import-PrivateValue -Name $name -PrivateEnvPath $privateEnv
    }
    Write-Host 'L0_PROVIDER_BASELINE_STAGE provider-configured'
    [Environment]::SetEnvironmentVariable('LIVE_VOICE_SPEECH_PROVIDER', 'openai', 'Process')
    [Environment]::SetEnvironmentVariable('LIVE_VOICE_SPEECH_TTS_VOICE', 'marin', 'Process')
    [Environment]::SetEnvironmentVariable('LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED', '1', 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8', 'Process')

    if ([string]::IsNullOrWhiteSpace($OutputPath)) {
        $OutputPath = Join-Path $RepoRoot 'logs\l0-provider-baseline.json'
    } elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
        $OutputPath = Join-Path $RepoRoot $OutputPath
    }
    $OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
    New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null

    Set-Location -LiteralPath $RepoRoot
    Write-Host 'L0_PROVIDER_BASELINE_STAGE running'
    & $Python scripts\live_voice\l0_measurement_baseline.py provider-baseline `
        --successful-rounds $SuccessfulRounds `
        --max-attempts-per-temperature $MaxAttemptsPerTemperature `
        --output $OutputPath
    $providerExit = $LASTEXITCODE
    if ($providerExit -notin @(0, 2)) {
        Fail "Provider baseline tool failed (exit=$providerExit)."
    }
    Write-Host "L0_PROVIDER_BASELINE_RESULT output=$OutputPath complete=$($providerExit -eq 0)"
    $scriptExitCode = $providerExit
} catch {
    [Console]::Error.WriteLine([string]$_.Exception.Message)
    $scriptExitCode = 1
}
exit $scriptExitCode
