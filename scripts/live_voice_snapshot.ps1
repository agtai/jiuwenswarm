[CmdletBinding()]
param(
    [switch]$Remote,
    [switch]$DeepCandidates,
    [switch]$Json,
    [ValidateRange(1, 20)]
    [int]$CommitCount = 6
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$rootResult = @(& git rev-parse --show-toplevel 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Run this script from inside the JiuwenSwarm repository."
}
$repoRoot = [System.IO.Path]::GetFullPath([string]$rootResult[-1])

function Invoke-RepoGit {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $lines = @(& git -C $repoRoot @Arguments 2>&1 | ForEach-Object { [string]$_ })
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        $detail = $lines -join [Environment]::NewLine
        throw "git $($Arguments -join ' ') failed ($exitCode).`n$detail"
    }
    [pscustomobject]@{
        ExitCode = $exitCode
        Lines = $lines
    }
}

function Get-OneLine {
    param([Parameter(Mandatory = $true)]$Result)

    if ($Result.ExitCode -ne 0 -or $Result.Lines.Count -eq 0) {
        return $null
    }
    return [string]$Result.Lines[-1]
}

function Get-BranchStatus {
    $result = Invoke-RepoGit -Arguments @("status", "--porcelain=v2", "--branch", "--untracked-files=normal")
    $branchStatus = [ordered]@{
        Branch = "(detached)"
        Head = $null
        Upstream = $null
        Ahead = $null
        Behind = $null
        Dirty = @()
    }

    foreach ($line in $result.Lines) {
        if ($line -match '^# branch\.oid (?<value>.+)$') {
            $branchStatus.Head = $Matches.value
        }
        elseif ($line -match '^# branch\.head (?<value>.+)$') {
            $branchStatus.Branch = $Matches.value
        }
        elseif ($line -match '^# branch\.upstream (?<value>.+)$') {
            $branchStatus.Upstream = $Matches.value
        }
        elseif ($line -match '^# branch\.ab \+(?<ahead>\d+) -(?<behind>\d+)$') {
            $branchStatus.Ahead = [int]$Matches.ahead
            $branchStatus.Behind = [int]$Matches.behind
        }
        elseif ($line.StartsWith("? ")) {
            $branchStatus.Dirty += "?? $($line.Substring(2))"
        }
        elseif (-not $line.StartsWith("# ")) {
            $parts = $line -split "\s+", 9
            $branchStatus.Dirty += $(if ($parts.Count -ge 9) { "$($parts[1]) $($parts[8])" } else { $line })
        }
    }
    return [pscustomobject]$branchStatus
}

function Get-Worktrees {
    $result = Invoke-RepoGit -Arguments @("worktree", "list", "--porcelain")
    $items = @()
    $current = @{}

    foreach ($line in @($result.Lines) + "") {
        if ([string]::IsNullOrWhiteSpace($line)) {
            if ($current.ContainsKey("Path")) {
                $items += [pscustomobject]@{
                    path = $current.Path
                    head = $current.Head
                    branch = $current.Branch
                }
            }
            $current = @{}
            continue
        }
        if ($line.StartsWith("worktree ")) {
            $current.Path = $line.Substring(9)
        }
        elseif ($line.StartsWith("HEAD ")) {
            $current.Head = $line.Substring(5, [Math]::Min(8, $line.Length - 5))
        }
        elseif ($line.StartsWith("branch refs/heads/")) {
            $current.Branch = $line.Substring(18)
        }
        elseif ($line -eq "detached") {
            $current.Branch = "(detached)"
        }
    }
    return @($items)
}

$statusPath = Join-Path $repoRoot "live-voice\STATUS.md"
$decisionsPath = Join-Path $repoRoot "live-voice\decisions\DECISIONS.md"
if (-not (Test-Path -LiteralPath $statusPath)) {
    throw "live-voice/STATUS.md was not found under $repoRoot."
}

$statusLines = @(Get-Content -Encoding UTF8 -LiteralPath $statusPath)
$statusText = $statusLines -join "`n"
$capsuleLines = @()
$inCapsule = $false
foreach ($line in $statusLines) {
    if ($line -eq "## Resume capsule") {
        $inCapsule = $true
        continue
    }
    if ($inCapsule -and $line.StartsWith("## ")) {
        break
    }
    if ($inCapsule -and -not [string]::IsNullOrWhiteSpace($line)) {
        $capsuleLines += [string]$line
    }
}

$branchStatus = Get-BranchStatus
$branch = $branchStatus.Branch
$head = $branchStatus.Head
$upstream = $branchStatus.Upstream

