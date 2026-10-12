"""T-018-001: case registry schema, generated types, studio/cases.yaml and tools/check_cases.py cross-checks.

Requirements: DC-018-01, FR-018-10.

Spec: specs/018-web-cases/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/cases.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/cases.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest

SPEC = "018-web-cases"


@pytest.mark.req("DC-018-01")
def test_cases_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("cases.schema.json")


@pytest.mark.req("DC-018-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["cases.schema.json"], valid=True))
def test_cases_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-018-01")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["cases.schema.json"], valid=False))
def test_cases_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-018-01")
def test_cases_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["cases.schema.json"])


@pytest.mark.req("DC-018-01")
def test_cases_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["cases.schema.json"])


STUDIO_TOOLS_17 = [
    # data-model 001 section 4.3, first 17 rows (the studio tools; the other three are evaluated-not-adopted)
    "openusd",
    "warp",
    "newton",
    "mujoco-warp",
    "physx-ovphysx",
    "ovrtx",
    "isaac-sim-replicator",
    "isaac-lab",
    "kit-usd-composer-explorer",
    "cosmos-reason-2",
    "pytorch",
    "onnx-runtime",
    "tensorrt",
    "nvenc-ffmpeg",
    "nsight-nvml",
    "threejs-r3f-3d-tiles",
    "rapier-webgpu-pyodide",
]
CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]  # spec 018 FR-018-09: 12 cases


def _cases_doc() -> dict:
    return kit.load_yaml_strict(kit.ROOT / "studio" / "cases.yaml")


@pytest.mark.req("DC-018-01")
def test_cases_yaml_validates_against_the_promoted_schema() -> None:
    doc = _cases_doc()
    assert kit.validation_errors("cases.schema.json", "#", doc) == []


@pytest.mark.req("DC-018-01")
def test_cases_yaml_holds_the_twelve_cases_each_in_its_own_category() -> None:
    doc = _cases_doc()
    assert sorted(doc["cases"]) == sorted(CASE_IDS)
    for cid, case in doc["cases"].items():
        assert case["category"] == cid[0], f"{cid}: category must be {cid[0]}"
        assert case["recipe"] == f"studio/recipes/cases/{cid.lower()}.yaml"
    assert sorted(doc["categories"]) == ["A", "B", "C", "D", "E"]


@pytest.mark.req("FR-018-10")
def test_cases_yaml_covers_every_method_and_every_studio_tool() -> None:
    cases = _cases_doc()["cases"].values()
    methods = {m for c in cases for m in c["methods"]}
    assert methods == {f"M{i}" for i in range(1, 24)}, "every method M1-M23 must appear in at least one case"
    tools = {t for c in cases for t in c["tools"]}
    assert set(STUDIO_TOOLS_17) <= tools, f"tools in no case: {sorted(set(STUDIO_TOOLS_17) - tools)}"


def _fixture_root(tmp_path, mutate=None, raw_cases_text: str | None = None):
    """A repository copy holding only what `tools/check_cases.py --root` reads, with a mutated cases.yaml."""
    import yaml

    root = tmp_path / "repo"
    for rel in ("studio/cases.yaml", "studio/tools.yaml", "studio/methods.yaml", "data/sources.yaml"):
        src = kit.ROOT / rel
        if src.is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(src.read_bytes())
    kit.copy_tree(kit.ROOT / "contracts", root / "contracts")
    doc = _cases_doc()
    if mutate is not None:
        mutate(doc)
    text = raw_cases_text if raw_cases_text is not None else yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    (root / "studio" / "cases.yaml").write_text(text, encoding="utf-8")
    return root


@pytest.mark.req("FR-018-10")
def test_check_cases_accepts_the_committed_registry(tmp_path) -> None:
    # Expected CLI: `python tools/check_cases.py [--root DIR]`; exit 0 clean, 1 on findings (one line each, naming the
    # offending id), 2 on usage error; never a traceback.
    code, out = kit.run_tool("check_cases.py", "--root", str(_fixture_root(tmp_path)))
    assert code == 0, out
    code, out = kit.run_tool("check_cases.py")
    assert code == 0, out


def _drop_method(doc: dict) -> None:
    for c in doc["cases"].values():
        c["methods"] = [m for m in c["methods"] if m != "M7"]


def _drop_tool(doc: dict) -> None:
    for c in doc["cases"].values():
        c["tools"].pop("warp", None)


def _unknown_method(doc: dict) -> None:
    doc["cases"]["A1"]["methods"].append("M24")


def _unknown_tool(doc: dict) -> None:
    doc["cases"]["A1"]["tools"]["no-such-tool"] = "named"


def _unknown_source(doc: dict) -> None:
    doc["cases"]["A1"]["sources"].append("no-such-source")


def _unknown_engine(doc: dict) -> None:
    doc["cases"]["A1"]["engines"].append("no-such-engine")


def _outside_categories(doc: dict) -> None:
    case = doc["cases"].pop("E2")
    case["category"] = "F"
    doc["cases"]["F1"] = case


@pytest.mark.req("FR-018-10")
@pytest.mark.parametrize(
    ("mutate", "offending"),
    [
        pytest.param(_drop_method, "M7", id="method-left-out-of-every-case"),
        pytest.param(_drop_tool, "warp", id="studio-tool-left-out-of-every-case"),
        pytest.param(_unknown_method, "M24", id="unknown-method"),
        pytest.param(_unknown_tool, "no-such-tool", id="unknown-tool"),
        pytest.param(_unknown_source, "no-such-source", id="unknown-source"),
        pytest.param(_unknown_engine, "no-such-engine", id="unknown-engine"),
        pytest.param(_outside_categories, "F1", id="case-outside-categories-A-to-E"),
    ],
)
def test_check_cases_fails_and_names_the_offending_id(tmp_path, mutate, offending: str) -> None:
    code, out = kit.run_tool("check_cases.py", "--root", str(_fixture_root(tmp_path, mutate)))
    assert code == 1, out
    assert offending in out, f"the finding must name {offending!r}: {out[:400]}"
    assert "Traceback" not in out


@pytest.mark.req("FR-018-10")
def test_check_cases_fails_on_a_repeated_case_id(tmp_path) -> None:
    import yaml

    doc = _cases_doc()
    head = yaml.safe_dump({k: v for k, v in doc.items() if k != "cases"}, sort_keys=False, allow_unicode=True)
    blocks = [yaml.safe_dump({cid: case}, sort_keys=False, allow_unicode=True) for cid, case in doc["cases"].items()]
    blocks.append(blocks[0])  # A1 twice
    body = "cases:\n" + "".join("".join("  " + ln + "\n" for ln in b.splitlines()) for b in blocks)
    root = _fixture_root(tmp_path, raw_cases_text=head + body)
    code, out = kit.run_tool("check_cases.py", "--root", str(root))
    assert code == 1, out
    assert "A1" in out
    assert "Traceback" not in out
