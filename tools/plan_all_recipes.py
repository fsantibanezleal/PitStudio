"""Plan every recipe of `studio/recipes/{cases,_bench}` with one profile and the committed fake GPU (FR-002-05).

Usage: python tools/plan_all_recipes.py --profile linux-gpu
Exit 0 when every plan exits 0 and none leaks a machine detail (FR-002-04 patterns, host, user, home); else 1.
The repository is PITSTUDIO_REPO or this checkout; the GPU is the fake device below (no driver or NVML needed).
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import io
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DEVICE = ROOT / "tests" / "fixtures" / "fake_gpu" / "linux-1x48gib.yaml"
PATTERNS = [
    re.compile(p)
    for p in (
        r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]",
        r"\\\\[A-Za-z0-9._$-]+\\",
        r"(^|[\s\"'=(,:])/(home|Users|root|tmp|var|mnt|media|opt|srv|private|run)/",
        r"\\",
    )
]


def leaks(text: str) -> list[str]:
    found = [p.pattern for p in PATTERNS if p.search(text)]
    who = {socket.gethostname(), getpass.getuser(), Path.home().name}
    return found + [
        f"identity {w}"
        for w in sorted(who)
        if len(w) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(w.lower())}(?![a-z0-9])", text.lower())
    ]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    args = ap.parse_args(argv)
    from pitstudio.runner import cli

    repo = Path(os.environ.get("PITSTUDIO_REPO") or ROOT)
    files = sorted(p for d in ("cases", "_bench") for p in (repo / "studio" / "recipes" / d).glob("*.yaml"))
    failed = 0
    with tempfile.TemporaryDirectory(prefix="pst") as store:
        os.environ.setdefault("PITSTUDIO_STORE", store)  # planning never writes; the profile default may not exist here
        for f in files:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(
                    ["plan", str(f), "--profile", args.profile, "--json", "--gpu-backend", f"fake:{DEVICE}"]
                )
            bad = leaks(out.getvalue())
            print(
                f"planned {f.parent.name}/{f.name}: "
                + ("ok" if code == 0 and not bad else f"FAILED exit {code} {err.getvalue().strip()} {bad}")
            )
            failed += code != 0 or bool(bad)
    print(f"{len(files)} recipe(s) planned with {args.profile}, {failed} failure(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
