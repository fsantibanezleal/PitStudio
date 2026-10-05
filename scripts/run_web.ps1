# Build and serve the web app exactly as GitHub Pages serves it (under /<Repo>/).
# Usage: scripts/run_web.ps1 [serve|build|dev]      serve = build + local static server (default)
# Optional: $env:ACCESS_PASSPHRASE sets the demo access gate for this build (only its SHA-256 reaches the bundle).
param([ValidateSet('serve', 'build', 'dev')][string]$Mode = 'serve')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Leaf $root
Push-Location (Join-Path $root 'web')
try {
  pnpm install --frozen-lockfile
  if ($Mode -eq 'dev') { pnpm dev; return }
  $env:BASE_PATH = "/$repo/"
  pnpm build
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  if ($Mode -eq 'serve') { pnpm serve }
} finally {
  Remove-Item Env:BASE_PATH -ErrorAction SilentlyContinue
  Pop-Location
}
