"""Write or check the console's OpenAPI document `api/openapi.json` (FR-003-17).

Usage: python tools/gen_openapi.py [--check]
Without the flag the file is (re)written from the application. With --check nothing is written: the exit code is 0 when
the committed file equals the generated document and 1 (naming the file) when it differs or is missing.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "api")]
TARGET = ROOT / "api" / "openapi.json"


def generate() -> str:
    from pitstudio_api.app import create_app

    return json.dumps(create_app(port=8765).openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check", action="store_true", help="exit 1 when api/openapi.json differs from the generated document"
    )
    args = ap.parse_args(argv)
    text = generate()
    if args.check:
        current = TARGET.read_bytes().decode("utf-8").replace("\r\n", "\n") if TARGET.is_file() else None
        if current != text:
            print(
                f"{TARGET.relative_to(ROOT).as_posix()} differs from the application (or is missing): run python tools/gen_openapi.py"
            )
            return 1
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
