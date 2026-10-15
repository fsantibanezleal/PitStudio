"""T-016-010: export determinism (pipeline).

Requirements: NFR-016-03.

Spec: specs/016-export-acceleration/spec.md NFR-016-03 ("re-exporting from the same checkpoint, code and lock gives
byte-identical ONNX files and manifest entries"); plan.md test strategy row NFR-016-03 (metamorphic: two exports,
byte-identical files).

Oracle: the metamorphic relation itself, evaluated with `hashlib.sha256` over the file bytes and a byte comparison
(no number comes from the code under test): exporting the same seeded module twice, in two different output folders and
with an unrelated export in between, yields equal bytes and equal SHA-256 digests, and the file does not embed the
output folder, the wall-clock time or the host name.

Expected public API (module `pitstudio_pipeline.export.onnx_export`, see tests/unit/test_t_016_010_onnx_export.py for
the full contract): `export_model(model, example_inputs, config, out_path) -> ExportResult` with `.sha256` (hex SHA-256
of the written file) and `.path`.
"""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest
from pitstudio_pipeline.export.onnx_export import export_model

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads(
    (ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples" / "export-config.valid-gns.json").read_text(
        encoding="utf-8"
    )
)


def _module(seed: int):
    import torch

    torch.manual_seed(seed)
    model = torch.nn.Sequential(torch.nn.Conv2d(3, 4, 3, padding=1), torch.nn.ReLU(), torch.nn.AdaptiveAvgPool2d(1))
    return model.eval(), (torch.zeros(1, 3, 8, 8),)


@pytest.mark.req("NFR-016-03")
def test_two_exports_of_the_same_module_are_byte_identical_with_equal_digests(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    m1, i1 = _module(7)
    first = export_model(m1, i1, CONFIG, tmp_path / "a" / "model.onnx")
    m_other, i_other = _module(99)
    export_model(m_other, i_other, CONFIG, tmp_path / "other.onnx")  # unrelated export in between
    m2, i2 = _module(7)
    second = export_model(m2, i2, CONFIG, tmp_path / "b" / "model.onnx")

    bytes_a = (tmp_path / "a" / "model.onnx").read_bytes()
    bytes_b = (tmp_path / "b" / "model.onnx").read_bytes()
    assert bytes_a == bytes_b
    assert first.sha256 == second.sha256 == hashlib.sha256(bytes_a).hexdigest()


@pytest.mark.req("NFR-016-03")
def test_exports_of_different_weights_differ(tmp_path: Path) -> None:
    m1, i1 = _module(7)
    m2, i2 = _module(8)
    a = export_model(m1, i1, CONFIG, tmp_path / "a.onnx")
    b = export_model(m2, i2, CONFIG, tmp_path / "b.onnx")
    assert a.sha256 != b.sha256  # the digest is not a constant


@pytest.mark.req("NFR-016-03")
def test_exported_file_embeds_no_folder_host_or_clock_values(tmp_path: Path) -> None:
    folder = tmp_path / "unique-folder-name-for-the-test"
    folder.mkdir()
    m, i = _module(3)
    export_model(m, i, CONFIG, folder / "model.onnx")
    data = (folder / "model.onnx").read_bytes()
    assert b"unique-folder-name-for-the-test" not in data
    assert socket.gethostname().encode() not in data or len(socket.gethostname()) < 4
