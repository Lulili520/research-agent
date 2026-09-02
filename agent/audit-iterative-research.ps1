param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TopicDirectory
)

$ErrorActionPreference = 'Stop'
$topicRoot = Resolve-Path -LiteralPath $TopicDirectory -ErrorAction SilentlyContinue
if (-not $topicRoot) { Write-Output "ERROR: topic directory does not exist: $TopicDirectory"; exit 2 }
$internalRoot = Join-Path $topicRoot '.research'
$root = if (Test-Path -LiteralPath $internalRoot -PathType Container) {
    Resolve-Path -LiteralPath $internalRoot
} else {
    $topicRoot
}

$errors = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

$layout = @{
    'research.json' = 'control/project.json'; 'state.json' = 'control/state.json'
    'events.jsonl' = 'control/events.jsonl'; 'decisions.jsonl' = 'control/decisions.jsonl'
    'state.md' = 'control/state.md'; 'scope.md' = 'review/scope.md'
    'search-log.md' = 'review/search-log.md'; 'literature.md' = 'review/literature.md'
    'evidence.md' = 'review/evidence.md'; 'research-directions.md' = 'proposal/directions.md'
    'selected-direction.md' = 'proposal/selected-direction.md'; 'theory.md' = 'theory/theory.md'
}

function Resolve-ArtifactPath([string]$RelativePath) {
    $relative = if ($layout.ContainsKey($RelativePath)) { $layout[$RelativePath] } else { $RelativePath }
    return Join-Path $root $relative
}

function Require-File([string]$RelativePath) {
    $path = Resolve-ArtifactPath $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $errors.Add("missing required artifact: $RelativePath")
        return ''
    }
    return Get-Content -Raw -Encoding UTF8 -LiteralPath $path
}

$configJson = Require-File 'research.json'
$machineStateJson = Require-File 'state.json'
$events = Require-File 'events.jsonl'
$decisions = Require-File 'decisions.jsonl'
$state = Require-File 'state.md'
$machineState = $null
try {
    if ($machineStateJson) { $machineState = $machineStateJson | ConvertFrom-Json }
    if ($configJson) { $null = $configJson | ConvertFrom-Json }
} catch {
    $errors.Add("invalid machine state JSON: $($_.Exception.Message)")
}

