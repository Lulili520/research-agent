param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TopicDirectory
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$runtime = Join-Path $PSScriptRoot 'runtime/research/audit.py'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $pythonExecutable = $venvPython
} else {
    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        Write-Output 'ERROR: Python 3.11+ was not found. Create agent/.venv or add python.exe to PATH.'
        exit 2
    }
    $pythonExecutable = $pythonCommand.Source
}
& $pythonExecutable $runtime review $TopicDirectory
exit $LASTEXITCODE
