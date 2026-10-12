# ruff: noqa: E501, PT018, RUF059
"""T-013-030 (Python side): the slider bake in `s60_export` and the Python post-model against the committed goldens.

Requirements: FR-013-38 (bake side), P-013-15 (Python reference), SC-013-03.

Oracle: the golden frames of `web/src/engines/sensors/__fixtures__/dust-golden-{1,2,3}.json`, written by the independent reference
in `tests/_sensor_kit/golden_dust.py` (the dust rule from the spec text, the MurmurHash3 reference, a hand-written 16-bit quantiser
and payload packer); regenerating them with that script gives the same bytes (checked here), so the committed goldens are the
reference. The TypeScript worker is tested against the same files (`dust-slider-parity.test.ts`).

Expected API (package `pitstudio.sensors`, root environment; NumPy only):
- `quantise.bake_slider(positions, intensity_code, class_codes, tau_unit, r_edge, beam, *, frame, seed, tau_ref, source,
  payload_path, dust_return_intensity, k_first=0.01) -> WebShard` (`.header`: a DC-013-05 dict, `.payload`: bytes): the baked
  frame of the dust slider. Per return the payload holds, planar little-endian: x, y, z uint16 codes over the frame's bounding
  box (as `encode_web_shard`), the clean intensity code (uint8), the class code (uint8: retro 0, diffuse 1), `tau_unit` (float32),
  `r_edge_m` (float32) and the beam hash h (uint32 = MurmurHash3 of (frame, beam, seed)). The header carries the 41 levels `k`:
  `k[0] = 0` (T1 = 1.0), `k[1] = k_first`, `k[40] = -ln(0.02) / tau_ref` (T1 = 0.02 on the reference target), levels 1 to 40 log-spaced
  (a constant ratio), plus the fixed `rule`, `material_codes` (retro 0, diffuse 1, dust 2), `label` and `encoding` of the schema.
- `dust.classify(tau, u, retro) -> bool array` (kept): the keep rule of FR-013-12 on baked inputs (`tau` float64, `u` float64,
  `retro` bool); `dust.emit_dust(tau, kept, max_returns) -> bool array`: the rule of FR-013-13 (a dust return where tau > 0.3216
  and the return was dropped, or `max_returns >= 2`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import golden_dust  # noqa: E402
import sensor_kit as kit  # noqa: E402
from pitstudio.sensors import dust, quantise  # noqa: E402

FIXTURES = ROOT / "web" / "src" / "engines" / "sensors" / "__fixtures__"
FILES = [FIXTURES / f"dust-golden-{i}.json" for i in (1, 2, 3)]
PARAMS = {i: p for i, p in enumerate(golden_dust.GOLDENS, start=1)}  # (seed, returns, frame, run seed)


def _load(i: int) -> dict:
    return json.loads(FILES[i - 1].read_text(encoding="utf-8"))


@pytest.mark.req("P-013-15")
def test_the_committed_goldens_are_what_the_reference_generator_writes(tmp_path: Path) -> None:
    written = golden_dust.write_all(tmp_path)
    for committed, regenerated in zip(FILES, written, strict=True):
        # compared as parsed JSON: the committed files are formatted by the web formatter (biome), the generator writes compact JSON
        assert json.loads(committed.read_text(encoding="utf-8")) == json.loads(
            regenerated.read_text(encoding="utf-8")
        ), committed.name


@pytest.mark.req("FR-013-38")
@pytest.mark.parametrize("i", [1, 2, 3])
def test_the_bake_reproduces_the_golden_payload_and_header(i: int) -> None:
    seed, n, frame, run_seed = PARAMS[i]
    gold = golden_dust.make_golden(seed, n, frame=frame, run_seed=run_seed)
    raw = gold["inputs"]
    ref = _load(i)
    shard = quantise.bake_slider(
        raw["positions"],
        raw["intensity_code"],
        raw["class_codes"],
        raw["tau_unit"],
        raw["r_edge"],
        raw["beam"],
        frame=frame,
        seed=run_seed,
        tau_ref=1.0,
        source=ref["header"]["source"],
        payload_path=ref["header"]["payload"]["path"],
        dust_return_intensity=0.05,
    )
    assert shard.payload == base64.b64decode(ref["payload_b64"])  # every plane, byte for byte
    h, g = shard.header, ref["header"]
    assert kit.schema_errors("dust-slider.schema.json", h) == []
    for key in (
        "schema_version",
        "source",
        "returns",
        "levels",
        "tau_ref",
        "rule",
        "dust_return_intensity",
        "material_codes",
        "label",
        "encoding",
    ):
        assert h[key] == g[key], key
    np.testing.assert_allclose(h["quantisation"]["offset_m"], g["quantisation"]["offset_m"], rtol=1e-12)
    np.testing.assert_allclose(h["quantisation"]["scale_m"], g["quantisation"]["scale_m"], rtol=1e-12)
    assert h["payload"] == {
        "path": g["payload"]["path"],
        "bytes": 20 * n,
        "sha256": hashlib.sha256(shard.payload).hexdigest(),
    }
    assert h["payload"]["sha256"] == g["payload"]["sha256"]


@pytest.mark.req("FR-013-38")
def test_the_slider_levels_are_41_log_spaced_from_t1_1_to_0_02() -> None:
    gold = golden_dust.make_golden(*PARAMS[1][:2], frame=PARAMS[1][2], run_seed=PARAMS[1][3], tau_ref=2.5)
    raw = gold["inputs"]
    shard = quantise.bake_slider(
        raw["positions"],
        raw["intensity_code"],
        raw["class_codes"],
        raw["tau_unit"],
        raw["r_edge"],
        raw["beam"],
        frame=3,
        seed=20261007,
        tau_ref=2.5,
        source=gold["header"]["source"],
        payload_path="sensors/s1/x.bin",
        dust_return_intensity=0.05,
        k_first=0.004,
    )
    k = np.array(shard.header["k"])
    assert len(k) == 41 and k[0] == 0.0 and k[1] == pytest.approx(0.004, rel=1e-12)
    assert k[40] * 2.5 == pytest.approx(-math.log(0.02), rel=1e-9)  # T1 = 0.02 on the reference target: tau = 3.912
    ratios = k[2:] / k[1:-1]
    assert np.all(np.diff(k) > 0) and np.allclose(ratios, ratios[0], rtol=1e-9)  # log-spaced: a constant ratio


@pytest.mark.req("P-013-15")
@pytest.mark.parametrize("i", [1, 2, 3])
@pytest.mark.parametrize("max_returns", [1, 2])
def test_the_python_decisions_on_baked_inputs_match_the_golden_at_all_41_levels(i: int, max_returns: int) -> None:
    ref = _load(i)
    seed, n, frame, run_seed = PARAMS[i]
    payload = base64.b64decode(ref["payload_b64"])
    classes = np.frombuffer(payload, dtype=np.uint8, count=n, offset=7 * n)
    tau_unit = np.frombuffer(payload, dtype="<f4", count=n, offset=8 * n).astype(np.float64)
    r_edge = np.frombuffer(payload, dtype="<f4", count=n, offset=12 * n).astype(np.float64)
    u = np.frombuffer(payload, dtype="<u4", count=n, offset=16 * n).astype(np.float64) / 2.0**32
    k = ref["header"]["k"]
    for level in ref["expected"][f"max_returns_{max_returns}"]:
        tau = k[level["level"]] * tau_unit
        kept = dust.classify(tau, u, classes == 0)
        emit = dust.emit_dust(tau, kept, max_returns)
        assert "".join("1" if x else "0" for x in kept) == level["kept"], level["level"]
        assert "".join("1" if x else "0" for x in emit) == level["emit"], level["level"]
        assert int(emit.sum()) == level["dust_count"] and r_edge[emit].tolist() == level["r_edge"]
        if "intensity" in level:
            i0 = np.frombuffer(payload, dtype=np.uint8, count=n, offset=6 * n).astype(np.float64)
            np.testing.assert_allclose(i0[kept] * np.exp(-2.0 * tau[kept]), level["intensity"], rtol=1e-12)
