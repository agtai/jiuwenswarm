[CmdletBinding()]
param(
    [ValidateSet('hands-free-demo', 'formal-web-validation')]
    [string]$RuntimeProfile = 'hands-free-demo',
    [string]$ProjectPath,
    [string]$ProjectId,
    [string]$DataDir,
    [switch]$SaveConfiguration,
    [switch]$PreflightOnly,
    [switch]$RestartExisting,
    [switch]$AllowDirtyProject,
    [switch]$NoBrowser,
    [switch]$L0Measurement,
    [ValidateRange(9222, 9322)]
    [int]$L0MeasurementPort = 9223,
    [string]$L0MeasurementDirectory,
    [string]$L0EnvironmentRef,
    [ValidateRange(30, 300)]
    [int]$ReadyTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$StopCommand = Join-Path $RepoRoot '.venv\Scripts\jiuwenswarm-stop.exe'
$FrontendRoot = Join-Path $RepoRoot 'jiuwenswarm\channels\web\frontend'
$ProductionFrontendEnv = Join-Path $FrontendRoot '.env.production'
$LiveVoiceFrontendEnv = Join-Path $FrontendRoot '.env.live-voice'
$FormalWebRuntimeProbe = Join-Path $PSScriptRoot 'formal_web_runtime_probe.py'
$ExpectedBranch = 'hx/0812_live_voice_w3'
$FrontendPort = if ($RuntimeProfile -eq 'formal-web-validation') { 5173 } else { 6173 }
$RuntimeProfileLabel = if ($RuntimeProfile -eq 'formal-web-validation') {
    'Formal Web validation'
} else {
    'hands-free orders Demo'
}
$ExecutorProfile = 'live-voice.direct-project-code.d2.v1'
$ExpectedPorts = [ordered]@{
    FRONTEND_PORT     = $FrontendPort
    AGENT_SERVER_PORT = 18092
    WEB_PORT          = 19000
    GATEWAY_PORT      = 19001
}
$ExpectedOrderInputs = @(
    '01-去程航班.md',
    '02-上海酒店.md',
    '03-上海观景预约.md',
    '04-上海至杭州高铁.md',
    '05-杭州游船预约.md',
    '06-杭州酒店.md',
    '07-返程高铁.md'
)

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Write-Pass([string]$Text) {
    Write-Host "  [OK] $Text" -ForegroundColor Green
}

function Write-Warn([string]$Text) {
    Write-Host "  [WARN] $Text" -ForegroundColor Yellow
}

function Fail([string]$Text) {
    throw $Text
}

function Get-ChromeExecutable {
    $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    $candidateRoots = @(
        $env:ProgramFiles,
        $programFilesX86,
        $env:LOCALAPPDATA
    )
    foreach ($root in $candidateRoots) {
        if ([string]::IsNullOrWhiteSpace($root)) {
            continue
        }
        $candidate = Join-Path $root 'Google\Chrome\Application\chrome.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Get-Item -LiteralPath $candidate -Force).FullName
        }
    }
    Fail '找不到 Google Chrome。请安装桌面版 Google Chrome，或使用 -NoBrowser 仅启动服务。'
}

function Start-IsolatedChrome(
    [string]$ChromeExecutable,
    [string]$Url,
    [int]$RemoteDebuggingPort = 0
) {
    $profileName = 'jiuwenswarm-live-voice-chrome-{0}-{1}' -f (
        Get-Date -Format 'yyyyMMdd-HHmmss'
    ), ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $profilePath = Join-Path ([System.IO.Path]::GetTempPath()) $profileName
    if (Test-Path -LiteralPath $profilePath) {
        Fail "隔离 Chrome profile 路径意外已存在：$profilePath"
    }
    New-Item -ItemType Directory -Path $profilePath | Out-Null

    $quotedProfilePath = '"' + $profilePath + '"'
    $arguments = @(
        "--user-data-dir=$quotedProfilePath",
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-mode',
        '--new-window'
    )
    if ($RemoteDebuggingPort -gt 0) {
        $arguments += "--remote-debugging-port=$RemoteDebuggingPort"
    }
    $arguments += $Url
    $chrome = Start-Process -FilePath $ChromeExecutable -ArgumentList $arguments -WindowStyle Normal -PassThru
    Start-Sleep -Milliseconds 750
    if ($chrome.HasExited) {
        Fail "隔离 Chrome 启动后立即退出（exit=$($chrome.ExitCode)）。"
    }
    return $profilePath
}

function Stop-ExistingIsolatedChrome([string]$ChromeExecutable) {
    $profilePrefix = Join-Path ([System.IO.Path]::GetTempPath()) 'jiuwenswarm-live-voice-chrome-'
    $processes = @(
        Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*$profilePrefix*" }
    )
    if ($processes.Count -eq 0) {
        return
    }
    $unexpected = @(
        $processes | Where-Object {
            [string]::IsNullOrWhiteSpace([string]$_.ExecutablePath) -or
            ([string]$_.ExecutablePath -ine $ChromeExecutable)
        }
    )
    if ($unexpected.Count -gt 0) {
        Fail '旧隔离 Chrome profile 匹配到了非预期可执行文件；为避免误停进程，脚本已停止。'
    }
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 250
        $remaining = @(
            Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -like "*$profilePrefix*" }
        )
    } while ($remaining.Count -gt 0 -and [DateTime]::UtcNow -lt $deadline)
    if ($remaining.Count -gt 0) {
        Fail "仍有 $($remaining.Count) 个旧隔离 Chrome 进程未退出。"
    }
    Write-Pass "已关闭 $($processes.Count) 个旧隔离 Chrome 进程；未删除其 profile 目录"
}

