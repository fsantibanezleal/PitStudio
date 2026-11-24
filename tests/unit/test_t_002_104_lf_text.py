# ruff: noqa: PT018, F811
"""T-002-104: text outputs of an import are stored and published with LF line ends (FR-002-74).

Oracle: the bytes the test writes (a JSON file with CRLF line ends, as Python writes it on Windows) and the rule that a
published digest must equal the digest of the file a clean checkout holds (git keeps text with LF); a binary output is
never touched.
"""

from __future__ import annotations

import json

import pytest
from test_import_run import World, sha, world  # noqa: F401  (the fixture is used by name)

from pitstudio.runner import publish

CRLF = b'{\r\n "metric": 0.5,\r\n "budget": {"total_gpu_hours": 0.374}\r\n}\r\n'
LF = CRLF.replace(b"\r\n", b"\n")


@pytest.mark.req("FR-002-74")
def test_a_text_output_with_crlf_is_recorded_and_published_with_lf(world: World) -> None:
    (world.src / "result.json").write_bytes(CRLF)
    assert world.run()[0] == 0
    (run,) = world.runs()
    rec = json.loads((run / "import.json").read_text(encoding="utf-8"))
    out = next(o for o in rec["outputs"] if o["name"] == "result.json")
    assert out["sha256"] == sha(LF)
    publish.publish(world.store, world.repo, run.name, None)
    published = next((world.repo / "web/public/assets" / run.name).glob("result.json"))
    assert published.read_bytes() == LF


@pytest.mark.req("FR-002-74")
def test_a_binary_output_keeps_its_bytes_even_with_crlf_inside(world: World) -> None:
    model = b"onnx\r\nbytes" * 50
    (world.src / "sub" / "model.onnx").write_bytes(model)
    assert world.run()[0] == 0
    (run,) = world.runs()
    rec = json.loads((run / "import.json").read_text(encoding="utf-8"))
    assert next(o for o in rec["outputs"] if o["name"] == "model.onnx")["sha256"] == sha(model)


@pytest.mark.req("FR-002-74")
def test_a_pinned_digest_is_checked_against_the_lf_form(world: World) -> None:
    (world.src / "result.json").write_bytes(CRLF)
    spec = world.doc()
    spec["stages"][0]["outputs"][0]["sha256"] = sha(LF)
    assert world.run(spec)[0] == 0
