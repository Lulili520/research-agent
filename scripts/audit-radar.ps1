param([string]$RadarRoot = 'radar')

$ErrorActionPreference = 'Stop'
$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

if (-not (Test-Path -LiteralPath $RadarRoot -PathType Container)) {
    Write-Output "ERROR: radar directory does not exist: $RadarRoot"
    exit 2
}
foreach ($name in @('index.json', 'queue.json', 'queue.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $RadarRoot $name) -PathType Leaf)) { $errors.Add("missing $name") }
}
$reports = @(Get-ChildItem -LiteralPath $RadarRoot -Recurse -File -Filter '*.json' | Where-Object { $_.Name -notin @('index.json', 'queue.json') })
if ($reports.Count -eq 0) { $errors.Add('no dated radar JSON report found') }
foreach ($file in $reports) {
    try { $report = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName | ConvertFrom-Json } catch { $errors.Add("invalid JSON: $($file.FullName)"); continue }
    foreach ($field in @('date', 'generatedAt', 'primaryStart', 'lookbackStart', 'timezone', 'outputLanguage', 'provenance', 'failures', 'leads', 'watch')) {
        if ($null -eq $report.$field) { $errors.Add("$($file.Name) missing field: $field") }
    }
    if ($report.timezone -ne 'Asia/Shanghai') { $warnings.Add("$($file.Name) uses unexpected timezone") }
    if ($report.outputLanguage -ne 'zh-CN') { $errors.Add("$($file.Name) output language is not zh-CN") }
    $primaryHours = ([datetime]$report.generatedAt - [datetime]$report.primaryStart).TotalHours
    $lookbackHours = ([datetime]$report.generatedAt - [datetime]$report.lookbackStart).TotalHours
    if ([math]::Abs($primaryHours - 24) -gt 0.1) { $errors.Add("$($file.Name) primary window is not 24h") }
    if ([math]::Abs($lookbackHours - 72) -gt 0.1) { $errors.Add("$($file.Name) lookback window is not 72h") }
    foreach ($item in @($report.leads)) {
        if (-not $item.stableId -or -not $item.url -or -not $item.abstract -or $item.relevance -lt 1) { $errors.Add("$($file.Name) has an invalid lead item") }
    }
    if (@($report.provenance).Count -eq 0) { $errors.Add("$($file.Name) has no provenance") }
    $markdownPath = [System.IO.Path]::ChangeExtension($file.FullName, '.md')
    if (-not (Test-Path -LiteralPath $markdownPath)) { $errors.Add("$($file.Name) missing Markdown report") }
}
foreach ($message in $warnings) { Write-Output "WARNING: $message" }
foreach ($message in $errors) { Write-Output "ERROR: $message" }
Write-Output "Radar audit: $($errors.Count) error(s), $($warnings.Count) warning(s), $($reports.Count) report(s)"
if ($errors.Count) { exit 1 }
