#!/usr/bin/env bash
# Run data-pipeline stages in the pipeline environment.
# Usage: scripts/run_pipeline.sh [--lane cpu|cu126|cu130] (--all | --stage NAME [--stage NAME ...]) [stage options]
# Lane: --lane, else $PIPELINE_LANE, else picked from the NVIDIA driver like bootstrap (>= 580 cu130, >= 525 cu126,
# otherwise cpu). GPU stages take the machine-wide GPU lock themselves.
set -euo pipefail
cd "$(dirname "$0")/.."
lane=${PIPELINE_LANE:-}
if [ "${1:-}" = "--lane" ]; then lane=${2:?--lane needs a value}; shift 2; fi
if [ -z "$lane" ]; then
  lane=cpu
  if command -v nvidia-smi >/dev/null 2>&1; then
    major=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | tr -d ' ' | cut -d. -f1)
    if [ "$major" -ge 580 ]; then lane=cu130; elif [ "$major" -ge 525 ]; then lane=cu126; fi
  fi
fi
module=$(sed -n 's/^name = "\(.*\)"$/\1/p' pipeline/pyproject.toml | head -1 | tr '-' '_')
if [ ! -f "pipeline/src/$module/__main__.py" ]; then
  echo "The pipeline stages ($module) are not implemented yet; they are built test-first in the build phase." >&2
  exit 2
fi
exec uv run --project pipeline --locked --extra "$lane" python -m "$module" "$@"
