# ruff: noqa: E501
"""T-015-094: fixture propagation through the VLM stages and the scorer: `fixture: true` on every record and metric, no accuracy claim, nothing published.

Requirements: FR-015-50.

Spec: specs/015-vlm/spec.md FR-015-50 ("While a frame-state set or query set (DC-015-01, DC-015-02) is a contract fixture, the `st59_*` stages and the scorer shall run
against it, shall write `fixture: true` on every record and metric, and shall compute and publish no accuracy claim from it"); plan.md test strategy row FR-015-50
("a fixture query set gives records and a metrics table `fixture: true` and the publish step drops them"). Convention of spec 008 (FR-008-49): a source is a fixture
when asked to be (`fixture=True`) or when its file lies under a fixture folder; for spec 015 the fixture folders are `specs/*/contracts/examples/`, `tests/` and
`data/samples/` of the repository (the contract examples are the contract fixtures of DC-015-01 and DC-015-02).

Oracle: the spec's own contract example (`specs/015-vlm/contracts/examples/vlm-queries.valid.json`, a contract fixture by location); hand-built query sets and frame states
whose answers a fake driver gives by construction (half right, half wrong, so that a real run has a balanced accuracy of 0.5 and a fixture run must report none); counting
of marked records.

Expected API of the implementation (package `pitstudio`, root environment):
- `pitstudio.reason.fixture.is_fixture(path, *, fixture=None, repo_root) -> bool`: True when `fixture is True`, or when `path` lies under one of the fixture folders of
  `repo_root`; `fixture` must be a bool or None (TypeError otherwise); False otherwise.
- `pitstudio.reason.fixture.publishable(items) -> list[dict]`: the items (records or metrics tables) not marked `fixture: true`.
  `pitstudio.reason.fixture.assert_publishable(obj) -> None`: ValueError (naming "fixture") when the record or metrics table is marked `fixture: true`.
- `pitstudio.reason.vqa.run_task_a(queries, frames, *, driver, arm, prompts, out_dir, source_path, repo_root, fixture=None) -> dict`: runs the queries of one arm through
  `driver.ask(request: dict) -> QueryResult` (one request per query; `QueryResult` has `status`, `text`, `top_logprobs`, `attempts` as in
  tests/pipeline/test_t_015_016_server_driver.py), parses the answers, and writes `out_dir / "records.jsonl"` (one JSON record per query with `query_id`, `arm`,
  `question_type`, `condition`, `output`, `parsed`, `truth`, `correct`) and `out_dir / "metrics.json"` (`{"fixture": bool, "rows": [...]}`, one row per question type with
  `arm`, `type`, `n`, `balanced_accuracy`, `f1`, `auroc`). The run is a fixture run when `is_fixture(source_path, fixture=fixture, repo_root=repo_root)`; then every record
  carries `"fixture": true`, `metrics.json` carries `"fixture": true` and every row `"fixture": true` with `balanced_accuracy`, `f1` and `auroc` all None (no accuracy is
  computed). Otherwise no record or row is marked and the rows hold the measured values (`balanced_accuracy` a float from `pitstudio.reason.stats`). Returns
  `{"fixture": bool, "n_records": int, "records_path": Path, "metrics_path": Path}`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from pitstudio.reason import fixture as fx
from pitstudio.reason import vqa

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _p015_kit as kit

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "specs" / "015-vlm" / "contracts" / "examples" / "vlm-queries.valid.json"
PROMPTS = {
    "system": "You are a vision assistant. Reply inside <answer></answer>.",
    **{f"task_a_type_{t}": f"Question type {t}. Reply inside <answer></answer>." for t in range(1, 7)},
}


@dataclass
class Result:
    status: str = "ok"
    text: str = ""
    top_logprobs: dict | None = None
    attempts: int = 1


class FakeDriver:
    """Answers each query by its position: even positions right, odd positions wrong (truth is known from the query list)."""

    def __init__(self, queries: list[dict]) -> None:
        self.calls: list[dict] = []
        self._truth = [q["truth"] for q in queries]

    def ask(self, request: dict) -> Result:
        n = len(self.calls)
        self.calls.append(request)
        truth = self._truth[n]
        wrong = {"yes": "no", "no": "yes"}.get(truth, "0")
        ans = truth if n % 2 == 0 else wrong
        return Result(text=f"<answer>{ans}</answer>", top_logprobs={"yes": -0.2, "no": -1.7})


def _data(n: int = 40) -> tuple[dict, dict]:
    frames = {}
    queries = []
    for i in range(n):
        fid = f"b2-pit-s0001-f{i:04d}"
        frames[fid] = kit.frame_state(
            [kit.truck(100.0, 0.0), kit.person(110.0, 5.0)],
            frame_id=fid,
            condition=["day", "night", "dust", "rain"][i % 4],
        )
        queries.append(
            {
                "query_id": f"q{i:04d}",
                "frame_id": fid,
                "frame_state_sha256": kit.canonical_sha256(frames[fid]),
                "type": 1,
                "condition": frames[fid]["condition"],
                "location": "haul_road",
                "truth": "yes"
                if i % 4 < 2
                else "no",  # i even: driver right, i odd: wrong; yes/no balanced within each parity class
                "gate_subset": False,
                "reasoning_subset": False,
            }
        )
    return {"schema_version": "1.0", "seed": 1, "source_run_id": "20261012T013000Z-b2", "queries": queries}, frames


def _run(tmp_path: Path, **kw) -> dict:
    qs, frames = _data()
    drv = FakeDriver(qs["queries"])
    out = tmp_path / "out"
    res = vqa.run_task_a(qs, frames, driver=drv, arm="qwen-base", prompts=PROMPTS, out_dir=out, repo_root=ROOT, **kw)
    assert len(drv.calls) == len(qs["queries"])
    return res


def _records(res: dict) -> list[dict]:
    return [json.loads(x) for x in Path(res["records_path"]).read_text(encoding="utf-8").splitlines() if x.strip()]


# ------------------------------------------------------------------------------------------------ detection
@pytest.mark.req("FR-015-50")
def test_the_contract_example_is_a_fixture_by_location() -> None:
    assert EXAMPLE.is_file()
    assert fx.is_fixture(EXAMPLE, repo_root=ROOT) is True


@pytest.mark.req("FR-015-50")
@pytest.mark.parametrize(
    "rel", ["tests/unit/data.json", "data/samples/q.json", "specs/012-fragmentation/contracts/examples/x.json"]
)
def test_the_fixture_folders_are_the_examples_the_samples_and_the_tests(rel: str) -> None:
    assert fx.is_fixture(ROOT / rel, repo_root=ROOT) is True


@pytest.mark.req("FR-015-50")
@pytest.mark.parametrize(
    "rel",
    [
        "data/reason/task_a/queries.json",
        "src/pitstudio/x.json",
        "specs/015-vlm/spec.md",
        "data/samples_extra/q.json",
        "web/tests_data/q.json",
    ],
)
def test_a_real_input_is_not_a_fixture(rel: str) -> None:
    assert fx.is_fixture(ROOT / rel, repo_root=ROOT) is False


@pytest.mark.req("FR-015-50")
def test_the_flag_forces_a_fixture_and_a_non_bool_flag_is_refused(tmp_path: Path) -> None:
    p = tmp_path / "queries.json"
    assert fx.is_fixture(p, repo_root=ROOT, fixture=True) is True
    assert fx.is_fixture(p, repo_root=ROOT, fixture=None) is False
    assert fx.is_fixture(p, repo_root=ROOT, fixture=False) is False
    for bad in ("yes", 1, 0.0, [], {}):
        with pytest.raises(TypeError):
            fx.is_fixture(p, repo_root=ROOT, fixture=bad)  # type: ignore[arg-type]


@pytest.mark.req("FR-015-50")
def test_a_path_that_climbs_out_of_a_fixture_folder_is_not_a_fixture() -> None:
    sneaky = ROOT / "tests" / ".." / "data" / "reason" / "q.json"
    assert fx.is_fixture(sneaky, repo_root=ROOT) is False


# ------------------------------------------------------------------------------------------------ the run
@pytest.mark.req("FR-015-50")
def test_a_fixture_run_marks_every_record_and_every_metric_and_computes_no_accuracy(tmp_path: Path) -> None:
    res = _run(tmp_path, source_path=EXAMPLE)
    assert res["fixture"] is True
    recs = _records(res)
    assert len(recs) == res["n_records"] == 40
    assert all(r.get("fixture") is True for r in recs)
    metrics = json.loads(Path(res["metrics_path"]).read_text(encoding="utf-8"))
    assert metrics["fixture"] is True
    assert metrics["rows"]
    for row in metrics["rows"]:
        assert row["fixture"] is True
        assert (row["balanced_accuracy"], row["f1"], row["auroc"]) == (None, None, None)
        assert row["n"] > 0
    text = Path(res["metrics_path"]).read_text(encoding="utf-8")
    assert "verdict" not in text
    assert "beats" not in text.lower()


@pytest.mark.req("FR-015-50")
def test_the_flag_makes_a_run_of_a_real_looking_path_a_fixture_run(tmp_path: Path) -> None:
    res = _run(tmp_path, source_path=ROOT / "data" / "reason" / "task_a" / "queries.json", fixture=True)
    assert res["fixture"] is True
    assert all(r.get("fixture") is True for r in _records(res))


@pytest.mark.req("FR-015-50")
def test_a_real_run_marks_nothing_and_reports_the_measured_accuracy(tmp_path: Path) -> None:
    res = _run(tmp_path, source_path=ROOT / "data" / "reason" / "task_a" / "queries.json")
    assert res["fixture"] is False
    recs = _records(res)
    assert len(recs) == 40
    assert not any(r.get("fixture") for r in recs)
    metrics = json.loads(Path(res["metrics_path"]).read_text(encoding="utf-8"))
    assert not metrics.get("fixture")
    (row,) = metrics["rows"]
    assert not row.get("fixture")
    assert isinstance(row["balanced_accuracy"], float)
    assert row["balanced_accuracy"] == pytest.approx(
        0.5, abs=1e-12
    )  # half the answers are right in each true class by construction


@pytest.mark.req("FR-015-50")
def test_the_records_of_a_fixture_run_still_hold_the_parsed_answers_and_truth(tmp_path: Path) -> None:
    """A fixture run exercises the code path completely: only the claims are withheld."""
    recs = _records(_run(tmp_path, source_path=EXAMPLE))
    assert {r["parsed"] for r in recs} == {"yes", "no"}
    assert all(r["arm"] == "qwen-base" and r["question_type"] == 1 for r in recs)
    assert all(isinstance(r["correct"], bool) for r in recs)


# ------------------------------------------------------------------------------------------------ the publish step
@pytest.mark.req("FR-015-50")
def test_the_publish_step_drops_every_fixture_record_and_metric_table(tmp_path: Path) -> None:
    res = _run(tmp_path, source_path=EXAMPLE)
    recs = _records(res)
    metrics = json.loads(Path(res["metrics_path"]).read_text(encoding="utf-8"))
    assert fx.publishable(recs) == []
    assert fx.publishable([metrics]) == []
    mixed = [*recs[:3], {"query_id": "real-1", "correct": True}]
    assert fx.publishable(mixed) == [{"query_id": "real-1", "correct": True}]


@pytest.mark.req("FR-015-50")
def test_assert_publishable_refuses_fixture_output_and_accepts_real_output(tmp_path: Path) -> None:
    res = _run(tmp_path, source_path=EXAMPLE)
    metrics = json.loads(Path(res["metrics_path"]).read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="fixture"):
        fx.assert_publishable(metrics)
    with pytest.raises(ValueError, match="fixture"):
        fx.assert_publishable(_records(res)[0])
    fx.assert_publishable({"query_id": "q1", "correct": True})
    fx.assert_publishable({"fixture": False, "rows": []})