$runtime = Join-Path $PSScriptRoot 'runtime/research/researchctl.py'
if ((Test-Path -LiteralPath $runtime -PathType Leaf) -and $machineState) {
    & python $runtime verify-log $root 2>&1 | ForEach-Object { $null = $_ }
    if ($LASTEXITCODE -ne 0) { $errors.Add('events.jsonl failed hash-chain verification') }
    $proposalPassedStages = @('theory-building', 'experiment-protocol', 'pilot', 'main-experiment', 'robustness-analysis', 'evidence-audit', 'artifact-building', 'artifact-validation', 'report-writing', 'report-review', 'complete')
    if ($proposalPassedStages -contains $machineState.research_stage) {
        & python $runtime audit-proposal $root 2>&1 | ForEach-Object { $null = $_ }
        if ($LASTEXITCODE -ne 0) { $errors.Add('research Proposal failed corpus or novelty audit') }
    }
    $scopePassedStages = @('literature-mapping', 'direction-audit', 'theory-building', 'experiment-protocol', 'pilot', 'main-experiment', 'robustness-analysis', 'evidence-audit', 'artifact-building', 'artifact-validation', 'report-writing', 'report-review', 'complete')
    if ($scopePassedStages -contains $machineState.research_stage) {
        & python $runtime audit-scope $root 2>&1 | ForEach-Object { $null = $_ }
        if ($LASTEXITCODE -ne 0) { $errors.Add('research scope failed problem-framing audit') }
    }
    $theoryPassedStages = @('experiment-protocol', 'pilot', 'main-experiment', 'robustness-analysis', 'evidence-audit', 'artifact-building', 'artifact-validation', 'report-writing', 'report-review', 'complete')
    if ($theoryPassedStages -contains $machineState.research_stage) {
        & python $runtime audit-theory $root 2>&1 | ForEach-Object { $null = $_ }
        if ($LASTEXITCODE -ne 0) { $errors.Add('theory failed mechanism, prediction, or falsifiability audit') }
    }
    $protocolLock = Join-Path $root 'experiments/protocol.lock.json'
    if (Test-Path -LiteralPath $protocolLock -PathType Leaf) {
        & python $runtime audit-protocol $root 2>&1 | ForEach-Object { $null = $_ }
        if ($LASTEXITCODE -ne 0) { $errors.Add('experiment protocol failed design or analysis-plan audit') }
    }
}
foreach ($field in @('Workflow status:', 'Research stage:', 'Novelty status:', 'Iteration:', 'Last updated:')) {
    if ($state.IndexOf($field, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        $errors.Add("state.md missing field: $field")
    }
}

$isComplete = $machineState -and $machineState.workflow_status -eq 'complete'
if ($isComplete) {
    $scope = Require-File 'scope.md'
    $search = Require-File 'search-log.md'
    $literature = Require-File 'literature.md'
    $directions = Require-File 'research-directions.md'
    $decision = Require-File 'selected-direction.md'
    $theory = Require-File 'theory.md'
    $protocol = Require-File 'experiments/protocol.md'
    $pilot = Require-File 'experiments/pilot.md'
    $experimentRegistry = Require-File 'experiments/registry.jsonl'
    $runRegistry = Require-File 'runs/registry.jsonl'
    $runOutcomes = Require-File 'runs/outcomes.jsonl'
    $results = Require-File 'experiments/results.md'
    $analysis = Require-File 'analysis.md'
    $evidence = Require-File 'evidence.md'
    $artifact = Require-File 'artifact/README.md'
    $report = Require-File 'report.md'

    foreach ($term in @('Assumptions:', 'Competing explanations:', 'Predictions:', 'Falsifiers:', 'Experiment mapping:')) {
        if ($theory -and $theory.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            $errors.Add("theory.md missing field: $term")
        }
    }
    foreach ($term in @('Claims:', 'Independent variables:', 'Dependent variables:', 'Controls:', 'Baselines:', 'Metrics:', 'Randomness:', 'Stopping rules:')) {
        if ($protocol -and $protocol.IndexOf($term, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            $errors.Add("experiments/protocol.md missing field: $term")
        }
    }
    if ($experimentRegistry -and $experimentRegistry -notmatch '(?i)experiment_id') { $errors.Add('experiment registry exposes no experiment ID') }
    if ($runRegistry -and $runRegistry -notmatch '(?i)run_id') { $errors.Add('run registry exposes no run ID') }
    if ($runOutcomes -and $runOutcomes -notmatch '(?i)status') { $errors.Add('run outcomes expose no terminal status') }
    if ($evidence -and $evidence -notmatch '\bC\d+\b') { $errors.Add('evidence.md contains no stable claim IDs') }
    if ($results -and $results -notmatch '(?im)^Outcome:\s*(supported|refuted|mixed|inconclusive)\s*$') {
        $errors.Add('experiments/results.md does not expose a valid Outcome field')
    }
    if ($search -and ($search -notmatch '(?i)query|search' -or $search -notmatch '\b20\d{2}-\d{2}-\d{2}\b')) {
        $errors.Add('search-log.md lacks dated queries')
    }
}

if ($isComplete -and $errors.Count -gt 0) { $errors.Add('machine state claims completion while audit errors remain') }
foreach ($message in $warnings) { Write-Output "WARNING: $message" }
foreach ($message in $errors) { Write-Output "ERROR: $message" }
Write-Output "Iterative research audit: $($errors.Count) error(s), $($warnings.Count) warning(s)"
if ($errors.Count -gt 0) { exit 1 }
exit 0