function Get-CanonicalPath([string]$Path) {
    return (Get-Item -LiteralPath $Path -Force -ErrorAction Stop).FullName.TrimEnd('\')
}

function Get-DotEnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    $escaped = [regex]::Escape($Name)
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match "^\s*$escaped\s*=\s*(.*)$") {
            $value = $Matches[1].Trim()
            if ($value.Length -ge 2) {
                if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                    ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
            }
            return $value
        }
    }
    return $null
}

function Import-PrivateValue([string]$Name, [string]$PrivateEnvPath, [switch]$Required) {
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
        if ($Required) {
            Fail "缺少私有配置 $Name。请把它保存在 Windows 用户环境变量或 $PrivateEnvPath；不要写入仓库。"
        }
        return $null
    }
    [Environment]::SetEnvironmentVariable($Name, $value, 'Process')
    return $value
}

function Invoke-Git([string[]]$Arguments) {
    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail "git $($Arguments -join ' ') 失败：$($output -join ' ')"
    }
    return @($output)
}

function Get-ListeningOwners([int[]]$Ports) {
    $rows = @()
    foreach ($port in $Ports) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
            $rows += [pscustomobject]@{
                Port        = $port
                ProcessId   = [int]$listener.OwningProcess
                Name        = if ($null -ne $process) { [string]$process.Name } else { '' }
                CommandLine = if ($null -ne $process) { [string]$process.CommandLine } else { '' }
            }
        }
    }
    return @($rows | Sort-Object ProcessId, Port -Unique)
}

function Stop-ExistingDemoServices {
    $statePath = Join-Path $RepoRoot 'logs\debug_service.json'
    if ((Test-Path -LiteralPath $statePath -PathType Leaf) -and (Test-Path -LiteralPath $StopCommand -PathType Leaf)) {
        Write-Host '  正在停止由调试启动器管理的旧服务……'
        & $StopCommand --timeout 15
        if ($LASTEXITCODE -ne 0) {
            Fail '旧调试服务未能正常停止。'
        }
    }

    $owners = @(Get-ListeningOwners -Ports @($ExpectedPorts.Values))
    if ($owners.Count -eq 0) {
        return
    }

    foreach ($owner in ($owners | Sort-Object ProcessId -Unique)) {
        if ($owner.Name -notmatch '^python(w)?\.exe$' -or $owner.CommandLine -notmatch 'jiuwenswarm\.(channels\.web\.app_web|server\.app_agentserver|gateway\.app_gateway|start_services)') {
            Fail "端口 $($owner.Port) 被非 JiuwenSwarm 进程占用（PID $($owner.ProcessId)，$($owner.Name)）。为避免误杀进程，脚本已停止。"
        }
        Write-Host "  停止旧 JiuwenSwarm 进程 PID $($owner.ProcessId)（端口 $($owner.Port)）"
        Stop-Process -Id $owner.ProcessId -Force -ErrorAction Stop
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $remaining = @(Get-ListeningOwners -Ports @($ExpectedPorts.Values))
    } while ($remaining.Count -gt 0 -and [DateTime]::UtcNow -lt $deadline)
    if ($remaining.Count -gt 0) {
        Fail "旧服务仍占用端口：$($remaining.Port -join ', ')"
    }
}

function Wait-TcpPort([int]$Port, [DateTime]$Deadline) {
    do {
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $task = $client.ConnectAsync('127.0.0.1', $Port)
            if ($task.Wait(500) -and $client.Connected) {
                $client.Dispose()
                return $true
            }
            $client.Dispose()
        } catch {
            # Continue until the shared deadline.
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    return $false
}

function Wait-HttpResponse([string]$Uri, [DateTime]$Deadline) {
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -Headers @{ 'Cache-Control' = 'no-cache' } -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return $response
            }
        } catch {
            # A listening socket can precede HTTP readiness by a few seconds.
            # Keep the same bounded launch deadline and never turn a transient
            # connection refusal into a false deployment failure.
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    return $null
}

