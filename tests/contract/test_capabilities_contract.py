"""Contract: the committed capability report matches its schema and never carries licence-restricted or local data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts" / "capabilities.schema.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(ROOT / "studio" / "bench"))
import run_bench  # noqa: E402

VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
TELE = {"samples": 12, "max_temp_c": 71, "max_power_w": 80.5, "pcie_replays_delta": 0}


def sample_results() -> list[dict]:
    home = str(Path.home())
    return [
        {
            "probe": "warp_newton",
            "status": "pass",
            "publish": "public",
            "env": {"python": "3.14.4"},
            "versions": {"warp": "1.17.0"},
            "metrics": {"saxpy_16M_x20_s": 0.0123},
            "telemetry": TELE,
        },
        {
            "probe": "ovrtx",
            "status": "pass",
            "publish": "local-only",
            "env": {"python": "3.12.15"},
            "versions": {"ovrtx": "0.5.0"},
            "metrics": {"frames_per_s": 12.5},
            "telemetry": TELE,
        },
        {
            "probe": "tensorrt",
            "status": "fail",
            "publish": "public",
            "versions": {},
            "error": f"FileNotFoundError: {home}\\Data\\x.onnx " + "y" * 400,
            "notes": [f"see {run_bench.ROOT}\\studio\\bench"],
        },
        {"probe": "isaacsim", "status": "skip", "notes": ["probe script not written yet"]},
    ]


def test_schema_is_valid_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_public_view_matches_schema() -> None:
    doc = run_bench.public_view(sample_results(), "582.78", "NVIDIA RTX 5000 Ada Generation Laptop GPU")
    assert sorted(e.message for e in VALIDATOR.iter_errors(doc)) == []


def test_local_only_probe_publishes_no_metrics_or_telemetry() -> None:
    p = run_bench.public_view(sample_results(), "582.78", "gpu")["probes"]
    assert p["ovrtx"]["metrics"] == run_bench.LOCAL_ONLY
    assert "telemetry" not in p["ovrtx"]
    assert p["warp_newton"]["metrics"] == {"saxpy_16M_x20_s": 0.0123}
    assert p["warp_newton"]["telemetry"] == TELE
    assert p["warp_newton"]["versions"] == {"python": "3.14.4", "warp": "1.17.0"}


def test_local_paths_are_scrubbed_and_errors_truncated() -> None:
    doc = run_bench.public_view(sample_results(), "582.78", "gpu")
    text = json.dumps(doc)
    for secret in (str(Path.home()), str(Path.home()).replace("\\", "/"), str(run_bench.ROOT)):
        assert secret.replace("\\", "\\\\") not in text
        assert secret not in text
    assert len(doc["probes"]["tensorrt"]["error"]) <= 300
    assert doc["probes"]["tensorrt"]["error"].startswith("FileNotFoundError: ~")


def test_committed_report_matches_schema_when_present() -> None:
    cap = ROOT / "studio" / "capabilities.json"
    doc = json.loads(cap.read_text(encoding="utf-8")) if cap.exists() else run_bench.public_view([], "1.0", "none")
    assert sorted(e.message for e in VALIDATOR.iter_errors(doc)) == []
