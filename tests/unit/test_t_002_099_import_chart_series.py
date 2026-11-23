# ruff: noqa: PT018, F811
"""T-002-099: `studio import-run` accepts outputs of kind `chart-series` (FR-002-70).

Oracles: the chart-series contract (contracts/chart-series.schema.json, valid and hostile examples of its corpus), the
run manifest contract, the byte cap of DC-020-05 (524,288), and the file digests the test wrote. The publish path of
spec 002 is then applied to the imported run: the published manifest lists the file as an artefact of kind
`chart-series`.
"""

from __future__ import annotations

import copy
import json
import pytest
from test_import_run import JOB, ROOT, World, manifest_of, sha, world  # noqa: F401  (the fixture is used by name)

from pitstudio.runner import publish
from pitstudio.runner.recipe import Usage, first_errors

EXAMPLES = ROOT / "specs" / "020-web-knowledge" / "contracts" / "examples"
VALID = json.loads((EXAMPLES / "chart-series.valid-bar-error-bars.json").read_text(encoding="utf-8"))


def chart(**changes: object) -> dict:
    doc = copy.deepcopy(VALID)
    doc.update(case="C1", **changes)
    return doc


def with_chart(w: World, doc: dict, name: str = "chart.json", **output: object) -> dict:
    (w.src / name).write_text(json.dumps(doc), encoding="utf-8")
    spec = w.doc()
    spec["stages"][0]["outputs"].append(
        {
            "name": name,
            "from": name,
            "kind": "chart-series",
            "budget_class": "studio-showcase",
            "publish": True,
            "media_type": "application/json",
            "licence_class": "own",
            "spdx": "CC-BY-4.0",
            **output,
        }
    )
    return spec


@pytest.mark.req("FR-002-70")
def test_a_valid_chart_series_output_is_imported_and_listed_in_the_import_record(world: World) -> None:
    code, err = world.run(with_chart(world, chart()))
    assert code == 0, err
    m = manifest_of(world)
    assert first_errors("manifest", m, "#/$defs/run", n=3) == []
    (run,) = world.runs()
    rec = json.loads((run / "import.json").read_text(encoding="utf-8"))
    out = next(o for o in rec["outputs"] if o["name"] == "chart.json")
    assert out["kind"] == "chart-series"
    assert out["sha256"] == sha((world.src / "chart.json").read_bytes())


@pytest.mark.req("FR-002-70")
@pytest.mark.parametrize(
    ("label", "mutate", "needle"),
    [
        ("a schema violation", lambda d: d.pop("producer"), "producer"),
        ("a missing unit", lambda d: d["y_axis"].pop("unit"), "unit"),
        ("a series shorter than its categories", lambda d: d["series"][0].update(y=[1.0, 2.0]), "categories"),
        ("a band shorter than its series", lambda d: d["series"][0].update(lo=[1.0]), "lo"),
        ("a case that is not the case of the import", lambda d: d.update(case="A3"), "case"),
    ],
)
def test_an_invalid_chart_series_is_refused_before_the_first_write(
    world: World, label: str, mutate, needle: str
) -> None:
    doc = chart()
    mutate(doc)
    code, err = world.run(with_chart(world, doc))
    assert code == 2, f"{label} must be refused: {err}"
    assert needle in err
    assert world.runs() == []


@pytest.mark.req("FR-002-70")
def test_a_chart_series_over_the_byte_cap_is_refused(world: World) -> None:
    doc = chart(
        chart_type="line",
        x_axis={"label": {"en": "x", "es": "x"}, "unit": "1"},
        y_axis={"label": {"en": "y", "es": "y"}, "unit": "1"},
        series=[
            {
                "id": f"s{k}",
                "label": {"en": "s", "es": "s"},
                "x": [i + 0.123456789 for i in range(20000)],
                "y": [i * 1.987654321 for i in range(20000)],
            }
            for k in range(3)
        ],
    )
    doc.pop("categories")
    code, err = world.run(with_chart(world, doc))
    assert code == 2 and "524288" in err
    assert world.runs() == []


@pytest.mark.req("FR-002-70")
def test_a_line_chart_whose_x_goes_backwards_is_refused(world: World) -> None:
    doc = chart(
        chart_type="line",
        x_axis={"label": {"en": "x", "es": "x"}, "unit": "1"},
        y_axis={"label": {"en": "y", "es": "y"}, "unit": "1"},
        series=[{"id": "s", "label": {"en": "s", "es": "s"}, "x": [0, 2, 1], "y": [0, 1, 2]}],
    )
    doc.pop("categories")
    code, err = world.run(with_chart(world, doc))
    assert code == 2 and "x" in err
    assert world.runs() == []


@pytest.mark.req("FR-002-70")
def test_a_not_run_chart_series_is_imported_with_its_reason(world: World) -> None:
    doc = chart(chart_type="line", status="not-run", not_run_reason={"en": "no data", "es": "sin datos"})
    for key in ("categories", "series", "y_axis"):
        doc.pop(key, None)
    code, err = world.run(with_chart(world, doc))
    assert code == 0, err


@pytest.mark.req("FR-002-70")
def test_a_chart_series_with_an_absolute_path_is_not_published(world: World) -> None:
    doc = chart(caption={"en": "see C:\\Users\\someone\\data", "es": "ver C:\\Users\\someone\\data"})
    code, err = world.run(with_chart(world, doc))
    assert code == 0, err
    (run,) = world.runs()
    with pytest.raises(Usage, match="absolute path"):
        publish.publish(world.store, world.repo, run.name, None)


@pytest.mark.req("FR-002-70")
def test_the_published_manifest_lists_the_chart_series_artefact_of_its_case(world: World) -> None:
    code, err = world.run(with_chart(world, chart()))
    assert code == 0, err
    (run,) = world.runs()
    publish.publish(world.store, world.repo, run.name, None)
    index = json.loads((world.repo / "web" / "public" / "assets" / "manifest.json").read_text(encoding="utf-8"))
    art = next(a for a in index["artefacts"] if a["kind"] == "chart-series")
    assert art["cases"] == ["C1"] and art["lane"] == "static" and art["budget_class"] == "studio-showcase"
    assert art["media_type"] == "application/json"
    published = world.repo / "web" / "public" / art["path"]
    assert sha(published.read_bytes()) == art["sha256"]
    assert JOB in " ".join(manifest_of(world)["notes"])
