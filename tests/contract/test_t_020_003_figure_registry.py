"""T-020-003: figure registry schema, generated types and tools/check_figures.py.

Requirements: DC-020-04, FR-020-09, FR-020-10, FR-020-16.

Spec: specs/020-web-knowledge/ (spec.md, plan.md, tasks.md; draft schemas and the example corpus in contracts/).

Oracle: the spec's own example corpus (`contracts/examples/index*.json`: every `valid` example is accepted, every
hostile example is rejected at its stated JSON pointer and keyword), the JSON Schema 2020-12 meta-schema (reference
implementation `jsonschema`), and, for generated types, the Pydantic and TypeScript compilers. See
tests/contract/_contract_kit.py for the exact assertions.

Expected API of the implementation (promotion of the drafts, then generation):
- `contracts/figures.schema.json` (JSON Schema 2020-12, `$id` https://fsantibanezleal.github.io/PitStudio/contracts/figures.schema.json)
- `src/pitstudio/contracts/_generated/<stem>.py` (Pydantic v2, header, extra=forbid) and
  `web/src/contracts/generated/<stem>.ts` (type-only, banner) for each schema, from `tools/gen_types.py` and
  `web/scripts/gen-types.mjs` (spec 001, FR-001-40, FR-001-41).
"""

from __future__ import annotations

import _contract_kit as kit
import pytest
import yaml

SPEC = "020-web-knowledge"


@pytest.mark.req("DC-020-04")
def test_figures_schema_is_promoted_and_valid_2020_12() -> None:
    kit.assert_schema_promoted("figures.schema.json")


@pytest.mark.req("DC-020-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["figures.schema.json"], valid=True))
def test_figures_valid_example_is_accepted(ex: dict) -> None:
    kit.assert_valid_example(ex)


@pytest.mark.req("DC-020-04")
@pytest.mark.parametrize("ex", kit.example_params(SPEC, ["figures.schema.json"], valid=False))
def test_figures_hostile_example_is_rejected_at_its_pointer(ex: dict) -> None:
    kit.assert_hostile_example(ex)


@pytest.mark.req("DC-020-04")
def test_figures_generated_pydantic_model_round_trips_valid_examples() -> None:
    kit.assert_generated_python(SPEC, ["figures.schema.json"])


@pytest.mark.req("DC-020-04")
def test_figures_generated_typescript_type_checks_valid_examples() -> None:
    kit.assert_generated_typescript(SPEC, ["figures.schema.json"])


def _figures(name: str) -> dict:
    ex = next(e for e in kit.load_examples(SPEC, ["figures.schema.json"]) if e["file"] == name)
    return kit.read_json(ex["path"])


def _root(tmp_path, doc: dict, pages: dict[str, str] | None = None, binaries: dict[str, bytes] | None = None):
    root = tmp_path / "repo"
    f = root / "web" / "src" / "theory" / "figures.yaml"
    f.parent.mkdir(parents=True)
    f.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    for rel, text in (pages or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    for rel, data in (binaries or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    return root


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


@pytest.mark.req("DC-020-04")
@pytest.mark.parametrize("name", ["figures.valid.json", "figures.valid-3d.json"])
def test_check_figures_accepts_the_valid_registries(tmp_path, name: str) -> None:
    # Expected CLI: `python tools/check_figures.py [--root DIR]` reads <root>/web/src/theory/figures.yaml and scans the
    # Markdown pages under <root>/docs/ for raster images; exit 0 clean, 1 on findings (each names the figure id or the
    # file), 2 on usage error; never a traceback.
    code, out = kit.run_tool("check_figures.py", "--root", str(_root(tmp_path, _figures(name))))
    assert code == 0, out
    code, out = kit.run_tool("check_figures.py")
    assert code == 0, out


@pytest.mark.req("FR-020-09")
def test_check_figures_rejects_a_3d_figure_without_a_justification(tmp_path) -> None:
    doc = _figures("figures.valid-3d.json")
    fig = doc["figures"][0]
    assert fig["plot"] == "3d"
    del fig["justification3d"]
    code, out = kit.run_tool("check_figures.py", "--root", str(_root(tmp_path, doc)))
    assert code == 1, out
    assert fig["id"] in out
    assert "Traceback" not in out


@pytest.mark.req("FR-020-10")
@pytest.mark.parametrize("colormap", ["jet", "rainbow", "hsv", "turbo", "custom-gradient"])
def test_check_figures_rejects_colour_maps_other_than_the_four_perceptual_ones(tmp_path, colormap: str) -> None:
    doc = _figures("figures.valid-3d.json")
    fig = doc["figures"][0]
    fig["colormap"] = colormap
    code, out = kit.run_tool("check_figures.py", "--root", str(_root(tmp_path, doc)))
    assert code == 1, out
    assert fig["id"] in out
    assert "Traceback" not in out


@pytest.mark.req("FR-020-10")
@pytest.mark.parametrize("colormap", ["viridis", "cividis", "inferno", "magma"])
def test_check_figures_accepts_the_four_perceptual_colour_maps(tmp_path, colormap: str) -> None:
    doc = _figures("figures.valid-3d.json")
    doc["figures"][0]["colormap"] = colormap
    code, out = kit.run_tool("check_figures.py", "--root", str(_root(tmp_path, doc)))
    assert code == 0, out


@pytest.mark.req("FR-020-16")
def test_check_figures_rejects_a_raster_chart_on_a_theory_page_naming_the_file(tmp_path) -> None:
    page = "# Pit shells\n\n![shell chart](pit-shell-chart.png)\n"
    root = _root(
        tmp_path,
        _figures("figures.valid.json"),
        pages={"docs/theory/pit-shells.md": page},
        binaries={"docs/theory/pit-shell-chart.png": PNG},
    )
    code, out = kit.run_tool("check_figures.py", "--root", str(root))
    assert code == 1, out
    assert "pit-shell-chart.png" in out
    assert "Traceback" not in out


@pytest.mark.req("FR-020-16")
def test_check_figures_accepts_a_markdown_page_without_raster_images(tmp_path) -> None:
    root = _root(
        tmp_path, _figures("figures.valid.json"), pages={"docs/theory/pit-shells.md": "# Pit shells\n\nText only.\n"}
    )
    code, out = kit.run_tool("check_figures.py", "--root", str(root))
    assert code == 0, out
