"""T-016-011: reject hostile ONNX files at every consumer (unit, hostile).

Requirements: FR-016-03.

Spec: specs/016-export-acceleration/spec.md FR-016-03 (a file that does not parse as a ModelProto, has `ir_version`
> 10, references external data outside its own folder, or is >= 2^31 bytes is rejected with the reason and nothing
is processed from it); plan.md test strategy row FR-016-03 (truncated bytes, `ir_version` 11, external data
`../w.bin`, a reported size of 2^31 bytes).

Oracles (hand calculation written in the test, nothing taken from the code under test):
- truncated bytes: the first half of a valid serialised model is not a parseable ModelProto (checked here with
  `onnx.load_from_string`, which must raise, before the guard is asked);
- `ir_version` 11 and 10: the boundary of the spec (> 10 rejected, <= 10 accepted);
- external-data locations `../w.bin`, `sub/../../w.bin` and an absolute path escape the model's folder; `w.bin` and
  `weights/w.bin` do not;
- sizes 2^31 - 1 (accepted) and 2^31 (rejected), supplied as the reported size because a 2 GiB file cannot be written
  in a unit test.

Expected public API (module `pitstudio_pipeline.export.onnx_guard`, `pipeline/` environment; the single choke point that
`s62_accel`, `s64_bench` and the web bake call before reading a file, see the consumer tests in T-016-033 and
T-016-040):
    class OnnxFileRejected(Exception)       # `.reason: str` (also the message), never empty
    @dataclass OnnxFileInfo                 # ir_version: int, nbytes: int, sha256: str (hex)
    check_onnx_file(path: Path, *, size_bytes: int | None = None) -> OnnxFileInfo
        `size_bytes` overrides the size read from the file system (the "reported" size).
        Raises OnnxFileRejected for: a missing path or a directory, bytes that do not parse as a ModelProto (empty,
        truncated, garbage), `ir_version` > 10, any initializer whose external-data `location` is absolute or resolves
        outside the folder of `path`, and a size >= 2**31.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pitstudio_pipeline.export.onnx_guard import OnnxFileRejected, check_onnx_file


def _model(*, ir: int = 10, external_location: str | None = None):
    import numpy as np
    from onnx import TensorProto, helper, numpy_helper

    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])
    w = numpy_helper.from_array(np.ones((1, 4), dtype=np.float32), "w")
    if external_location is not None:
        w.ClearField("raw_data")
        w.data_location = TensorProto.EXTERNAL
        for key, value in (("location", external_location), ("offset", "0"), ("length", "16")):
            entry = w.external_data.add()
            entry.key, entry.value = key, value
    node = helper.make_node("Mul", ["x", "w"], ["y"])
    model = helper.make_model(
        helper.make_graph([node], "g", [x], [y], initializer=[w]), opset_imports=[helper.make_opsetid("", 18)]
    )
    model.ir_version = ir
    return model


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.mark.req("FR-016-03")
def test_valid_ir10_model_is_accepted_and_described(tmp_path: Path) -> None:
    data = _model(ir=10).SerializeToString()
    info = check_onnx_file(_write(tmp_path, "ok.onnx", data))
    assert info.ir_version == 10
    assert info.nbytes == len(data)
    assert info.sha256 == hashlib.sha256(data).hexdigest()


@pytest.mark.req("FR-016-03")
def test_old_ir_versions_are_accepted(tmp_path: Path) -> None:
    for ir in (3, 8, 9):
        assert check_onnx_file(_write(tmp_path, f"ir{ir}.onnx", _model(ir=ir).SerializeToString())).ir_version == ir


@pytest.mark.req("FR-016-03")
@pytest.mark.parametrize("ir", [11, 12, 14])
def test_ir_version_above_10_is_rejected_with_the_reason(tmp_path: Path, ir: int) -> None:
    path = _write(tmp_path, "new.onnx", _model(ir=ir).SerializeToString())
    with pytest.raises(OnnxFileRejected) as info:
        check_onnx_file(path)
    assert "ir_version" in info.value.reason


@pytest.mark.req("FR-016-03")
def test_truncated_bytes_do_not_parse_and_are_rejected(tmp_path: Path) -> None:
    import onnx

    whole = _model().SerializeToString()
    half = whole[: len(whole) // 2]
    with pytest.raises(Exception):  # noqa: B017, PT011  # oracle: the reference parser itself refuses these bytes
        onnx.load_from_string(half)
    with pytest.raises(OnnxFileRejected) as info:
        check_onnx_file(_write(tmp_path, "cut.onnx", half))
    assert info.value.reason


@pytest.mark.req("FR-016-03")
@pytest.mark.parametrize(
    "data",
    [b"", b"\x00", b"not an onnx file at all", b"\xff" * 64, "unicode \u00e9\u4e2d\u6587".encode()],
    ids=["empty", "one-zero-byte", "ascii-text", "all-ff", "unicode-text"],
)
def test_garbage_bytes_are_rejected(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(OnnxFileRejected) as info:
        check_onnx_file(_write(tmp_path, "junk.onnx", data))
    assert info.value.reason


@pytest.mark.req("FR-016-03")
def test_missing_file_and_directory_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(OnnxFileRejected):
        check_onnx_file(tmp_path / "absent.onnx")
    (tmp_path / "dir.onnx").mkdir()
    with pytest.raises(OnnxFileRejected):
        check_onnx_file(tmp_path / "dir.onnx")


@pytest.mark.req("FR-016-03")
@pytest.mark.parametrize("location", ["../w.bin", "sub/../../w.bin", "/etc/w.bin", "C:/w.bin", "..\\w.bin"])
def test_external_data_outside_the_models_folder_is_rejected(tmp_path: Path, location: str) -> None:
    path = _write(tmp_path, "m/model.onnx", _model(external_location=location).SerializeToString())
    with pytest.raises(OnnxFileRejected) as info:
        check_onnx_file(path)
    assert "external" in info.value.reason.lower()


@pytest.mark.req("FR-016-03")
@pytest.mark.parametrize("location", ["w.bin", "weights/w.bin", "./w.bin"])
def test_external_data_inside_the_models_folder_is_accepted(tmp_path: Path, location: str) -> None:
    path = _write(tmp_path, "m/model.onnx", _model(external_location=location).SerializeToString())
    _write(tmp_path, f"m/{location}", b"\x00" * 16)
    assert check_onnx_file(path).ir_version == 10


@pytest.mark.req("FR-016-03")
def test_reported_size_boundary_is_2_pow_31_bytes(tmp_path: Path) -> None:
    path = _write(tmp_path, "m.onnx", _model().SerializeToString())
    assert check_onnx_file(path, size_bytes=2**31 - 1).nbytes == 2**31 - 1
    with pytest.raises(OnnxFileRejected) as info:
        check_onnx_file(path, size_bytes=2**31)
    assert "size" in info.value.reason.lower()


@pytest.mark.req("FR-016-03")
def test_a_unicode_file_name_is_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path, "modelo-\u00e1\u00f1\u4e2d.onnx", _model().SerializeToString())
    assert check_onnx_file(path).ir_version == 10
