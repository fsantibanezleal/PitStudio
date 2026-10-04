"""Verify that the pipeline venv got the PyTorch build it was asked for (fails fast on a silent CPU fallback).

Usage (inside pipeline/):  uv run python ../scripts/verify_gpu.py --expect cu126|cu130|cpu
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", required=True, choices=["cpu", "cu126", "cu130"])
    a = ap.parse_args(argv[1:])
    import torch

    cuda = torch.version.cuda
    print(f"torch {torch.__version__} · CUDA build {cuda} · available={torch.cuda.is_available()}")
    if a.expect == "cpu":
        return 0
    if not torch.cuda.is_available() or cuda is None:
        print(f"FAIL: expected {a.expect} but torch cannot use CUDA (CPU-only wheel or driver problem)")
        return 1
    want = {"cu126": "12.6", "cu130": "13.0"}[a.expect]
    if not cuda.startswith(want):
        print(f"FAIL: expected CUDA {want}, torch was built for {cuda}")
        return 1
    print(f"OK: {torch.cuda.get_device_name(0)} · capability {torch.cuda.get_device_capability(0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
