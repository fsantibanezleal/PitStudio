# Run data-pipeline stages in the pipeline environment.
# Usage: scripts/run_pipeline.ps1 [-Lane cpu|cu126|cu130] (--all | --stage NAME [--stage NAME ...]) [stage options]
# Lane: -Lane, else $env:PIPELINE_LANE, else picked from the NVIDIA driver like bootstrap (>= 580 cu130, >= 525 cu126,
# otherwise cpu). GPU stages take the machine-wide GPU lock themselves.
param([ValidateSet('', 'cpu', 'cu126', 'cu130')][string]$Lane = '', [Parameter(ValueFromRemainingArguments)][string[]]$Rest)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $Lane) { $Lane = $env:PIPELINE_LANE }
if (-not $Lane) {
  $Lane = 'cpu'
  if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $major = [int]((& nvidia-smi --query-gpu=driver_version --format=csv,noheader | Select-Object -First 1).Trim().Split('.')[0])
    if ($major -ge 580) { $Lane = 'cu130' } elseif ($major -ge 525) { $Lane = 'cu126' }
  }
}
$name = (Select-String -Path pipeline/pyproject.toml -Pattern '^name = "(.*)"$' | Select-Object -First 1).Matches[0].Groups[1].Value
$module = $name -replace '-', '_'
if (-not (Test-Path "pipeline/src/$module/__main__.py")) {
  Write-Host "The pipeline stages ($module) are not implemented yet; they are built test-first in the build phase." -ForegroundColor Yellow
  exit 2
}
uv run --project pipeline --locked --extra $Lane python -m $module @Rest
exit $LASTEXITCODE
