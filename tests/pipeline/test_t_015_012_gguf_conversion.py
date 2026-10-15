# ruff: noqa: E501
"""T-015-012: the lane's own GGUF conversion pipeline with fake tools, and the determinism of the output hashes.

Requirements: FR-015-05, P-015-12.

Spec: specs/015-vlm/spec.md
- FR-015-05: when the Cosmos weights are converted, the lane runs `convert_hf_to_gguf.py` from the llama.cpp source at tag b11381 to
  produce an F16 text model and an F16 vision projector (`mmproj`), then `llama-quantize` b11381 to produce Q8_0, and records the SHA-256 of
  every output; a second conversion from the same inputs produces identical SHA-256 values.
- P-015-12: converting the same inputs with the same tools twice yields identical SHA-256 values for the F16 model, the projector and the
  Q8_0 file (the real-model equality is checked locally by tests/gpu/test_t_015_070_reason_local.py).
- spec section 7: GGUF Q8_0 layout (llama.cpp `ggml/src/ggml-common.h`): `QK8_0 = 32`; `block_q8_0 { ggml_half d; int8_t qs[QK8_0]; }`, a
  block of 32 weights takes 34 bytes = 8.5 bits per weight.
- FR-015-06 (related): conversions are never tracked in git, so the output folder must lie outside the repository.

Oracle: fake tools (`FakeTools` below) that write bytes which are a deterministic function of their inputs only (the converter: the bytes of
the snapshot files, the output type and whether `--mmproj` was given; the quantiser: the bytes of its input file and the type), so the expected
digests are recomputed in the test with `hashlib`; the command lines expected by the documented interface of llama.cpp's converter
(`convert_hf_to_gguf.py <model dir> --outtype f16 --outfile <file> [--mmproj]`) and quantiser (`llama-quantize <in.gguf> <out.gguf> Q8_0`); the Q8_0
block arithmetic of the header.

Expected API of the implementation (package `pitstudio_pipeline`), `pitstudio_pipeline.reason.convert`:
- `ConversionError(Exception)` with `step` ("f16", "mmproj", "q8_0", or "inputs" when a precondition fails) and `reason`.
- `convert_model(snapshot, out_dir, *, runtime, pins, python, converter, runner, repo_root) -> ConversionResult` where `snapshot` is the
  verified Cosmos snapshot folder, `runtime` a `VerifiedRuntime`, `pins` the pin document, `python` the interpreter for the converter,
  `converter` the path of `convert_hf_to_gguf.py` of the b11381 source tree, `runner(argv: list[str]) -> int` runs one command and returns
  its exit code. Before any command it verifies the snapshot files against the Cosmos pins (ProvenanceError of
  `pitstudio_pipeline.reason.hub`), the converter script against `pins["llamacpp"]["converter"]["sha256"]` (PinError of
  `pitstudio_pipeline.reason.runtime`, `file == "convert_hf_to_gguf.py"`) and that `out_dir` is outside `repo_root` (ConversionError, step "inputs").
  It then runs, in this order: the converter for the F16 text model, the converter with `--mmproj` for the F16 projector, `llama-quantize` from
  `runtime.executable("llama-quantize.exe")` for Q8_0 from the F16 text model; a non-zero exit code raises ConversionError with that step and
  stops. `ConversionResult` has `f16`, `mmproj`, `q8_0` (Paths inside `out_dir`) and `sha256` (`{"f16", "mmproj", "q8_0"}` to hex digests of the
  file bytes) and the same digests are written to `out_dir / "conversion.json"`.
- `q8_0_tensor_bytes(n_weights) -> int`: 34 bytes per 32 weights; ValueError for a negative count or one that is not a multiple of 32.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import _p015_pins_kit as kit
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pitstudio_pipeline.reason import convert, hub, runtime


class FakeTools:
    """Fake converter and quantiser: outputs are a deterministic function of the inputs; every command is recorded."""

    def __init__(self, *, fail_step: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_step = fail_step

    @staticmethod
    def expand(tag: bytes, n: int = 4000) -> bytes:
        out = bytearray()
        i = 0
        while len(out) < n:
            out += hashlib.sha256(tag + str(i).encode()).digest()
            i += 1
        return bytes(out[:n])

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(list(argv))
        a = [str(x) for x in argv]
        if any(x.endswith("convert_hf_to_gguf.py") for x in a):
            mm = "--mmproj" in a
            step = "mmproj" if mm else "f16"
            if self.fail_step == step:
                return 3
            outtype = a[a.index("--outtype") + 1]
            snap = Path(next(x for x in a if Path(x).is_dir()))
            h = hashlib.sha256()
            for f in sorted(snap.iterdir()):
                h.update(f.name.encode() + f.read_bytes())
            tag = h.digest() + outtype.encode() + (b"mmproj" if mm else b"text")
            Path(a[a.index("--outfile") + 1]).write_bytes(self.expand(tag))
            return 0
        if Path(a[0]).name == "llama-quantize.exe":
            if self.fail_step == "q8_0":
                return 4
            src, dst, typ = a[1], a[2], a[3]
            Path(dst).write_bytes(self.expand(Path(src).read_bytes()[:64] + typ.encode()))
            return 0
        raise AssertionError(f"unexpected command: {argv}")


@pytest.fixture
def setup(tmp_path: Path):
    env = kit.build_env(tmp_path)
    snap = tmp_path / "snapshot"
    snap.mkdir()
    for n, data in kit.MODEL_FILES[kit.COSMOS_REPO].items():
        (snap / n).write_bytes(data)
    src = tmp_path / "llama.cpp-b11381"
    src.mkdir()
    conv = src / "convert_hf_to_gguf.py"
    conv.write_bytes(kit.payload("convert_hf_to_gguf.py", 500))
    rt = runtime.verify_runtime(
        env.pins, archive_dir=env.archive_dir, runtime_dir=env.runtime_dir, repo_root=env.repo_root
    )
    return env, snap, conv, rt, tmp_path / "out"


def _run(setup, tools: FakeTools, **kw):
    env, snap, conv, rt, out = setup
    return convert.convert_model(
        kw.pop("snapshot", snap),
        kw.pop("out_dir", out),
        runtime=rt,
        pins=env.pins,
        python=sys.executable,
        converter=kw.pop("converter", conv),
        runner=tools,
        repo_root=env.repo_root,
        **kw,
    )


@pytest.mark.req("FR-015-05")
def test_the_commands_run_in_order_with_the_documented_interface(setup) -> None:
    env, snap, conv, rt, out = setup  # noqa: RUF059
    tools = FakeTools()
    res = _run(setup, tools)
    assert len(tools.calls) == 3
    text, proj, quant = tools.calls
    for argv in (text, proj):
        assert argv[0] == sys.executable
        assert str(conv) in argv
        assert str(snap) in argv
        assert argv[argv.index("--outtype") + 1] == "f16"
    assert "--mmproj" not in text
    assert "--mmproj" in proj
    assert Path(text[text.index("--outfile") + 1]) == res.f16
    assert Path(proj[proj.index("--outfile") + 1]) == res.mmproj
    assert Path(quant[0]) == rt.executable("llama-quantize.exe")
    assert quant[1:] == [
        str(res.f16),
        str(res.q8_0),
        "Q8_0",
    ]  # llama-quantize <in> <out> <type>: from the text model, not the projector
    assert len({res.f16, res.mmproj, res.q8_0}) == 3
    assert all(p.parent == out for p in (res.f16, res.mmproj, res.q8_0))


@pytest.mark.req("FR-015-05")
def test_the_sha256_of_every_output_is_recorded(setup) -> None:
    env, snap, conv, rt, out = setup  # noqa: RUF059
    res = _run(setup, FakeTools())
    for key, path in (("f16", res.f16), ("mmproj", res.mmproj), ("q8_0", res.q8_0)):
        assert path.is_file()
        assert res.sha256[key] == hashlib.sha256(path.read_bytes()).hexdigest()
    record = json.loads((out / "conversion.json").read_text(encoding="utf-8"))
    for key in ("f16", "mmproj", "q8_0"):
        assert record[key] == res.sha256[key]
    assert len(set(res.sha256.values())) == 3


@pytest.mark.req("FR-015-05")
@pytest.mark.req("P-015-12")
def test_a_second_conversion_of_the_same_inputs_gives_identical_digests(setup, tmp_path: Path) -> None:
    a = _run(setup, FakeTools(), out_dir=tmp_path / "out-a")
    b = _run(setup, FakeTools(), out_dir=tmp_path / "out-b")
    assert a.sha256 == b.sha256
    assert a.f16.read_bytes() == b.f16.read_bytes()
    assert a.q8_0.read_bytes() == b.q8_0.read_bytes()


@pytest.mark.req("P-015-12")
def test_different_weights_give_different_digests(setup, tmp_path: Path) -> None:
    env, snap, conv, rt, out = setup  # noqa: RUF059
    base = _run(setup, FakeTools(), out_dir=tmp_path / "out-a")
    other = tmp_path / "other-snapshot"
    other.mkdir()
    for n, data in kit.MODEL_FILES[kit.COSMOS_REPO].items():
        (other / n).write_bytes(data)
    # a snapshot that differs from the pins is refused (below); here the pins describe the other bytes as well
    w = other / "model.safetensors"
    w.write_bytes(w.read_bytes()[:-1] + b"\x01")
    pins = json.loads(json.dumps(env.pins))
    pins["models"]["cosmos"]["files"]["model.safetensors"] = {
        "sha256": hashlib.sha256(w.read_bytes()).hexdigest(),
        "bytes": w.stat().st_size,
    }
    res = convert.convert_model(
        other,
        tmp_path / "out-b",
        runtime=rt,
        pins=pins,
        python=sys.executable,
        converter=conv,
        runner=FakeTools(),
        repo_root=env.repo_root,
    )
    assert res.sha256["f16"] != base.sha256["f16"]
    assert res.sha256["q8_0"] != base.sha256["q8_0"]


@pytest.mark.req("FR-015-05")
def test_a_snapshot_file_that_differs_from_the_pin_is_refused_before_any_command(setup) -> None:
    env, snap, conv, rt, out = setup  # noqa: RUF059
    f = snap / "model.safetensors"
    f.write_bytes(f.read_bytes() + b"x")
    tools = FakeTools()
    with pytest.raises(hub.ProvenanceError):
        _run(setup, tools)
    assert tools.calls == []
    assert not out.exists() or not any(out.iterdir())


@pytest.mark.req("FR-015-05")
@pytest.mark.parametrize("how", ["altered", "missing"])
def test_a_converter_script_that_differs_from_its_pin_is_refused_naming_it_before_any_command(setup, how: str) -> None:
    env, snap, conv, rt, out = setup  # noqa: RUF059
    if how == "altered":
        conv.write_bytes(conv.read_bytes() + b"# patched\n")
    else:
        conv.unlink()
    tools = FakeTools()
    with pytest.raises(runtime.PinError) as exc:
        _run(setup, tools)
    assert exc.value.file == "convert_hf_to_gguf.py"
    assert tools.calls == []


@pytest.mark.req("FR-015-06")
def test_the_output_folder_must_lie_outside_the_repository(setup) -> None:
    env, *_ = setup
    tools = FakeTools()
    with pytest.raises(convert.ConversionError) as exc:
        _run(setup, tools, out_dir=env.repo_root / "models" / "gguf")
    assert exc.value.step == "inputs"
    assert tools.calls == []
    assert not (env.repo_root / "models").exists()


@pytest.mark.req("FR-015-05")
@pytest.mark.parametrize(("fail", "ran"), [("f16", 1), ("mmproj", 2), ("q8_0", 3)])
def test_a_failing_tool_stops_the_pipeline_with_the_failing_step(setup, fail: str, ran: int) -> None:
    tools = FakeTools(fail_step=fail)
    with pytest.raises(convert.ConversionError) as exc:
        _run(setup, tools)
    assert exc.value.step == fail
    assert len(tools.calls) == ran  # nothing runs after the failure


@pytest.mark.req("FR-015-05")
def test_q8_0_blocks_hold_32_weights_in_34_bytes() -> None:
    assert convert.q8_0_tensor_bytes(32) == 34  # one block: fp16 scale (2 bytes) + 32 int8 weights
    assert convert.q8_0_tensor_bytes(0) == 0
    assert convert.q8_0_tensor_bytes(2_048 * 2_048) == 2_048 * 2_048 // 32 * 34
    assert 8 * convert.q8_0_tensor_bytes(32_000) / 32_000 == pytest.approx(8.5, abs=1e-12)  # 8.5 bits per weight


@pytest.mark.req("FR-015-05")
@pytest.mark.parametrize("n", [-32, 1, 31, 33, 100, 2**31 + 1])
def test_a_tensor_that_is_not_a_whole_number_of_blocks_is_refused(n: int) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        convert.q8_0_tensor_bytes(n)


@pytest.mark.req("FR-015-05")
@given(st.integers(0, 10**8))
def test_property_q8_0_size_is_34_32nds_of_the_weight_count(blocks: int) -> None:
    assert convert.q8_0_tensor_bytes(32 * blocks) == 34 * blocks