if ($Remote) {
    if (-not $upstream -or $upstream.IndexOf("/") -lt 1) {
        throw "Remote orientation requires a configured upstream."
    }
    $separator = $upstream.IndexOf("/")
    $remoteName = $upstream.Substring(0, $separator)
    $remoteBranch = $upstream.Substring($separator + 1)
    $refspec = "+refs/heads/${remoteBranch}:refs/remotes/${upstream}"
    $null = Invoke-RepoGit -Arguments @("fetch", "--no-tags", $remoteName, $refspec)
    $branchStatus = Get-BranchStatus
}

$branch = $branchStatus.Branch
$head = $branchStatus.Head
$upstream = $branchStatus.Upstream
$ahead = $branchStatus.Ahead
$behind = $branchStatus.Behind
$dirtyLines = @($branchStatus.Dirty)
$dirtyShown = @($dirtyLines | Select-Object -First 40)
$recentCommits = @((Invoke-RepoGit -Arguments @("log", "-n", [string]$CommitCount, "--format=%h%x09%s")).Lines)
$worktrees = @(Get-Worktrees)

$codexBranches = @()
if ($DeepCandidates) {
    $branchRows = @((Invoke-RepoGit -Arguments @("for-each-ref", "--format=%(refname:short)%09%(objectname)", "refs/heads/codex")).Lines)
    $mergedCodexBranches = @{}
    foreach ($mergedBranch in @((Invoke-RepoGit -Arguments @("for-each-ref", "--merged=HEAD", "--format=%(refname:short)", "refs/heads/codex")).Lines)) {
        $mergedCodexBranches[$mergedBranch] = $true
    }
    foreach ($row in $branchRows) {
        if ([string]::IsNullOrWhiteSpace($row)) {
            continue
        }
        $columns = $row -split "`t", 2
        $candidateBranch = $columns[0]
        $candidateHead = $columns[1]
        $candidateDivergence = Get-OneLine (Invoke-RepoGit -Arguments @("rev-list", "--left-right", "--count", "HEAD...$candidateHead"))
        $candidateParts = $candidateDivergence -split "\s+"
        $headOnly = [int]$candidateParts[0]
        $branchOnly = [int]$candidateParts[1]
        $cherryLines = @((Invoke-RepoGit -Arguments @("cherry", "HEAD", $candidateHead)).Lines)
        $patchAhead = @($cherryLines | Where-Object { $_.StartsWith("+") }).Count
        $patchEquivalent = @($cherryLines | Where-Object { $_.StartsWith("-") }).Count
        $documented = $statusText.Contains($candidateHead) -or $statusText.Contains($candidateHead.Substring(0, 8))

        if ($mergedCodexBranches.ContainsKey($candidateBranch)) {
            $relation = "ancestor"
        }
        elseif ($patchAhead -eq 0 -and $patchEquivalent -gt 0) {
            $relation = "patch-equivalent"
        }
        elseif ($documented) {
            $relation = "documented-reference"
        }
        else {
            $relation = "not-ancestor"
        }

        $codexBranches += [pscustomobject]@{
            branch = $candidateBranch
            head = $candidateHead.Substring(0, 8)
            headOnly = $headOnly
            branchOnly = $branchOnly
            patchAhead = $patchAhead
            patchEquivalent = $patchEquivalent
            relationHint = $relation
        }
    }
}

$decisionHeadingCount = 0
$duplicateDecisionIds = @()
if (Test-Path -LiteralPath $decisionsPath) {
    $decisionText = Get-Content -Raw -Encoding UTF8 -LiteralPath $decisionsPath
    $decisionIds = @([regex]::Matches($decisionText, "(?m)^## (?<id>D-\d{3})\b") | ForEach-Object { $_.Groups["id"].Value })
    $decisionHeadingCount = $decisionIds.Count
    $duplicateDecisionIds = @($decisionIds | Group-Object | Where-Object { $_.Count -gt 1 } | ForEach-Object { $_.Name })
}

