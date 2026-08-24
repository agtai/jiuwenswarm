[CmdletBinding()]
param(
    [string]$ProjectPath,
    [string]$ProjectId,
    [string]$DataDir,
    [string]$EnvironmentRef,
    [string]$EvidenceDirectory,
    [string]$BrowserPath = '/',
    [ValidateSet(20)]
    [int]$SuccessfulRounds = 20,
    [ValidateRange(9222, 9322)]
    [int]$CoordinatorPort = 9233,
    [ValidateRange(600, 7200)]
    [int]$TemperatureTimeoutSeconds = 3600,
    [ValidateRange(40, 80)]
    [int]$MaximumColdEpochs = 80
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Launcher = Join-Path $PSScriptRoot 'start_hands_free_demo.ps1'
if ([string]::IsNullOrWhiteSpace($EnvironmentRef) -or $EnvironmentRef -notmatch '^[a-z0-9][a-z0-9._-]{0,63}$') {
    throw 'EnvironmentRef must be a required safe environment label.'
}
if ($BrowserPath -notmatch '^/(?:chat/[A-Za-z0-9_-]+)?$') {
    throw 'BrowserPath must be / or one safe /chat/<session> path.'
}
if ([string]::IsNullOrWhiteSpace($EvidenceDirectory)) {
    $EvidenceDirectory = Join-Path $RepoRoot (
        'logs\l0-ordinary-{0}' -f (Get-Date -Format 'yyyyMMdd-HHmmss')
    )
} elseif (-not [System.IO.Path]::IsPathRooted($EvidenceDirectory)) {
    $EvidenceDirectory = Join-Path $RepoRoot ('logs\' + $EvidenceDirectory)
}
$EvidenceDirectory = [System.IO.Path]::GetFullPath($EvidenceDirectory)
$Nonce = [guid]::NewGuid().ToString('N')

function New-EpochId {
    return [guid]::NewGuid().ToString('N')
}

function Invoke-ControlledEpoch(
    [string]$Temperature,
    [string]$EpochId,
    [bool]$Resume,
    [bool]$OpenBrowser
) {
    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $Launcher,
        '-RuntimeProfile', 'formal-web-validation',
        '-RestartExisting',
        '-L0OrdinaryChromeBatch',
        '-L0Temperature', $Temperature,
        '-L0SuccessfulRounds', [string]$SuccessfulRounds,
        '-L0BatchPort', [string]$CoordinatorPort,
        '-L0MeasurementDirectory', $EvidenceDirectory,
        '-L0EnvironmentRef', $EnvironmentRef,
        '-L0BatchNonce', $Nonce,
        '-L0EpochId', $EpochId,
        '-L0BrowserPath', $BrowserPath
    )
    if (-not [string]::IsNullOrWhiteSpace($ProjectPath)) {
        $arguments += @('-ProjectPath', $ProjectPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($ProjectId)) {
        $arguments += @('-ProjectId', $ProjectId)
    }
    if (-not [string]::IsNullOrWhiteSpace($DataDir)) {
        $arguments += @('-DataDir', $DataDir)
    }
    if ($Resume) {
        $arguments += @('-L0ResumeBatch', '-L0ReuseValidatedBuild')
    }
    if (-not $OpenBrowser) {
        $arguments += '-NoBrowser'
    }
    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Controlled $Temperature launcher epoch failed (exit=$LASTEXITCODE)."
    }
}

function Wait-Epoch(
    [string]$EpochId,
    [bool]$RequireTemperatureComplete
) {
    $marker = Join-Path $EvidenceDirectory "epoch-$EpochId.json"
    $deadline = [DateTime]::UtcNow.AddSeconds($TemperatureTimeoutSeconds)
    do {
        if (Test-Path -LiteralPath $marker -PathType Leaf) {
            try {
                $result = Get-Content -Raw -LiteralPath $marker -Encoding UTF8 | ConvertFrom-Json
                if (
                    $result.epoch_id -eq $EpochId -and
                    ($RequireTemperatureComplete -eq $false -or $result.temperature_complete -eq $true)
                ) {
                    return $result
                }
            } catch {
                # Atomic writer may be between replace and reader open; retry.
            }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out waiting for L0 epoch $EpochId."
}

function Wait-CoordinatorReleased {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $listeners = @(
            Get-NetTCPConnection -State Listen -LocalPort $CoordinatorPort `
                -ErrorAction SilentlyContinue
        )
        if ($listeners.Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "L0 coordinator port $CoordinatorPort was not released after the epoch."
}

function Test-ColdComplete {
    $reportPath = Join-Path $EvidenceDirectory 'd095-report.json'
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
        return $false
    }
    try {
        $report = Get-Content -Raw -LiteralPath $reportPath -Encoding UTF8 | ConvertFrom-Json
        $cold = @($report.profiles | Where-Object { $_.temperature -eq 'cold' })
        return $cold.Count -eq 1 -and $cold[0].complete -eq $true
    } catch {
        return $false
    }
}

Write-Host "`n==> D-095 warm ordinary-Chrome batch" -ForegroundColor Cyan
$warmEpoch = New-EpochId
Invoke-ControlledEpoch -Temperature 'warm' -EpochId $warmEpoch -Resume $false -OpenBrowser $true
Write-Host '  [ACTION] Click Start automatic batch once in ordinary Chrome and grant microphone permission if prompted.' -ForegroundColor Yellow
$null = Wait-Epoch -EpochId $warmEpoch -RequireTemperatureComplete $true
Wait-CoordinatorReleased
Write-Host '  [OK] warm: non-counted warm-up, first-audio and dedicated barge targets completed' -ForegroundColor Green

Write-Host "`n==> D-095 cold fresh-launcher epochs" -ForegroundColor Cyan
for ($index = 0; $index -lt $MaximumColdEpochs -and -not (Test-ColdComplete); $index++) {
    $coldEpoch = New-EpochId
    Invoke-ControlledEpoch -Temperature 'cold' -EpochId $coldEpoch -Resume $true -OpenBrowser $false
    $result = Wait-Epoch -EpochId $coldEpoch -RequireTemperatureComplete $false
    Wait-CoordinatorReleased
    $outcome = if ($result.eligible -eq $true) { 'eligible' } else { 'retry-required' }
    Write-Host "  [OK] cold epoch $($index + 1): $outcome" -ForegroundColor Green
}
if (-not (Test-ColdComplete)) {
    throw "cold did not reach both 20-success targets in $MaximumColdEpochs fresh launcher epochs."
}

$finalReport = Join-Path $EvidenceDirectory 'd095-report.json'
$report = Get-Content -Raw -LiteralPath $finalReport -Encoding UTF8 | ConvertFrom-Json
if ($report.complete -ne $true) {
    throw 'The D-095 report did not close both cold and warm metrics.'
}
Write-Host "`nD-095 ordinary-Chrome automatic series completed: $finalReport" -ForegroundColor Green
Write-Host 'Results are Browser digital-path metrics; no per-round physical audibility or silence is claimed.' -ForegroundColor Yellow
