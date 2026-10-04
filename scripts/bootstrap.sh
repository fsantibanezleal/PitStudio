#!/usr/bin/env bash
# Bootstrap a local environment on Linux/macOS. It NEVER installs system software: it checks for uv, Node and pnpm
# and tells you what is missing. It then creates the core venv and the pipeline venv and picks the PyTorch build from
# the NVIDIA driver: driver >= 580 -> cu130, >= 525 -> cu126, otherwise cpu.
set -euo pipefail
cd "$(dirname "$0")/.."

missing=()
for tool in uv node pnpm git; do command -v "$tool" >/dev/null 2>&1 || missing+=("$tool"); done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing tools: ${missing[*]}"
  echo "Install them yourself (uv: https://docs.astral.sh/uv/, Node 24 LTS: https://nodejs.org/, pnpm: corepack enable), then re-run."
  exit 1
fi

extra=cpu
if command -v nvidia-smi >/dev/null 2>&1; then
  driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | tr -d ' ')
  major=${driver%%.*}
  if [ "$major" -ge 580 ]; then extra=cu130; elif [ "$major" -ge 525 ]; then extra=cu126; fi
  echo "NVIDIA driver $driver -> PyTorch build '$extra'"
else
  echo "No NVIDIA GPU detected -> PyTorch build 'cpu'"
fi

uv sync --all-groups
( cd pipeline && uv sync --extra "$extra" --all-groups && uv run python ../scripts/verify_gpu.py --expect "$extra" )
if [ -f web/package.json ]; then ( cd web && pnpm install --frozen-lockfile ); fi
echo "Ready. Core tests: uv run pytest -m 'not gpu'  ·  pipeline: scripts/run_pipeline.sh --all"
