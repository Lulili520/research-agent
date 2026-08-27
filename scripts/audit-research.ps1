param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TopicDirectory
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path -LiteralPath $TopicDirectory -ErrorAction SilentlyContinue
if (-not $root) {
    Write-Output "ERROR: topic directory does not exist: $TopicDirectory"
    exit 2
}

$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Read-Artifact([string]$Name) {
    $path = Join-Path $root $Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $errors.Add("missing required artifact: $Name")
        return ''
    }
    return Get-Content -Raw -Encoding UTF8 -LiteralPath $path
}

function Get-IsoDates([string]$Text) {
    $result = [System.Collections.Generic.List[datetime]]::new()
    foreach ($match in [regex]::Matches($Text, '\b20\d{2}-\d{2}-\d{2}\b')) {
        $parsed = [datetime]::MinValue
        if ([datetime]::TryParseExact($match.Value, 'yyyy-MM-dd', $null, 'None', [ref]$parsed)) {
            $result.Add($parsed)
        }
    }
    return $result
}

$state = Read-Artifact 'state.md'
$search = Read-Artifact 'search-log.md'
$literature = Read-Artifact 'literature.md'
$evidence = Read-Artifact 'evidence.md'
$report = Read-Artifact 'report.md'

foreach ($field in @('Workflow status:', 'Novelty status:', 'Search cutoff:', 'Last updated:')) {
    if ($state.IndexOf($field, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        $errors.Add("state.md missing field: $field")
    }
}

$stateDates = @(Get-IsoDates $state)
$artifactDates = @(Get-IsoDates ($search + "`n" + $evidence + "`n" + $report))
if ($stateDates.Count -gt 0 -and $artifactDates.Count -gt 0) {
    $latestState = ($stateDates | Sort-Object -Descending | Select-Object -First 1)
    $latestArtifact = ($artifactDates | Sort-Object -Descending | Select-Object -First 1)
    if ($latestState -lt $latestArtifact) {
        $errors.Add('state.md is older than another core artifact')
    }
}

foreach ($item in @(@('search-log.md', $search), @('literature.md', $literature))) {
    if ($item[1] -notmatch 'https?://') {
        $warnings.Add("$($item[0]) contains no stable links")
    }
}

if ($search -and $search -notmatch '(?i)query|search') {
    $errors.Add('search-log.md does not expose queries/search activity')
}
if ($search -and $search -notmatch '\b20\d{2}-\d{2}-\d{2}\b') {
    $errors.Add('search-log.md has no run/update date')
}

$claimIds = @([regex]::Matches($evidence, '\bC\d+\b') | ForEach-Object Value | Sort-Object -Unique)
if ($claimIds.Count -eq 0) {
    $errors.Add('evidence.md contains no stable claim IDs')
} elseif (-not ($claimIds | Where-Object { $report -match "\b$([regex]::Escape($_))\b" })) {
    $warnings.Add('report.md does not expose claim-ID traceability')
}

if ($state -match '(?i)Novelty status:\s*provisional') {
    $directionsPath = Join-Path $root 'research-directions.md'
    $directions = if (Test-Path -LiteralPath $directionsPath) {
        Get-Content -Raw -Encoding UTF8 -LiteralPath $directionsPath
    } else { '' }
    if ($search -notmatch '(?i)novelty status remains provisional') {
        $errors.Add('provisional novelty lacks a dated/scoped bounded statement')
    }
}

if ($state -match '(?i)Workflow status:\s*complete' -and $errors.Count -gt 0) {
    $errors.Add('state claims workflow completion while audit errors remain')
}

foreach ($message in $warnings) { Write-Output "WARNING: $message" }
foreach ($message in $errors) { Write-Output "ERROR: $message" }
Write-Output "Audit summary: $($errors.Count) error(s), $($warnings.Count) warning(s)"
if ($errors.Count -gt 0) { exit 1 }
exit 0
