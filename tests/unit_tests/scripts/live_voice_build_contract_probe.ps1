# 探针：驱动 build_contract.psm1 的纯函数，把各场景结果以 JSON 输出给 pytest。
param(
    [Parameter(Mandatory)][string]$ModulePath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module -Name $ModulePath -Force

$env:VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION = 'true'
$env:VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1 = 'true'

$inputs = Get-LiveVoiceViteBuildInputs
$contract = New-LiveVoiceBuildContract `
    -SourceHead 'head-1' `
    -FrontendTree 'tree-1' `
    -PackageLockSha256 'lock-1' `
    -BundleRelativePath 'dist\assets\index-abc.js' `
    -BundleSha256 'bundle-1' `
    -ViteEnv $inputs

# 走 JSON 往返：复用路径拿到的是 ConvertFrom-Json 的 PSCustomObject。
$parsed = ($contract | ConvertTo-Json -Depth 5) | ConvertFrom-Json

function Probe {
    param([string]$SourceHead = 'head-1', [string]$Lock = 'lock-1', $Contract = $parsed)
    return Test-LiveVoiceBuildContractReuse `
        -Contract $Contract `
        -SourceHead $SourceHead `
        -FrontendTree 'tree-1' `
        -PackageLockSha256 $Lock `
        -CurrentViteEnv (Get-LiveVoiceViteBuildInputs)
}

$results = [ordered]@{}
$results.same = Probe

$env:VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION = 'false'
$results.flip_true_to_false = Probe
$env:VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION = 'true'

Remove-Item Env:VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION
$results.recorded_input_missing = Probe
$env:VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION = 'true'

$env:VITE_NEW_UNKNOWN_FLAG = 'on'
$results.unknown_new_input = Probe
Remove-Item Env:VITE_NEW_UNKNOWN_FLAG

$results.lock_mismatch = Probe -Lock 'lock-2'
$results.source_mismatch = Probe -SourceHead 'head-2'

$legacy = '{"schema_version":1,"source_head":"head-1","frontend_tree":"tree-1","package_lock_sha256":"lock-1"}' | ConvertFrom-Json
$results.legacy_schema = Probe -Contract $legacy

$flags = Get-LiveVoiceContractViteEnv -Contract $parsed
$results.contract_flag_value = [string]$flags['VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION']

$results | ConvertTo-Json -Depth 4
