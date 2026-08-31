# Live Voice 前端构建合同（schema v2）。
#
# 合同把一次成功构建绑定到：源码 HEAD、前端子树、依赖锁、bundle 摘要，
# 以及**全部编译期 Vite 输入**（构建时进程环境里所有 VITE_* 变量的精确快照）。
# 复用要求逐项精确相等；出现新的/未知的 VITE_ 输入同样使旧合同失效。
# 运行时旗标声明必须从已验证的合同派生，而不是当前命令行参数。

Set-StrictMode -Version Latest

$script:LiveVoiceBuildContractSchemaVersion = 2

function Get-LiveVoiceViteBuildInputs {
    <# 返回当前进程环境中全部 VITE_* 变量的有序精确快照。 #>
    $inputs = [ordered]@{}
    Get-ChildItem Env: |
        Where-Object { $_.Name -clike 'VITE_*' } |
        Sort-Object Name |
        ForEach-Object { $inputs[$_.Name] = [string]$_.Value }
    return $inputs
}

function New-LiveVoiceBuildContract {
    param(
        [Parameter(Mandatory)][string]$SourceHead,
        [Parameter(Mandatory)][string]$FrontendTree,
        [Parameter(Mandatory)][string]$PackageLockSha256,
        [Parameter(Mandatory)][string]$BundleRelativePath,
        [Parameter(Mandatory)][string]$BundleSha256,
        [Parameter(Mandatory)]$ViteEnv
    )
    $viteOrdered = [ordered]@{}
    if ($ViteEnv -is [System.Collections.IDictionary]) {
        foreach ($name in ($ViteEnv.Keys | Sort-Object)) {
            $viteOrdered[[string]$name] = [string]$ViteEnv[$name]
        }
    } else {
        foreach ($property in ($ViteEnv.PSObject.Properties | Sort-Object Name)) {
            $viteOrdered[[string]$property.Name] = [string]$property.Value
        }
    }
    return [ordered]@{
        schema_version       = $script:LiveVoiceBuildContractSchemaVersion
        source_head          = $SourceHead
        frontend_tree        = $FrontendTree
        package_lock_sha256  = $PackageLockSha256
        bundle_relative_path = $BundleRelativePath
        bundle_sha256        = $BundleSha256
        vite_env             = $viteOrdered
    }
}

function Get-LiveVoiceContractViteEnv {
    <# 从合同对象（含 ConvertFrom-Json 的 PSCustomObject）取回旗标快照。 #>
    param([Parameter(Mandatory)]$Contract)
    $result = [ordered]@{}
    $viteEnv = $Contract.vite_env
    if ($null -eq $viteEnv) { return $result }
    if ($viteEnv -is [System.Collections.IDictionary]) {
        foreach ($name in ($viteEnv.Keys | Sort-Object)) {
            $result[[string]$name] = [string]$viteEnv[$name]
        }
        return $result
    }
    foreach ($property in ($viteEnv.PSObject.Properties | Sort-Object Name)) {
        $result[[string]$property.Name] = [string]$property.Value
    }
    return $result
}

function Test-LiveVoiceBuildContractReuse {
    <# 判定合同能否复用。返回 $null 表示允许；否则返回带原因码的拒绝文本。
       bundle 路径合法性与 bundle 哈希比对由调用方完成（文件系统职责）。 #>
    param(
        [Parameter(Mandatory)]$Contract,
        [Parameter(Mandatory)][string]$SourceHead,
        [Parameter(Mandatory)][string]$FrontendTree,
        [Parameter(Mandatory)][string]$PackageLockSha256,
        [Parameter(Mandatory)]$CurrentViteEnv
    )
    $schemaVersion = $null
    if ($null -ne $Contract.PSObject.Properties['schema_version']) {
        $schemaVersion = $Contract.schema_version
    }
    if ($schemaVersion -ne $script:LiveVoiceBuildContractSchemaVersion) {
        return "BUILD_CONTRACT_SCHEMA_UNSUPPORTED: 合同 schema_version=$schemaVersion，要求 $($script:LiveVoiceBuildContractSchemaVersion)；旧合同不携带编译期旗标绑定，必须全量重建。"
    }
    if ([string]$Contract.source_head -cne $SourceHead) {
        return 'BUILD_CONTRACT_SOURCE_MISMATCH: 合同绑定的源码 HEAD 与当前不一致。'
    }
    if ([string]$Contract.frontend_tree -cne $FrontendTree) {
        return 'BUILD_CONTRACT_FRONTEND_TREE_MISMATCH: 合同绑定的前端子树与当前不一致。'
    }
    if ([string]$Contract.package_lock_sha256 -cne $PackageLockSha256) {
        return 'BUILD_CONTRACT_LOCKFILE_MISMATCH: 合同绑定的依赖锁与当前不一致。'
    }
    $recorded = Get-LiveVoiceContractViteEnv -Contract $Contract
    $current = [ordered]@{}
    if ($CurrentViteEnv -is [System.Collections.IDictionary]) {
        foreach ($name in ($CurrentViteEnv.Keys | Sort-Object)) {
            $current[[string]$name] = [string]$CurrentViteEnv[$name]
        }
    } else {
        foreach ($property in ($CurrentViteEnv.PSObject.Properties | Sort-Object Name)) {
            $current[[string]$property.Name] = [string]$property.Value
        }
    }
    foreach ($name in $recorded.Keys) {
        if (-not $current.Contains($name)) {
            return "BUILD_CONTRACT_VITE_INPUTS_CHANGED: 构建期输入 $name 现已缺失；旗标组合变化必须全量重建。"
        }
        if ($current[$name] -cne $recorded[$name]) {
            return "BUILD_CONTRACT_VITE_INPUTS_CHANGED: 构建期输入 $name 的值已变化；旗标组合变化必须全量重建。"
        }
    }
    foreach ($name in $current.Keys) {
        if (-not $recorded.Contains($name)) {
            return "BUILD_CONTRACT_VITE_INPUTS_CHANGED: 出现合同未记录的构建期输入 $name；未知旗标使旧合同失效，必须全量重建。"
        }
    }
    return $null
}

Export-ModuleMember -Function Get-LiveVoiceViteBuildInputs, New-LiveVoiceBuildContract, Get-LiveVoiceContractViteEnv, Test-LiveVoiceBuildContractReuse
