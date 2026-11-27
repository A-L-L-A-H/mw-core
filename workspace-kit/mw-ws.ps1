[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'pull', 'sync', 'test', 'ci', 'health', 'doctor', 'drift', 'lint')]
    [string]$Command = 'status',

    [Parameter(Position = 1)]
    [string]$Filter = '',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$WorkspaceRoot = $PSScriptRoot
$ManifestPath = Join-Path $WorkspaceRoot 'workspace.json'

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Missing workspace manifest: $ManifestPath"
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$Repos = @($Manifest.repositories)
if ($Filter) {
    $Repos = @($Repos | Where-Object { $_.name -like "*$Filter*" -or $_.profile -eq $Filter -or $_.stack -like "*$Filter*" })
}

switch ($Command) {
    'status' {
        $rows = foreach ($repo in $Repos) {
            $repoDir = Join-Path $WorkspaceRoot $repo.name
            if (-not (Test-Path -LiteralPath (Join-Path $repoDir '.git'))) {
                [PSCustomObject]@{
                    Repo    = $repo.name
                    Branch  = 'MISSING'
                    Head    = '-'
                    Dirty   = '-'
                    Profile = $repo.profile
                    Port    = if ($null -ne $repo.port) { $repo.port } else { '-' }
                }
                continue
            }
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $branch = (git -C $repoDir symbolic-ref --short HEAD 2>$null)
                if (-not $branch) { $branch = (git -C $repoDir rev-parse --abbrev-ref HEAD 2>$null) }
                $head = (git -C $repoDir rev-parse --short HEAD 2>$null)
                $porcelain = @(git -C $repoDir status --porcelain 2>$null | Where-Object { $_ -ne '' })
            } finally {
                $ErrorActionPreference = $prevEap
            }
            [PSCustomObject]@{
                Repo    = $repo.name
                Branch  = if ($branch) { $branch } else { 'UNBORN' }
                Head    = if ($head) { $head } else { 'unborn' }
                Dirty   = $porcelain.Count
                Profile = $repo.profile
                Port    = if ($null -ne $repo.port) { $repo.port } else { '-' }
            }
        }
        $rows | Format-Table -AutoSize
    }

    'pull' {
        foreach ($repo in $Repos) {
            $repoDir = Join-Path $WorkspaceRoot $repo.name
            if (-not (Test-Path -LiteralPath (Join-Path $repoDir '.git'))) {
                Write-Host "[SKIP] $($repo.name) not cloned (run '.\mw-ws.ps1 sync')" -ForegroundColor Yellow
                continue
            }
            Write-Host "[PULL] $($repo.name)" -ForegroundColor Cyan
            git -C $repoDir pull --ff-only
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[WARN] $($repo.name) pull --ff-only exited $LASTEXITCODE" -ForegroundColor Red
            }
        }
    }

    'sync' {
        foreach ($repo in $Repos) {
            $repoDir = Join-Path $WorkspaceRoot $repo.name
            if (Test-Path -LiteralPath (Join-Path $repoDir '.git')) {
                Write-Host "[OK]   $($repo.name) already present" -ForegroundColor Green
                continue
            }
            $remoteUrl = "https://github.com/$($repo.github).git"
            Write-Host "[CLONE] $($repo.name) <- $remoteUrl" -ForegroundColor Cyan
            git clone $remoteUrl $repoDir
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[FAIL] $($repo.name) clone exited $LASTEXITCODE" -ForegroundColor Red
            }
        }
    }

    'test' {
        $failed = @()
        foreach ($repo in $Repos) {
            $repoDir = Join-Path $WorkspaceRoot $repo.name
            if (-not (Test-Path -LiteralPath $repoDir)) {
                Write-Host "[SKIP] $($repo.name) not cloned" -ForegroundColor Yellow
                continue
            }
            if (-not $repo.testCmd) {
                Write-Host "[SKIP] $($repo.name) has no testCmd" -ForegroundColor Yellow
                continue
            }
            Write-Host "[TEST] $($repo.name): $($repo.testCmd)" -ForegroundColor Cyan
            Push-Location $repoDir
            $prevCargoTarget = $env:CARGO_TARGET_DIR
            try {
                if ($repo.stack -eq 'Rust') {
                    $env:CARGO_TARGET_DIR = Join-Path $WorkspaceRoot "cargo-target-$($repo.name)"
                }
                Invoke-Expression $repo.testCmd
                if ($LASTEXITCODE -ne 0) {
                    $failed += $repo.name
                    Write-Host "[FAIL] $($repo.name) exited $LASTEXITCODE" -ForegroundColor Red
                } else {
                    Write-Host "[PASS] $($repo.name)" -ForegroundColor Green
                }
            } finally {
                if ($null -eq $prevCargoTarget) {
                    Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
                } else {
                    $env:CARGO_TARGET_DIR = $prevCargoTarget
                }
                Pop-Location
            }
        }
        if ($failed.Count -gt 0) {
            Write-Host "Failed repos: $($failed -join ', ')" -ForegroundColor Red
            exit 1
        }
    }

    'ci' {
        if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
            throw 'GitHub CLI (gh) is required for the ci subcommand.'
        }
        $rows = foreach ($repo in $Repos) {
            $raw = gh run list -R $repo.github -L 1 --json status,conclusion,headBranch,displayTitle,createdAt 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $raw) {
                [PSCustomObject]@{ Repo = $repo.name; Branch = '-'; Status = 'UNAVAILABLE'; Conclusion = '-'; Title = '-' }
                continue
            }
            $runs = @($raw | ConvertFrom-Json)
            if ($runs.Count -eq 0) {
                [PSCustomObject]@{ Repo = $repo.name; Branch = '-'; Status = 'NONE'; Conclusion = '-'; Title = '-' }
                continue
            }
            $run = $runs[0]
            [PSCustomObject]@{
                Repo       = $repo.name
                Branch     = $run.headBranch
                Status     = $run.status
                Conclusion = if ($run.conclusion) { $run.conclusion } else { '-' }
                Title      = $run.displayTitle
            }
        }
        $rows | Format-Table -AutoSize
    }

    'health' {
        $rows = foreach ($repo in $Repos | Where-Object { $null -ne $_.port }) {
            $url = "http://127.0.0.1:$($repo.port)/health"
            $state = 'DOWN'
            $code = '-'
            try {
                $resp = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
                $state = 'UP'
                $code = $resp.StatusCode
            } catch {
                $tcp = New-Object System.Net.Sockets.TcpClient
                try {
                    $iar = $tcp.BeginConnect('127.0.0.1', [int]$repo.port, $null, $null)
                    if ($iar.AsyncWaitHandle.WaitOne(500, $false) -and $tcp.Connected) {
                        $state = 'LISTENING'
                    }
                } finally {
                    $tcp.Close()
                }
            }
            [PSCustomObject]@{
                Repo    = $repo.name
                Profile = $repo.profile
                Port    = $repo.port
                State   = $state
                Http    = $code
            }
        }
        $rows | Format-Table -AutoSize
    }

    'doctor' {
        Write-Host '=== Repositories ===' -ForegroundColor Cyan
        $repoRows = foreach ($repo in $Repos) {
            $repoDir = Join-Path $WorkspaceRoot $repo.name
            if (-not (Test-Path -LiteralPath $repoDir)) {
                [PSCustomObject]@{
                    Repo   = $repo.name
                    Status = '[MISSING]'
                    Branch = '-'
                    Dirty  = '-'
                }
                continue
            }
            if (-not (Test-Path -LiteralPath (Join-Path $repoDir '.git'))) {
                [PSCustomObject]@{
                    Repo   = $repo.name
                    Status = '[NO-GIT]'
                    Branch = '-'
                    Dirty  = '-'
                }
                continue
            }
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $branch = (git -C $repoDir symbolic-ref --short HEAD 2>$null)
                if (-not $branch) { $branch = (git -C $repoDir rev-parse --abbrev-ref HEAD 2>$null) }
                $porcelain = @(git -C $repoDir status --porcelain 2>$null | Where-Object { $_ -ne '' })
            } finally {
                $ErrorActionPreference = $prevEap
            }
            $dirtyCount = $porcelain.Count
            $state = if ($dirtyCount -eq 0) { '[CLEAN]' } else { "[DIRTY ($dirtyCount)]" }
            [PSCustomObject]@{
                Repo   = $repo.name
                Status = $state
                Branch = if ($branch) { $branch } else { 'UNBORN' }
                Dirty  = $dirtyCount
            }
        }
        $repoRows | Format-Table -AutoSize

        Write-Host '=== Toolchains ===' -ForegroundColor Cyan
        $tools = @('go', 'bun', 'node', 'cargo', 'python', 'git', 'gh', 'docker')
        $toolRows = foreach ($tool in $tools) {
            $cmdInfo = Get-Command $tool -ErrorAction SilentlyContinue
            if (-not $cmdInfo) {
                [PSCustomObject]@{ Tool = $tool; Status = '[MISSING]'; Version = '-' }
                continue
            }
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $verArg = if ($tool -eq 'go') { 'version' } else { '--version' }
                $verLine = (& $tool $verArg 2>$null | Select-Object -First 1)
            } catch {
                $verLine = 'unknown'
            } finally {
                $ErrorActionPreference = $prevEap
            }
            [PSCustomObject]@{
                Tool    = $tool
                Status  = '[OK]'
                Version = if ($verLine) { ($verLine -as [string]).Trim() } else { 'unknown' }
            }
        }
        $toolRows | Format-Table -AutoSize

        Write-Host '=== Disk Space ===' -ForegroundColor Cyan
        $diskRows = foreach ($driveLetter in @('C', 'Z')) {
            try {
                $drive = [System.IO.DriveInfo]::new($driveLetter)
                if ($drive.IsReady) {
                    $freeGb = [math]::Round($drive.AvailableFreeSpace / 1GB, 2)
                    $totalGb = [math]::Round($drive.TotalSize / 1GB, 2)
                    [PSCustomObject]@{
                        Drive   = "${driveLetter}:"
                        Status  = '[OK]'
                        FreeGB  = $freeGb
                        TotalGB = $totalGb
                    }
                } else {
                    [PSCustomObject]@{ Drive = "${driveLetter}:"; Status = '[NOT-READY]'; FreeGB = '-'; TotalGB = '-' }
                }
            } catch {
                [PSCustomObject]@{ Drive = "${driveLetter}:"; Status = '[MISSING]'; FreeGB = '-'; TotalGB = '-' }
            }
        }
        $diskRows | Format-Table -AutoSize
    }

    'drift' {
        & python $PSScriptRoot\scripts\drift.py
    }

    'lint' {
        $lintArgs = @()
        if ($Filter) { $lintArgs += $Filter }
        if ($ExtraArgs) { $lintArgs += $ExtraArgs }
        & python "$PSScriptRoot\scripts\quality.py" @lintArgs
        exit $LASTEXITCODE
    }

}
