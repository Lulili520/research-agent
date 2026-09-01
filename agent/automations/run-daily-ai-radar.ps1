param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = 'Stop'

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$promptPath = Join-Path $repository 'agent\automations\daily-ai-radar.md'
$logDirectory = Join-Path $repository '.codex-log'
$lockPath = Join-Path $logDirectory 'daily-ai-radar.lock'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $logDirectory "daily-ai-radar-$timestamp.log"
$resultPath = Join-Path $logDirectory "daily-ai-radar-$timestamp-result.md"

if (-not (Test-Path -LiteralPath $promptPath -PathType Leaf)) {
    throw "Automation prompt not found: $promptPath"
}

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $utf8
[Console]::OutputEncoding = $utf8

$lockStream = $null
try {
    $lockStream = [System.IO.File]::Open(
        $lockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch [System.IO.IOException] {
    "$(Get-Date -Format o) Another daily radar run is active; skipped." |
        Set-Content -LiteralPath $logPath -Encoding utf8
    exit 0
}

try {
    $codexCommand = Get-Command codex.cmd -ErrorAction Stop
    $prompt = 'Read and fully execute the task prompt in agent/automations/daily-ai-radar.md. This is an unattended daily run: do not wait for user confirmation. Write only the report artifacts, sources, temporary build files, and logs permitted by that task inside this repository. Do not commit or push Git and do not modify agent definitions. If a complete report for today already passes audit, verify it and exit without regenerating it.'

    "$(Get-Date -Format o) Starting Codex daily AI radar in $repository" |
        Set-Content -LiteralPath $logPath -Encoding utf8

    $savedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $prompt | & $codexCommand.Source exec `
            --cd $repository `
            --approve-for-me `
            --color never `
            --output-last-message $resultPath `
            - 2>&1 | Out-File -LiteralPath $logPath -Encoding utf8 -Append
        $codexExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }

    if ($codexExitCode -ne 0) {
        throw "Codex exited with code $codexExitCode. See $logPath"
    }

    $publishScript = Join-Path $repository 'agent\automations\publish-daily-radar.ps1'
    & $publishScript -RepositoryRoot $repository

    "$(Get-Date -Format o) Completed successfully." |
        Add-Content -LiteralPath $logPath -Encoding utf8
} catch {
    "$(Get-Date -Format o) FAILED: $($_.Exception.Message)" |
        Add-Content -LiteralPath $logPath -Encoding utf8
    throw
} finally {
    if ($null -ne $lockStream) {
        $lockStream.Dispose()
    }
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
