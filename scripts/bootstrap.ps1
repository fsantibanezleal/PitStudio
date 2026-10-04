# Bootstrap a local environment on Windows (PowerShell 7+). It NEVER installs system software: it checks for uv,
# Node and pnpm and tells you what is missing. It then creates the core venv and the pipeline venv and picks the
# PyTorch build from your NVIDIA driver: driver >= 580 -> cu130, >= 525 -> cu126, otherwise cpu.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$missing = @()
foreach ($tool in 'uv', 'node', 'pnpm', 'git') {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
}
if ($missing.Count -gt 0) {
  Write-Host "Missing tools: $($missing -join ', ')" -ForegroundColor Yellow
  Write-Host "Install them yourself (uv: https://docs.astral.sh/uv/, Node 24 LTS: https://nodejs.org/, pnpm: corepack enable), then re-run."
  exit 1
}

$extra = 'cpu'
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
  $driver = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader | Select-Object -First 1).Trim()
  $major = [int]($driver.Split('.')[0])
  if ($major -ge 580) { $extra = 'cu130' } elseif ($major -ge 525) { $extra = 'cu126' }
  Write-Host "NVIDIA driver $driver -> PyTorch build '$extra'"
} else {
  Write-Host "No NVIDIA GPU detected -> PyTorch build 'cpu'"
}

uv sync --all-groups
Push-Location pipeline
try {
  uv sync --extra $extra --all-groups
  uv run python ../scripts/verify_gpu.py --expect $extra
} finally { Pop-Location }

if (Test-Path web/package.json) {
  Push-Location web
  try { pnpm install --frozen-lockfile } finally { Pop-Location }
}
Write-Host "Ready. Core tests: uv run pytest -m 'not gpu'  ·  pipeline: scripts/run_pipeline.ps1 --all" -ForegroundColor Green