try {
    Write-Step '检查源码与依赖'
    Set-Location -LiteralPath $RepoRoot
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        Fail "缺少仓库虚拟环境：$Python。请先运行 uv sync。"
    }
    foreach ($command in @('git', 'node', 'npm', 'uv')) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
            Fail "PATH 中找不到 $command。"
        }
    }
    $npmCommandInfo = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
    if ($null -eq $npmCommandInfo) {
        $npmCommandInfo = Get-Command 'npm' -ErrorAction Stop
    }
    $NpmCommand = $npmCommandInfo.Source
    $ChromeExecutable = $null
    if (-not $NoBrowser) {
        $ChromeExecutable = Get-ChromeExecutable
        Write-Pass "隔离浏览器将使用 Google Chrome：$ChromeExecutable"
    }
    & $Python -c "import openjiuwen.symphony, yaml; print('runtime-imports-ok')" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail 'Python 环境不能导入 openjiuwen.symphony/yaml；请重新运行 uv sync。'
    }
    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $ExpectedBranch) {
        Fail "当前分支是 '$branch'，Demo 要求 '$ExpectedBranch'。"
    }
    $head = (& git rev-parse --short=10 HEAD).Trim()
    Write-Pass "源码分支 $branch，HEAD $head"
    $sourceDirty = @(& git status --short)
    if ($sourceDirty.Count -gt 0) {
        if ($RuntimeProfile -eq 'formal-web-validation') {
            Fail "Formal Web 验证要求干净源码；当前有 $($sourceDirty.Count) 项未提交修改。请先完成审查、测试和提交。"
        }
        Write-Warn "源码工作区存在 $($sourceDirty.Count) 项未提交修改；脚本会按当前源码构建，不会提交或覆盖它们。"
    }
    $l0RunLabelsPath = $null
    $l0ConfigurationSha256 = $null
    if ($L0Measurement) {
        $l0LogsRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'logs'))
        if ($RuntimeProfile -ne 'formal-web-validation') {
            Fail 'L0 物理采集只允许 formal-web-validation profile。'
        }
        if ($NoBrowser) {
            Fail 'L0 物理采集需要隔离 Chrome，不能同时使用 -NoBrowser。'
        }
        if (
            [string]::IsNullOrWhiteSpace($L0EnvironmentRef) -or
            $L0EnvironmentRef -notmatch '^[a-z0-9][a-z0-9._-]{0,63}$'
        ) {
            Fail 'L0 物理采集需要显式、安全的 -L0EnvironmentRef（例如 lab-a-room-1）。'
        }
        if ([string]::IsNullOrWhiteSpace($L0MeasurementDirectory)) {
            $L0MeasurementDirectory = Join-Path $l0LogsRoot (
                'l0-physical-{0}' -f (Get-Date -Format 'yyyyMMdd-HHmmss')
            )
        } elseif (-not [System.IO.Path]::IsPathRooted($L0MeasurementDirectory)) {
            $L0MeasurementDirectory = Join-Path $l0LogsRoot $L0MeasurementDirectory
        }
        $L0MeasurementDirectory = [System.IO.Path]::GetFullPath($L0MeasurementDirectory)
        $repoPrefix = $RepoRoot.TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        ) + [System.IO.Path]::DirectorySeparatorChar
        $logsPrefix = $l0LogsRoot.TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        ) + [System.IO.Path]::DirectorySeparatorChar
        $insideRepo = (
            $L0MeasurementDirectory -ieq $RepoRoot -or
            $L0MeasurementDirectory.StartsWith(
                $repoPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        )
        $insideIgnoredLogs = (
            $L0MeasurementDirectory -ieq $l0LogsRoot -or
            $L0MeasurementDirectory.StartsWith(
                $logsPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        )
        if ($insideRepo -and -not $insideIgnoredLogs) {
            Fail '仓库内的 L0 证据目录必须位于已忽略的 logs 目录；也可使用仓库外的绝对路径。'
        }
        if (Test-Path -LiteralPath $L0MeasurementDirectory) {
            $existingEvidence = @(Get-ChildItem -LiteralPath $L0MeasurementDirectory -Force)
            if ($existingEvidence.Count -gt 0) {
                Fail "L0 采集目录必须为空或不存在：$L0MeasurementDirectory"
            }
        } else {
            New-Item -ItemType Directory -Path $L0MeasurementDirectory | Out-Null
        }
        $l0RunLabelsPath = Join-Path $L0MeasurementDirectory 'run-labels.json'
        Write-Pass "L0 内容无关证据目录已隔离：$L0MeasurementDirectory"
    }

    # Keep the machine selection at one stable path so a non-default data
    # directory can still be discovered by the next no-argument launch.
    $demoConfigName = if ($RuntimeProfile -eq 'formal-web-validation') {
        'live-voice-formal-web-validation.json'
    } else {
        'live-voice-demo.json'
    }
    $DemoConfigPath = Join-Path $env:USERPROFILE ".jiuwenswarm\config\$demoConfigName"
    $savedConfig = $null
    if (Test-Path -LiteralPath $DemoConfigPath -PathType Leaf) {
        $savedConfig = Get-Content -Raw -LiteralPath $DemoConfigPath -Encoding UTF8 | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace($DataDir) -and $null -ne $savedConfig.data_dir) {
            $DataDir = [string]$savedConfig.data_dir
        }
        if ([string]::IsNullOrWhiteSpace($ProjectPath) -and $null -ne $savedConfig.project_path) {
            $ProjectPath = [string]$savedConfig.project_path
        }
        if ([string]::IsNullOrWhiteSpace($ProjectId) -and $null -ne $savedConfig.project_id) {
            $ProjectId = [string]$savedConfig.project_id
        }
    }
    if ([string]::IsNullOrWhiteSpace($DataDir)) {
        $DataDir = Join-Path $env:USERPROFILE '.jiuwenswarm'
    }
    $DataDir = Get-CanonicalPath $DataDir
    $PrivateEnvPath = Join-Path $DataDir 'config\.env'
    $ConfigYamlPath = Join-Path $DataDir 'config\config.yaml'
    $ProjectsPath = Join-Path $DataDir 'agent\projects.json'
    foreach ($requiredPath in @($PrivateEnvPath, $ConfigYamlPath, $ProjectsPath)) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            Fail "数据目录不是已配置的 JiuwenSwarm 环境，缺少：$requiredPath"
        }
    }

    if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
        Fail "未指定 Demo 项目。首次运行请传入 -ProjectPath '<可丢弃 Git 项目>' -SaveConfiguration。"
    }
    $ProjectPath = Get-CanonicalPath $ProjectPath

    $projectsDocument = Get-Content -Raw -LiteralPath $ProjectsPath -Encoding UTF8 | ConvertFrom-Json
    $registeredProjects = @($projectsDocument.projects)
    $matches = @($registeredProjects | Where-Object {
        try { (Get-CanonicalPath ([string]$_.project_dir)) -ieq $ProjectPath } catch { $false }
    })
    if ($matches.Count -ne 1) {
        Fail "Demo 项目没有以唯一记录注册到 $ProjectsPath：$ProjectPath"
    }
    $registered = $matches[0]
    if (-not [string]::IsNullOrWhiteSpace($ProjectId) -and [string]$registered.project_id -ne $ProjectId) {
        Fail "项目 ID 不匹配：配置为 '$ProjectId'，注册表为 '$($registered.project_id)'。"
    }
    $ProjectId = [string]$registered.project_id
    if ([string]::IsNullOrWhiteSpace($ProjectId)) {
        Fail '注册项目缺少 project_id。'
    }

    $gitRoot = (@(Invoke-Git -Arguments @('-C', $ProjectPath, 'rev-parse', '--show-toplevel')))[0].Trim()
    if ((Get-CanonicalPath $gitRoot) -ine $ProjectPath) {
        Fail "项目路径必须是 Git 根目录；实际根目录为：$gitRoot"
    }
    $remotes = @(@(Invoke-Git -Arguments @('-C', $ProjectPath, 'remote')) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($remotes.Count -gt 0) {
        Fail "Demo 项目存在 Git remote（$($remotes -join ', ')）；为避免误改远端项目，脚本拒绝启动。"
    }
    if ($RuntimeProfile -eq 'hands-free-demo') {
        foreach ($fileName in $ExpectedOrderInputs) {
            if (-not (Test-Path -LiteralPath (Join-Path $ProjectPath $fileName) -PathType Leaf)) {
                Fail "Demo 订单输入不完整，缺少：$fileName"
            }
        }
    }
    $projectStatus = @(@(Invoke-Git -Arguments @('-C', $ProjectPath, '-c', 'core.quotepath=false', 'status', '--porcelain')) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($projectStatus.Count -gt 0 -and -not $AllowDirtyProject) {
        if ($RuntimeProfile -eq 'formal-web-validation') {
            Fail "Formal Web 验证项目必须干净。请先清理，或在明确接受基线时传入 -AllowDirtyProject。"
        } else {
            $unexpected = @($projectStatus | Where-Object {
                if ($_ -notmatch '^\?\?\s+(.+)$') { return $true }
                return $ExpectedOrderInputs -notcontains $Matches[1]
            })
            if ($unexpected.Count -gt 0) {
                Fail "Demo 项目含有订单输入以外的修改。请先清理，或在明确接受基线时传入 -AllowDirtyProject。"
            }
            Write-Warn 'Demo 项目仅有 7 份预期的未跟踪订单输入；它们将作为本次只读输入基线。'
        }
    } elseif ($projectStatus.Count -gt 0) {
        Write-Warn "已按 -AllowDirtyProject 接受 $($projectStatus.Count) 项现有项目变化。"
    } else {
        Write-Pass "$RuntimeProfileLabel Git 项目干净且无 remote"
    }
    if ($L0Measurement -and $projectStatus.Count -gt 0) {
        Fail 'L0 物理采集要求项目精确绑定到干净 revision；-AllowDirtyProject 不能放宽该证据边界。'
    }
    $projectRevision = (@(
        Invoke-Git -Arguments @('-C', $ProjectPath, 'rev-parse', 'HEAD')
    ))[0].Trim().ToLowerInvariant()
    if ($projectRevision -notmatch '^[0-9a-f]{40}$') {
        Fail '无法取得项目的精确 Git revision。'
    }
    Write-Pass "项目注册与 P3 绑定一致（$ProjectId）"

    if ($SaveConfiguration) {
        $configDirectory = Split-Path -Parent $DemoConfigPath
        New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
        [ordered]@{
            schema_version = 1
            project_path   = $ProjectPath
            project_id     = $ProjectId
            data_dir       = $DataDir
        } | ConvertTo-Json | Set-Content -LiteralPath $DemoConfigPath -Encoding UTF8
        Write-Pass "已保存无密钥的机器私有 Demo 选择：$DemoConfigPath"
    }

    Write-Step '检查 Agent、语言与私有 Speech 配置'
    $configProbe = & $Python -c "import json,yaml,pathlib,sys; p=pathlib.Path(sys.argv[1]); d=yaml.safe_load(p.read_text(encoding='utf-8')) or {}; c=d.get('channels') or {}; x=sorted(k for k,v in c.items() if k not in {'web','tui'} and isinstance(v,dict) and v.get('enabled') is True); print(json.dumps({'language':d.get('preferred_language'),'models':bool((d.get('models') or {}).get('defaults')),'leader':bool((d.get('agents') or {}).get('agent_leader')),'external_channels':x}))" $ConfigYamlPath
    if ($LASTEXITCODE -ne 0) { Fail '无法解析 JiuwenSwarm config.yaml。' }
    $configFacts = $configProbe | ConvertFrom-Json
    if ($configFacts.language -ne 'zh') { Fail "preferred_language 必须为 zh，当前为 '$($configFacts.language)'。" }
    if (-not $configFacts.models -or -not $configFacts.leader) { Fail 'Agent 默认模型或 agent_leader 配置缺失。' }
    $enabledExternalChannels = @($configFacts.external_channels)
    if ($enabledExternalChannels.Count -gt 0) {
        Fail "受控 Live Voice 验证禁止启用无关外部 channel：$($enabledExternalChannels -join ', ')。请先在隔离数据配置中关闭。"
    }
    # This launcher is intentionally pinned to the official OpenAI Speech
    # origin below. The runtime requires an explicit provider label as well;
    # without it both Streaming and Batch fail closed as unavailable even when
    # the key, base URL and models are otherwise valid.
    [Environment]::SetEnvironmentVariable('LIVE_VOICE_SPEECH_PROVIDER', 'openai', 'Process')
    Import-PrivateValue -Name 'API_KEY' -PrivateEnvPath $PrivateEnvPath -Required | Out-Null
    $speechKey = Import-PrivateValue -Name 'LIVE_VOICE_SPEECH_API_KEY' -PrivateEnvPath $PrivateEnvPath -Required
    $speechBase = Import-PrivateValue -Name 'LIVE_VOICE_SPEECH_API_BASE' -PrivateEnvPath $PrivateEnvPath -Required
    $sttModel = Import-PrivateValue -Name 'LIVE_VOICE_SPEECH_STT_MODEL' -PrivateEnvPath $PrivateEnvPath -Required
    $ttsModel = Import-PrivateValue -Name 'LIVE_VOICE_SPEECH_TTS_MODEL' -PrivateEnvPath $PrivateEnvPath -Required
    if ($speechKey.Length -lt 16) { Fail 'LIVE_VOICE_SPEECH_API_KEY 看起来无效。' }
    if ($speechBase.TrimEnd('/') -ne 'https://api.openai.com/v1') { Fail 'Demo 要求 LIVE_VOICE_SPEECH_API_BASE=https://api.openai.com/v1。' }
    if ($sttModel -ne 'gpt-4o-mini-transcribe-2025-12-15') { Fail 'STT 模型不是已验证的 Demo 模型。' }
    if ($ttsModel -ne 'gpt-4o-mini-tts-2025-12-15') { Fail 'TTS 模型不是已验证的 Demo 模型。' }
    if ($L0Measurement) {
        $agentConfigurationSha256 = (
            Get-FileHash -LiteralPath $ConfigYamlPath -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        $l0ConfigurationFacts = [ordered]@{
            runtime_profile = $RuntimeProfile
            executor_profile = $ExecutorProfile
            agent_configuration_sha256 = $agentConfigurationSha256
            project = [ordered]@{
                project_id = $ProjectId
                revision = $projectRevision
            }
            speech = [ordered]@{
                provider = 'openai'
                api_base = $speechBase.TrimEnd('/')
                stt_model = $sttModel
                tts_model = $ttsModel
                tts_voice = 'marin'
            }
        } | ConvertTo-Json -Compress -Depth 10
        $l0ConfigurationHasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            $l0ConfigurationBytes = [System.Text.Encoding]::UTF8.GetBytes(
                $l0ConfigurationFacts
            )
            $l0ConfigurationSha256 = [System.BitConverter]::ToString(
                $l0ConfigurationHasher.ComputeHash($l0ConfigurationBytes)
            ).Replace('-', '').ToLowerInvariant()
        } finally {
            $l0ConfigurationHasher.Dispose()
        }
    }
    [Environment]::SetEnvironmentVariable('LIVE_VOICE_SPEECH_TTS_VOICE', 'marin', 'Process')
    [Environment]::SetEnvironmentVariable('LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED', '1', 'Process')
    [Environment]::SetEnvironmentVariable('LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED', '1', 'Process')
    $speechProbeJson = & $Python -c "import asyncio,json; from jiuwenswarm.server.live_voice.batch_speech import create_environment_batch_speech_provider; from jiuwenswarm.server.live_voice.openai_streaming_speech import select_environment_streaming_speech; b=create_environment_batch_speech_provider().capability(); s=asyncio.run(select_environment_streaming_speech(batch_available=b.available)); print(json.dumps({'batch':b.available,'streaming':s.tier.value == 'streaming' and s.provider is not None}))"
    if ($LASTEXITCODE -ne 0) { Fail '无法执行正式 Speech Provider 可用性探针。' }
    $speechProbe = $speechProbeJson | ConvertFrom-Json
    if ($speechProbe.batch -ne $true -or $speechProbe.streaming -ne $true) {
        Fail '正式 Streaming/Batch Speech Provider 未就绪。'
    }
    Write-Pass '中文 Agent、OpenAI Speech、STT/TTS 模型和 TTS voice 已就绪；无关外部 channel 已关闭（私密值未输出）'

    Write-Step '设置完整免手 Demo 能力与安全边界'
    $taskStore = Join-Path $DataDir 'live_voice\p3alpha\formal_tasks.sqlite3'
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskStore) -Force | Out-Null
    $tokenBytes = [byte[]]::new(32)
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($tokenBytes)
    } finally {
        $random.Dispose()
    }
    $authToken = [Convert]::ToBase64String($tokenBytes)
    $expiry = [DateTimeOffset]::UtcNow.AddHours(12).ToString('o')
    $featureEnvironment = [ordered]@{
        JIUWENSWARM_LIVE_VOICE_RUNTIME_PROFILE                    = $RuntimeProfile
        JIUWENSWARM_DATA_DIR                                      = $DataDir
        JIUWENSWARM_ENABLE_ORIGIN_CHECK                           = '1'
        JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS                       = 'localhost,127.0.0.1'
        JIUWENSWARM_LIVE_VOICE_P3_ENABLED                         = '1'
        JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN                      = $authToken
        JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID                    = 'local-live-voice-demo'
        JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS                     = $ProjectId
        JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT                 = $expiry
        JIUWENSWARM_LIVE_VOICE_P3_DATABASE                        = $taskStore
        JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE                = $ExecutorProfile
        JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED        = '1'
        JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED                 = '1'
        JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED            = '1'
        JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED        = '1'
        JIUWENSWARM_LIVE_VOICE_CRITICAL_INPUT_ENABLED             = '1'
        # Demo-only runtime exceptions. Keep these out of every frontend
        # build profile and make the controlled launcher own them explicitly.
        JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED = '1'
        JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED = '1'
        JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED            = '1'
        JIUWENSWARM_LIVE_VOICE_END_OF_TURN_ENABLED                = '1'
        JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED       = '1'
        LIVE_VOICE_SPEECH_PROVIDER                               = 'openai'
        LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED                    = '1'
        LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED                = '1'
        PYTHONUTF8                                                = '1'
        PYTHONIOENCODING                                          = 'utf-8'
    }
    foreach ($entry in $featureEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable([string]$entry.Key, [string]$entry.Value, 'Process')
    }
    if ($L0Measurement) {
        [Environment]::SetEnvironmentVariable(
            'JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_DIR',
            $L0MeasurementDirectory,
            'Process'
        )
        [Environment]::SetEnvironmentVariable(
            'JIUWENSWARM_LIVE_VOICE_L0_MEASUREMENT_RUN_LABELS_FILE',
            $l0RunLabelsPath,
            'Process'
        )
    }
    foreach ($entry in $ExpectedPorts.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable([string]$entry.Key, [string]$entry.Value, 'Process')
    }
    # InstanceManager resolves its default port group from the JIUWENSWARM_*
    # names before it writes the child-process FRONTEND/WEB/GATEWAY variables.
    # Set both layers so the launcher cannot silently fall back to a different
    # frontend port than the selected controlled profile.
    [Environment]::SetEnvironmentVariable('JIUWENSWARM_FRONTEND_PORT', [string]$FrontendPort, 'Process')
    [Environment]::SetEnvironmentVariable('JIUWENSWARM_AGENT_SERVER_PORT', '18092', 'Process')
    [Environment]::SetEnvironmentVariable('JIUWENSWARM_WEB_PORT', '19000', 'Process')
    [Environment]::SetEnvironmentVariable('JIUWENSWARM_GATEWAY_PORT', '19001', 'Process')
    foreach ($frontendOverride in @(
        'VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB',
        'VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1',
        'VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION',
        'VITE_FEATURE_LIVE_VOICE_TASK_DEMO',
        'VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH'
    )) {
        # Vite gives an existing process variable precedence over mode files.
        # SetEnvironmentVariable(..., $null, 'Process') becomes an empty value
        # in this PowerShell/.NET runtime, which would still override the
        # profile. Remove the process entry itself so .env.live-voice can load.
        Remove-Item -LiteralPath "Env:\$frontendOverride" -ErrorAction SilentlyContinue
    }
    $requiredRuntimeFlags = @(
        'JIUWENSWARM_ENABLE_ORIGIN_CHECK',
        'JIUWENSWARM_LIVE_VOICE_P3_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_CRITICAL_INPUT_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_END_OF_TURN_ENABLED',
        'JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED',
        'LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED',
        'LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED'
    )
    foreach ($requiredRuntimeFlag in $requiredRuntimeFlags) {
        if ([Environment]::GetEnvironmentVariable($requiredRuntimeFlag, 'Process') -ne '1') {
            Fail "受控运行配置缺少必需开关：$requiredRuntimeFlag"
        }
    }
    if ([Environment]::GetEnvironmentVariable('JIUWENSWARM_LIVE_VOICE_RUNTIME_PROFILE', 'Process') -ne $RuntimeProfile) {
        Fail '受控运行配置的 profile 身份不一致。'
    }
    if ([Environment]::GetEnvironmentVariable('JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE', 'Process') -ne $ExecutorProfile) {
        Fail '受控运行配置必须选择精确的 Direct D2 Executor profile。'
    }
    Write-Pass "$RuntimeProfileLabel 的 P1/P2/P3、统一语义、Demo bypass、调整 checkpoint、Dedicated Media/EOT、Origin 与 Task Store 已完整绑定"

    if (-not (Test-Path -LiteralPath $ProductionFrontendEnv -PathType Leaf)) {
        Fail "缺少普通 production 前端开关文件：$ProductionFrontendEnv"
    }
    if (-not (Test-Path -LiteralPath $LiveVoiceFrontendEnv -PathType Leaf)) {
        Fail "缺少 Live Voice 前端构建配置：$LiveVoiceFrontendEnv"
    }
    $productionFrontendEnvText = Get-Content -Raw -LiteralPath $ProductionFrontendEnv -Encoding UTF8
    $liveVoiceFrontendEnvText = Get-Content -Raw -LiteralPath $LiveVoiceFrontendEnv -Encoding UTF8
    foreach ($requiredLine in @(
        'VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB=true',
        'VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1=true',
        'VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION=true'
    )) {
        if ($liveVoiceFrontendEnvText -notmatch "(?m)^$([regex]::Escape($requiredLine))\s*$") {
            Fail "Live Voice 构建配置缺少开关：$requiredLine"
        }
        $productionLine = $requiredLine -replace '=true$', '=false'
        if ($productionFrontendEnvText -notmatch "(?m)^$([regex]::Escape($productionLine))\s*$") {
            Fail "普通 production 构建必须关闭开关：$productionLine"
        }
    }
    Write-Pass '普通 production 保持 flag-off；显式 Live Voice 构建配置保持 flag-on'

    if ($PreflightOnly) {
        $owners = @(Get-ListeningOwners -Ports @($ExpectedPorts.Values))
        if ($owners.Count -gt 0) {
            Write-Warn "预检未改动进程；当前有 $($owners.Count) 个 Demo 端口监听记录。正式启动时使用 -RestartExisting。"
        }
        Write-Host "`n$RuntimeProfileLabel 预检完成：全部必需参数已校验；没有启动、停止或重启任何服务。" -ForegroundColor Green
        exit 0
    }

    Write-Step '处理旧服务并从最新源码构建'
    if (-not $NoBrowser) {
        Stop-ExistingIsolatedChrome -ChromeExecutable $ChromeExecutable
    }
    $owners = @(Get-ListeningOwners -Ports @($ExpectedPorts.Values))
    if ($owners.Count -gt 0) {
        if (-not $RestartExisting) {
            Fail "Demo 端口已被占用。请关闭旧服务，或重新运行并添加 -RestartExisting。"
        }
        Stop-ExistingDemoServices
    }
    Push-Location -LiteralPath $FrontendRoot
    try {
        & $NpmCommand install
        if ($LASTEXITCODE -ne 0) {
            Fail "前端依赖安装失败（exit=$LASTEXITCODE）。"
        }
        & $NpmCommand run build:live-voice
        if ($LASTEXITCODE -ne 0) {
            Fail "Live Voice 前端构建失败（exit=$LASTEXITCODE）。"
        }
    } finally {
        Pop-Location
    }
    & $Python -m jiuwenswarm.start_services debug --skip-build
    if ($LASTEXITCODE -ne 0) {
        Fail "JiuwenSwarm debug 启动失败（exit=$LASTEXITCODE）。"
    }

    Write-Step '验证实际部署，而不是只检查端口'
    $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
    foreach ($entry in $ExpectedPorts.GetEnumerator()) {
        if (-not (Wait-TcpPort -Port ([int]$entry.Value) -Deadline $deadline)) {
            Fail "$($entry.Key) 端口 $($entry.Value) 未在时限内就绪。"
        }
    }
    $indexUrl = "http://127.0.0.1:$FrontendPort/?live_voice_build_check=1"
    $indexResponse = Wait-HttpResponse -Uri $indexUrl -Deadline $deadline
    if ($null -eq $indexResponse) { Fail '前端 HTTP 未在启动时限内就绪。' }
    $assetMatch = [regex]::Match([string]$indexResponse.Content, 'src="([^"]*index-[^"]+\.js)"')
    if (-not $assetMatch.Success) { Fail '前端 index.html 没有引用 Live Voice profile bundle。' }
    $assetPath = $assetMatch.Groups[1].Value
    $bundleUrl = "http://127.0.0.1:$FrontendPort${assetPath}?live_voice_build_check=1"
    $bundle = Wait-HttpResponse -Uri $bundleUrl -Deadline $deadline
    if ($null -eq $bundle) { Fail 'Live Voice 前端 bundle 未在启动时限内就绪。' }
    if (-not ([string]$bundle.Content).Contains('live_voice.composition.unified.submit')) {
        Fail '实际提供的前端 bundle 不包含 live_voice.composition.unified.submit；拒绝进入 Demo。'
    }

    $statePath = Join-Path $RepoRoot 'logs\debug_service.json'
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { Fail '调试启动器没有写入服务状态。' }
    $state = Get-Content -Raw -LiteralPath $statePath -Encoding UTF8 | ConvertFrom-Json
    $logPath = [string]$state.log_file
    if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) { Fail '找不到服务启动日志。' }
    $logText = Get-Content -Raw -LiteralPath $logPath -Encoding UTF8
    if ($logText -notmatch '\[LiveVoiceP3\] authenticated formal route ready') { Fail 'P3 authenticated formal route 未就绪。' }
    if ($logText -notmatch '\[LiveVoiceProduct\] central composition registered; p2=True p3_text=True') { Fail 'Live Voice 产品组合未完整注册。' }
    if ($logText -match 'LiveVoice(P3|Product).*failed closed') { Fail '启动日志包含 Live Voice fail-closed 错误。' }
    Write-Pass "最新 Live Voice profile bundle 已加载（$assetPath）"
    Write-Pass 'P3 authenticated route 与 P2/P3 product composition 已就绪'
    Write-Pass '四个固定端口均已就绪；未发生静默端口漂移'

    $speechRoundTrip = 'not-required-for-this-profile'
    $gatewayClaimPolicy = 'not-required-for-this-profile'
    if ($RuntimeProfile -eq 'formal-web-validation') {
        if (-not (Test-Path -LiteralPath $FormalWebRuntimeProbe -PathType Leaf)) {
            Fail "缺少 Formal Web 运行探针：$FormalWebRuntimeProbe"
        }
        $probeOutput = @(& $Python $FormalWebRuntimeProbe)
        if ($LASTEXITCODE -ne 0) {
            Fail 'Formal Web 真实 Speech/receipt 运行探针失败。'
        }
        $probeLine = @($probeOutput | Where-Object { $_ -like 'FORMAL_WEB_RUNTIME_PROBE_RESULT *' })
        if ($probeLine.Count -ne 1) {
            Fail 'Formal Web 运行探针没有返回唯一的安全结果。'
        }
        $probeResult = $probeLine[0].Substring('FORMAL_WEB_RUNTIME_PROBE_RESULT '.Length) | ConvertFrom-Json
        if (
            $probeResult.provider_round_trip -ne 'passed' -or
            $probeResult.gateway_claim_policy -ne 'trusted_demo_bypass' -or
            $probeResult.identity_mismatch -ne 'rejected' -or
            $probeResult.forged_claim -ne 'rejected' -or
            $probeResult.business_effects -ne 0 -or
            $probeResult.audio_retained -ne $false -or
            $probeResult.transcript_retained -ne $false
        ) {
            Fail 'Formal Web 运行探针结果不满足安全合同。'
        }
        $speechRoundTrip = 'passed'
        $gatewayClaimPolicy = 'trusted_demo_bypass'
        Write-Pass '真实 Speech TTS→STT、critical receipt、身份错配拒绝和伪造 claim 拒绝均通过；业务副作用为 0'
    }

    $runtimeContractPath = Join-Path $RepoRoot 'logs\live_voice_runtime_contract.json'
    $validatedFlags = [ordered]@{}
    foreach ($requiredRuntimeFlag in $requiredRuntimeFlags) {
        $validatedFlags[$requiredRuntimeFlag] = $true
    }
    [ordered]@{
        schema_version            = 1
        runtime_profile           = $RuntimeProfile
        source_branch             = $branch
        source_head               = $head
        source_dirty_count        = $sourceDirty.Count
        data_directory_validated  = $true
        project_binding_validated = $true
        project_remote_count      = $remotes.Count
        ports                     = $ExpectedPorts
        required_flags            = $validatedFlags
        executor_profile          = $ExecutorProfile
        credential                = 'ephemeral-process-only'
        speech_provider           = 'openai'
        speech_round_trip         = $speechRoundTrip
        gateway_claim_policy      = $gatewayClaimPolicy
        bundle_validated          = $true
        backend_routes_validated  = $true
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runtimeContractPath -Encoding UTF8
    Write-Pass "已写入不含密钥的运行合同：$runtimeContractPath"

    $isolatedChromeProfile = $null
    if (-not $NoBrowser) {
        Write-Step '打开全新隔离 Chrome'
        $browserUrl = "http://localhost:$FrontendPort"
        $remoteDebuggingPort = 0
        if ($L0Measurement) {
            $browserUrl += '?live_voice_l0_measurement=1'
            $remoteDebuggingPort = $L0MeasurementPort
        }
        $isolatedChromeProfile = Start-IsolatedChrome `
            -ChromeExecutable $ChromeExecutable `
            -Url $browserUrl `
            -RemoteDebuggingPort $remoteDebuggingPort
        Write-Pass "隔离 Chrome 已打开：$isolatedChromeProfile"
        if ($L0Measurement) {
            [ordered]@{
                schema_version      = 'live-voice.l0-browser-session.v4'
                source_head         = (& git rev-parse HEAD).Trim()
                runtime_profile     = $RuntimeProfile
                evidence_directory = $L0MeasurementDirectory
                run_labels_file    = $l0RunLabelsPath
                browser_endpoint   = "http://127.0.0.1:$L0MeasurementPort"
                browser_page_origin = "http://localhost:$FrontendPort"
                temperature_epoch_id = ([guid]::NewGuid().ToString('N'))
                cold_sample_available = $true
                environment_ref     = $L0EnvironmentRef
                configuration_sha256 = $l0ConfigurationSha256
                physical_evidence  = 'pending-user-run'
                raw_audio_retained = $false
                transcript_retained = $false
            } | ConvertTo-Json | Set-Content `
                -LiteralPath (Join-Path $L0MeasurementDirectory 'browser-session.json') `
                -Encoding UTF8
            Write-Pass "L0 自动采集端点已就绪：127.0.0.1:$L0MeasurementPort"
        }
    }

    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host "  JiuwenSwarm Live Voice $RuntimeProfileLabel 已准备完成" -ForegroundColor Green
    Write-Host "  Web: http://localhost:$FrontendPort" -ForegroundColor White
    Write-Host "  Project: $ProjectPath" -ForegroundColor White
    Write-Host "  Log: $logPath" -ForegroundColor DarkGray
    if ($null -ne $isolatedChromeProfile) {
        Write-Host "  Isolated Chrome: $isolatedChromeProfile" -ForegroundColor DarkGray
    }
    if ($L0Measurement) {
        Write-Host "  L0 Evidence: $L0MeasurementDirectory" -ForegroundColor DarkGray
        Write-Host "  Capture: & '$Python' scripts\live_voice\l0_browser_capture.py --session '$L0MeasurementDirectory\browser-session.json'" -ForegroundColor Yellow
        Write-Host "  Cold shard: add --profile physical-formal-web-cold --temperature cold --successful-rounds 1 --scenario <case-id> --sample-index-start <unique-index>" -ForegroundColor Yellow
        Write-Host "  Cold aggregate: use --aggregate-cold, repeat --evidence-directory <cold-epoch-dir>, and set --output <report.json>" -ForegroundColor Yellow
    }
    Write-Host '  首次进入页面仍需由浏览器授予麦克风权限并选择该项目。' -ForegroundColor Yellow
    Write-Host '============================================================' -ForegroundColor Green
    exit 0
} catch {
    $failureLine = $_.InvocationInfo.ScriptLineNumber
    Write-Host "`n[Live Voice Demo 启动失败] $($_.Exception.Message)（脚本行 $failureLine）" -ForegroundColor Red
    Write-Host '没有输出任何密钥。修复上述单一问题后重新运行即可。' -ForegroundColor Yellow
    exit 1
}
