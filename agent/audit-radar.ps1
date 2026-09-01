param([string]$RadarRoot = 'data/radar')
$ErrorActionPreference = 'Stop'
$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

if (-not (Test-Path -LiteralPath $RadarRoot -PathType Container)) { Write-Output "ERROR: missing radar directory: $RadarRoot"; exit 2 }
if (-not (Test-Path -LiteralPath (Join-Path $RadarRoot 'index.json') -PathType Leaf)) { $errors.Add('missing index.json') }

$reports = @(Get-ChildItem -LiteralPath $RadarRoot -Recurse -File -Filter '*.json' | Where-Object { $_.Name -ne 'index.json' })
foreach ($file in $reports) {
    try { $report = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName | ConvertFrom-Json } catch { $errors.Add("invalid JSON: $($file.FullName)"); continue }
    if ($report.schemaVersion -lt 5) { $warnings.Add("$($file.Name) uses legacy radar schema"); continue }
    $requiredFields = if ($report.schemaVersion -ge 6) {
        @('date', 'generatedAt', 'timezone', 'outputLanguage', 'analysisLevel', 'selectionPolicy', 'selectionSummary', 'papers', 'provenance', 'failures')
    } else {
        @('date', 'coverageDate', 'generatedAt', 'primaryStart', 'primaryEnd', 'lookbackStart', 'timezone', 'outputLanguage', 'analysisLevel', 'selectionPolicy', 'freshSelectionCount', 'backfillSelectionCount', 'papers', 'provenance', 'failures')
    }
    foreach ($field in $requiredFields) {
        if ($null -eq $report.$field) { $errors.Add("$($file.Name) missing field: $field") }
    }
    if ($report.timezone -ne 'Asia/Shanghai') { $errors.Add("$($file.Name) timezone must be Asia/Shanghai") }
    if ($report.outputLanguage -ne 'zh-CN') { $errors.Add("$($file.Name) output language must be zh-CN") }
    if ($report.analysisLevel -notin @('abstract-screening', 'full-text')) { $errors.Add("$($file.Name) invalid analysisLevel") }
    if ($file.Name -ne 'report.json' -or $file.Directory.Name -ne $report.date) { $errors.Add("$($file.FullName) must be stored as <year>/<date>/report.json") }
    if (@($report.papers).Count -gt 3) { $errors.Add("$($file.Name) contains more than three papers") }
    if ($report.schemaVersion -lt 6 -and $report.freshSelectionCount + $report.backfillSelectionCount -ne @($report.papers).Count) { $errors.Add("$($file.Name) selection counts do not match papers") }
    foreach ($paper in @($report.papers)) {
        if (-not $paper.stableId -or -not $paper.title -or -not $paper.url -or -not $paper.abstract -or -not $paper.selectionTopic -or -not $paper.selectionWindow) { $errors.Add("$($file.Name) has an incomplete paper") }
        if ($report.analysisLevel -eq 'full-text') {
            if (-not $paper.fullTextSource -or -not $paper.fullTextPages -or -not $paper.analysis) { $errors.Add("$($file.Name) marks full-text but lacks full-text evidence for $($paper.stableId)") }
            elseif (-not $paper.analysis.problem -or -not $paper.analysis.method -or -not $paper.analysis.keyEvidence -or -not $paper.analysis.limitations -or -not $paper.analysis.evidenceLocations) { $errors.Add("$($file.Name) has incomplete full-text analysis for $($paper.stableId)") }
            if ($report.schemaVersion -ge 6 -and (-not $paper.qualityAssessment -or -not $paper.qualityAssessment.tier -or -not $paper.qualityAssessment.researchGenerativity)) { $errors.Add("$($file.Name) lacks importance assessment for $($paper.stableId)") }
            if ($paper.venue -and (-not $paper.presentationType -or -not $paper.officialVenueSource)) { $errors.Add("$($file.Name) lacks official venue verification for $($paper.stableId)") }
        }
    }
    if ($report.schemaVersion -lt 6) {
        $windowHours = (([datetime]$report.primaryEnd) - ([datetime]$report.primaryStart)).TotalHours
        if ([math]::Abs($windowHours - 24) -gt 0.1) { $errors.Add("$($file.Name) primary window is not 24h") }
    }
    foreach ($extension in @('.md', '.pdf')) {
        $artifact = [System.IO.Path]::ChangeExtension($file.FullName, $extension)
        if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) { $errors.Add("$($file.Name) missing $extension artifact") }
    }
    $processFiles = @(Get-ChildItem -LiteralPath $file.Directory.FullName -Force -Recurse -File | Where-Object { $_.Extension -in @('.aux', '.log', '.tex', '.xdv', '.toc', '.out', '.png', '.txt') })
    if ($processFiles.Count) { $errors.Add("$($file.Directory.FullName) contains build-process files") }
    if ($report.analysisLevel -eq 'full-text') {
        $sourceDir = Join-Path $file.Directory.FullName 'sources'
        if (-not (Test-Path -LiteralPath $sourceDir -PathType Container)) { $errors.Add("$($file.Directory.FullName) missing sources directory") }
        elseif (@(Get-ChildItem -LiteralPath $sourceDir -File -Filter '*.pdf').Count -ne @($report.papers).Count) { $errors.Add("$($file.Directory.FullName) source PDF count does not match papers") }
    }
}

if ($reports.Count -eq 0) { $errors.Add('no dated radar report found') }
foreach ($message in $warnings) { Write-Output "WARNING: $message" }
foreach ($message in $errors) { Write-Output "ERROR: $message" }
Write-Output "Radar audit: $($errors.Count) error(s), $($warnings.Count) warning(s), $($reports.Count) report(s)"
if ($errors.Count) { exit 1 }
