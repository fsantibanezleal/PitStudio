#!/usr/bin/env bash
# Build and serve the web app exactly as GitHub Pages serves it (under /<Repo>/).
# Usage: scripts/run_web.sh [serve|build|dev]      serve = build + local static server (default)
# Optional: ACCESS_PASSPHRASE=<phrase> sets the demo access gate for this build (only its SHA-256 reaches the bundle).
set -euo pipefail
cd "$(dirname "$0")/.."
repo=$(basename "$PWD")
mode=${1:-serve}
cd web
pnpm install --frozen-lockfile
# Git Bash on Windows rewrites values that look like POSIX paths (BASE_PATH=/Repo/); MSYS_NO_PATHCONV stops that.
export MSYS_NO_PATHCONV=1
case "$mode" in
  dev) exec pnpm dev ;;
  build) BASE_PATH="/$repo/" pnpm build ;;
  serve) BASE_PATH="/$repo/" pnpm build && BASE_PATH="/$repo/" exec pnpm serve ;;
  *) echo "usage: $0 [serve|build|dev]" >&2; exit 2 ;;
esac
