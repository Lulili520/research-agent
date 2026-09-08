param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TopicDirectory
)
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $PSScriptRoot 'runtime/research/audit.py'
& python $runtime iterative $TopicDirectory
exit $LASTEXITCODE
