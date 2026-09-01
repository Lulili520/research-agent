param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [datetime]$Date = (Get-Date),
    [string]$PublishBranch = 'radar'
)

$ErrorActionPreference = 'Stop'

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$dateText = $Date.ToString('yyyy-MM-dd')
$relativeDirectory = "data/radar/$($Date.Year)/$dateText"
$relativeFiles = @(
    "$relativeDirectory/report.md",
    "$relativeDirectory/report.json",
    "$relativeDirectory/report.pdf"
)
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$publishId = [guid]::NewGuid().ToString('N')
$worktree = Join-Path $temporaryRoot ("research-agent-radar-" + $publishId)
$temporaryBranch = "radar-publish-$publishId"
$worktreeAdded = $false
$temporaryBranchCreated = $false

Push-Location $repository
try {
    if (-not (Test-Path -LiteralPath '.git')) {
        throw "Repository root is not a Git worktree: $repository"
    }

    foreach ($relativeFile in $relativeFiles) {
        if (-not (Test-Path -LiteralPath $relativeFile -PathType Leaf)) {
            throw "Daily report artifact not found: $relativeFile"
        }
    }

    $pdf = Get-Item -LiteralPath $relativeFiles[2]
    if ($pdf.Length -gt 95MB) {
        throw "report.pdf exceeds the safe GitHub upload threshold of 95 MB: $($pdf.Length) bytes"
    }

    $report = Get-Content -Raw -Encoding utf8 -LiteralPath $relativeFiles[1] | ConvertFrom-Json
    if ($report.analysisLevel -ne 'full-text') {
        throw "Refusing to publish a non-full-text report: $($report.analysisLevel)"
    }
    if (-not $report.papers -or $report.papers.Count -lt 1 -or $report.papers.Count -gt 3) {
        throw "Unexpected paper count in report.json: $($report.papers.Count)"
    }

    & git fetch origin --prune
    if ($LASTEXITCODE -ne 0) { throw 'git fetch failed.' }

    & git show-ref --verify --quiet "refs/remotes/origin/$PublishBranch"
    if ($LASTEXITCODE -eq 0) {
        & git worktree add --detach $worktree "origin/$PublishBranch"
    } else {
        & git worktree add --orphan -b $temporaryBranch $worktree
        $temporaryBranchCreated = $LASTEXITCODE -eq 0
    }
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the isolated publishing worktree.' }
    $worktreeAdded = $true

    foreach ($relativeFile in $relativeFiles) {
        $destination = Join-Path $worktree $relativeFile
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $repository $relativeFile) -Destination $destination -Force
    }

    Push-Location $worktree
    try {
        & git add -- $relativeFiles
        if ($LASTEXITCODE -ne 0) { throw 'git add failed in the publishing worktree.' }

        & git diff --cached --quiet -- $relativeFiles
        $hasChanges = $LASTEXITCODE -eq 1
        if ($LASTEXITCODE -notin @(0, 1)) { throw 'git diff --cached failed.' }

        if ($hasChanges) {
            & git commit -m "radar: publish $dateText AI paper brief" -- $relativeFiles
            if ($LASTEXITCODE -ne 0) { throw 'git commit failed in the publishing worktree.' }
        } else {
            Write-Host "Daily report already exists on origin/$PublishBranch for $dateText."
        }

        & git push origin "HEAD:$PublishBranch"
        if ($LASTEXITCODE -ne 0) {
            throw 'git push failed without rewriting remote history.'
        }
    } finally {
        Pop-Location
    }

    $remoteUrl = (& git remote get-url origin).Trim()
    $browserUrl = $remoteUrl -replace '\.git$', ''
    Write-Host "Daily radar published: $browserUrl/tree/$PublishBranch/$relativeDirectory"
} finally {
    Pop-Location
    if ($worktreeAdded) {
        $resolvedWorktree = [System.IO.Path]::GetFullPath($worktree)
        if (-not $resolvedWorktree.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean an unexpected worktree path: $resolvedWorktree"
        }
        & git -C $repository worktree remove --force $resolvedWorktree
        & git -C $repository worktree prune
    }
    if ($temporaryBranchCreated) {
        if (-not $temporaryBranch.StartsWith('radar-publish-', [System.StringComparison]::Ordinal)) {
            throw "Refusing to remove an unexpected temporary branch: $temporaryBranch"
        }
        & git -C $repository branch -D $temporaryBranch
    }
}
