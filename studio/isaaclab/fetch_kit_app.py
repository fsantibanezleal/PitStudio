"""Post-sync step for the Isaac Lab env: put upstream's `apps/isaaclab.python.kit` where the pip install expects it.

`isaaclab.utils.assets` reads `<venv>/apps/isaaclab.python.kit` at import time (for the asset root setting), but the
git-subdirectory wheels do not ship the repository's top-level `apps/` folder. This copies that one file from the same
pinned commit as the lock (v3.0.0-EA, ae37b02...). Usage, after `uv sync` in studio/isaaclab:
    uv run python fetch_kit_app.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import httpx

COMMIT = "ae37b028ea415c91ea2bc32609efcd759ed2b974"  # = the isaaclab-* git sources in uv.lock
URL = f"https://raw.githubusercontent.com/isaac-sim/IsaacLab/{COMMIT}/apps/isaaclab.python.kit"


def main() -> int:
    dest = Path(sys.prefix) / "apps" / "isaaclab.python.kit"
    r = httpx.get(URL, follow_redirects=True, timeout=60)
    r.raise_for_status()
    if b"persistent.isaac.asset_root" not in r.content:
        print(f"unexpected content from {URL}: no asset_root setting")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    print(f"wrote {dest} ({len(r.content)} bytes, sha256 {hashlib.sha256(r.content).hexdigest()[:16]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