$verifiedCodeBase = $null
$verifiedMatch = [regex]::Match($statusText, 'Verified code base: `(?<sha>[0-9a-fA-F]{7,40})`')
if ($verifiedMatch.Success) {
    $verifiedCodeBase = $verifiedMatch.Groups["sha"].Value
}
$changedSinceVerified = @()
$changedSinceVerifiedCount = $null
$verifiedCodeBaseValid = $false
if ($verifiedCodeBase) {
    if ($head.StartsWith($verifiedCodeBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        $verifiedCodeBaseValid = $true
        $changedSinceVerifiedCount = 0
    }
    else {
        $changedResult = Invoke-RepoGit -Arguments @("diff", "--name-only", "$verifiedCodeBase..HEAD") -AllowFailure
        if ($changedResult.ExitCode -eq 0) {
            $verifiedCodeBaseValid = $true
            $changedSinceVerifiedAll = @($changedResult.Lines)
            $changedSinceVerifiedCount = $changedSinceVerifiedAll.Count
            $changedSinceVerified = @($changedSinceVerifiedAll | Select-Object -First 40)
        }
    }
}

$snapshot = [ordered]@{
    generatedAt = [DateTimeOffset]::UtcNow.ToString("o")
    mode = $(if ($Remote) { "remote-orientation" } else { "local-orientation" })
    repository = $repoRoot
    git = [ordered]@{
        branch = $branch
        head = $head
        upstream = $upstream
        ahead = $ahead
        behind = $behind
        dirtyCount = $dirtyLines.Count
        dirty = $dirtyShown
        dirtyTruncated = ($dirtyLines.Count -gt $dirtyShown.Count)
    }
    resumeCapsule = $capsuleLines
    recentCommits = $recentCommits
    worktrees = $worktrees
    codexBranches = $codexBranches
    decisions = [ordered]@{
        canonicalHeadingCount = $decisionHeadingCount
        duplicateCanonicalIds = $duplicateDecisionIds
    }
    machineCapabilities = [ordered]@{
        repositoryVenv = Test-Path -LiteralPath (Join-Path $repoRoot ".venv\Scripts\python.exe")
        frontendNodeModules = Test-Path -LiteralPath (Join-Path $repoRoot "jiuwenswarm\channels\web\frontend\node_modules")
        nodeOnPath = $null -ne (Get-Command node -ErrorAction SilentlyContinue)
        privateRuntimeConfiguration = "not-inspected"
    }
    verifiedCodeBase = $verifiedCodeBase
    verifiedCodeBaseValid = $verifiedCodeBaseValid
    changedSinceVerifiedCount = $changedSinceVerifiedCount
    changedSinceVerified = $changedSinceVerified
    changedSinceVerifiedTruncated = ($changedSinceVerifiedCount -gt $changedSinceVerified.Count)
}

if ($Json) {
    $snapshot | ConvertTo-Json -Depth 6
    exit 0
}

Write-Output "Live Voice snapshot [$($snapshot.mode)]"
Write-Output "repo: $repoRoot"
Write-Output "git: $branch $($head.Substring(0, 8)) -> $upstream (ahead=$ahead behind=$behind dirty=$($dirtyLines.Count))"
foreach ($line in $dirtyShown) {
    Write-Output "  dirty $line"
}
if ($dirtyLines.Count -gt $dirtyShown.Count) {
    Write-Output "  dirty ... $($dirtyLines.Count - $dirtyShown.Count) more"
}

Write-Output "resume capsule:"
foreach ($line in $capsuleLines) {
    Write-Output "  $line"
}

Write-Output "recent commits:"
foreach ($line in $recentCommits) {
    Write-Output "  $line"
}

Write-Output "worktrees:"
foreach ($item in $worktrees) {
    Write-Output "  $($item.branch) $($item.head) $($item.path)"
}

if ($DeepCandidates) {
    Write-Output "codex branches (relation hints are not integration authority):"
    foreach ($item in $codexBranches) {
        Write-Output "  $($item.branch) $($item.head) head-only=$($item.headOnly) branch-only=$($item.branchOnly) patch+=$($item.patchAhead) patch~=$($item.patchEquivalent) $($item.relationHint)"
    }
}

$duplicateText = if ($duplicateDecisionIds.Count -eq 0) { "none" } else { $duplicateDecisionIds -join "," }
Write-Output "decisions: headings=$decisionHeadingCount duplicate-canonical-ids=$duplicateText"
Write-Output "machine: repo-venv=$($snapshot.machineCapabilities.repositoryVenv) frontend-node-modules=$($snapshot.machineCapabilities.frontendNodeModules) node=$($snapshot.machineCapabilities.nodeOnPath) private-runtime=not-inspected"
Write-Output "verified base: $verifiedCodeBase valid=$verifiedCodeBaseValid; committed files since base=$changedSinceVerifiedCount"
foreach ($path in $changedSinceVerified) {
    Write-Output "  changed $path"
}
if ($changedSinceVerifiedCount -gt $changedSinceVerified.Count) {
    Write-Output "  changed ... $($changedSinceVerifiedCount - $changedSinceVerified.Count) more"
}
