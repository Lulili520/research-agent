param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TopicDirectory
)

$ErrorActionPreference = 'Stop'
$topicRoot = Resolve-Path -LiteralPath $TopicDirectory -ErrorAction SilentlyContinue
if (-not $topicRoot) {
    Write-Output "ERROR: topic directory does not exist: $TopicDirectory"
    exit 2
}
$internalRoot = Join-Path $topicRoot '.research'
$root = if (Test-Path -LiteralPath $internalRoot -PathType Container) {
    Resolve-Path -LiteralPath $internalRoot
} else {
    $topicRoot
}

$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

$layout = @{
    'state.md' = 'control/state.md'; 'scope.md' = 'review/scope.md'
    'search-log.md' = 'review/search-log.md'; 'literature.md' = 'review/literature.md'
    'evidence.md' = 'review/evidence.md'; 'research-directions.md' = 'proposal/directions.md'
}

function Resolve-ArtifactPath([string]$Name) {
    $relative = if ($layout.ContainsKey($Name)) { $layout[$Name] } else { $Name }
    return Join-Path $root $relative
}

function Read-Artifact([string]$Name) {
    $path = Resolve-ArtifactPath $Name
    if ($Name -eq 'report.md' -and -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $outputDirectory = Join-Path $topicRoot 'outputs'
        $publicReport = Get-ChildItem -LiteralPath $outputDirectory -Filter '01-*.md' -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($publicReport) {
            return Get-Content -Raw -Encoding UTF8 -LiteralPath $publicReport.FullName
        }
    }
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

if ($search -and $search -notmatch '(?i)query|search|\u67e5\u8be2|\u68c0\u7d22') {
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
    $directionsPath = Resolve-ArtifactPath 'research-directions.md'
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
