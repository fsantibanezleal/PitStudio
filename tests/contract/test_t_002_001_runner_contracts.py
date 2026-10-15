# ruff: noqa: E501, PT018
"""T-002-001: the runner's contracts (profile, job spec + stage result, events + telemetry), the two committed machine
profiles, the profile loader's hostile cases, and the packaging facts the runner needs.

Requirements: DC-002-01, DC-002-02, DC-002-03, FR-002-44, FR-002-45.

Expected product facts (the implementer must provide):
  * contracts/profile.schema.json, contracts/job.schema.json, contracts/events.schema.json (promoted from
    specs/002-runner/contracts/), valid JSON Schema 2020-12, with `$id` https://fsantibanezleal.github.io/PitStudio/contracts/<stem>.schema.json;
  * generated pydantic modules src/pitstudio/contracts/_generated/{profile,job,events}.py;
  * studio/recipes/_profiles/laptop-rtx5000ada.yaml and linux-gpu.yaml equal to plan.md D4;
  * pyproject.toml: [project.scripts] studio = "pitstudio.runner.cli:main" and networkx in the `dev` dependency group;
  * `pitstudio.runner.cli.main(argv)` loads the profile named by --profile from studio/recipes/_profiles/ of the
    repository (PITSTUDIO_REPO or the checkout) and exits 2 with a one-line message naming the offending field.

Oracles: the spec's own valid/hostile corpus (specs/002-runner/contracts/examples/index.json), Python `jsonschema`
(reference validator), plan.md D4 written out by hand, the privacy patterns of spec 001 data-model 1.5.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
import schemas

ROOT = rw.ROOT
STEMS = ["profile", "job", "events"]
BASE_ID = "https://fsantibanezleal.github.io/PitStudio/contracts/"
INDEX = json.loads(
    (ROOT / "specs" / "002-runner" / "contracts" / "examples" / "index.json").read_text(encoding="utf-8")
)["examples"]
EX_DIR = ROOT / "specs" / "002-runner" / "contracts" / "examples"


def _related(expected: str, got: str) -> bool:
    """Draft pointers are JSON Pointers; anyOf wrappers report the parent, root errors report an empty pointer."""
    return got in ("", "/") or expected in ("", "/") or expected.startswith(got) or got.startswith(expected)


@pytest.mark.req("DC-002-01")
@pytest.mark.req("DC-002-02")
@pytest.mark.req("DC-002-03")
@pytest.mark.parametrize("stem", STEMS)
def test_dc_002_schemas_are_promoted_to_contracts_and_valid(stem: str) -> None:
    p = ROOT / "contracts" / f"{stem}.schema.json"
    assert p.is_file(), f"{p.relative_to(ROOT)} is not promoted from specs/002-runner/contracts/"
    doc = json.loads(p.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(doc)
    assert doc["$id"] == f"{BASE_ID}{stem}.schema.json"
    assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.req("DC-002-01")
@pytest.mark.req("DC-002-02")
@pytest.mark.req("DC-002-03")
@pytest.mark.req("FR-002-45")
@pytest.mark.parametrize("entry", INDEX, ids=[e["file"] for e in INDEX])
def test_dc_002_corpus_verdicts_hold_on_the_promoted_schemas(entry: dict[str, Any]) -> None:
    stem = entry["schema"].removesuffix(".schema.json")
    assert (ROOT / "contracts" / entry["schema"]).is_file(), "schema not promoted to contracts/"
    inst = json.loads((EX_DIR / entry["file"]).read_text(encoding="utf-8"))
    errs = list(schemas.validator(stem, entry["target"]).iter_errors(inst))
    if entry["valid"]:
        assert errs == [], [e.message for e in errs][:3]
    else:
        assert errs, f"{entry['file']} must be rejected ({entry.get('class')})"
        want = entry.get("pointer")
        if want is not None:
            got = ["/" + "/".join(str(x) for x in e.absolute_path) for e in errs]
            assert any(_related(want, g) for g in got), (want, got[:5])


# ---- the two committed machine profiles (plan.md D4, written out by hand) -------------------------------------------
LAPTOP = {
    "id": "laptop-rtx5000ada",
    "os": "windows",
    "gpus": [{"index": 0, "vram_bytes": 17179869184, "power_class": "laptop-power-limited"}],
    "cpu_slots": 8,
    "envs_enabled": {"studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"},
    "process_control": "job-object",
    "guards": {"vram_margin_gib": 1.5, "disk_margin_gib": 20, "max_start_temp_c": 80, "cooldown_wait_s": 600, "lock_wait_s": 3600},
    "telemetry_hz": 2,
    "keep_awake": True,
    "quotas": {"st55_sdg": 80, "st50_physics": 30},
    "binaries": {
        "ffmpeg": "PITSTUDIO_FFMPEG", "llama-cpp": "PITSTUDIO_LLAMA_CPP", "colmap": "PITSTUDIO_COLMAP",
        "brush": "PITSTUDIO_BRUSH", "kit-app": "PITSTUDIO_KIT_APP",
    },
}  # fmt: skip
LINUX = {
    "id": "linux-gpu",
    "os": "linux",
    "gpus": [],
    "cpu_slots": 8,
    "envs_enabled": {"studio", "pipeline", "accel", "external"},
    "process_control": "process-group",
    "guards": {
        "vram_margin_gib": 1.5,
        "disk_margin_gib": 20,
        "max_start_temp_c": 80,
        "cooldown_wait_s": 600,
        "lock_wait_s": 3600,
    },
    "telemetry_hz": 2,
    "keep_awake": False,
    "binaries": {"ffmpeg": "PITSTUDIO_FFMPEG"},
}


@pytest.mark.req("FR-002-44")
@pytest.mark.parametrize("expected", [LAPTOP, LINUX], ids=["laptop-rtx5000ada", "linux-gpu"])
def test_fr_002_44_committed_profiles_match_plan_d4(expected: dict[str, Any]) -> None:
    p = ROOT / "studio" / "recipes" / "_profiles" / f"{expected['id']}.yaml"
    assert p.is_file(), f"{p.relative_to(ROOT)} missing"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert schemas.errors("profile", doc) == []
    for k, v in expected.items():
        got = doc.get(k)
        if k == "envs_enabled":
            assert set(got) == v and len(got) == len(v)
        else:
            assert got == v, f"{k}: {got!r} != {v!r}"
    if "quotas" not in expected:
        assert "quotas" not in doc
    assert (
        re.fullmatch(r"[A-Z]:/[a-z0-9_-]{1,16}", doc["store_default"])
        if expected["os"] == "windows"
        else re.fullmatch(r"/(srv|data|scratch)/[a-z0-9_-]{1,32}", doc["store_default"])
    )


@pytest.mark.req("FR-002-44")
def test_fr_002_44_no_recipe_or_profile_holds_machine_specific_data() -> None:
    """Privacy patterns of spec 001 data-model 1.5 plus this process's host, user and home (reference strings)."""
    import getpass
    import socket

    files = sorted((ROOT / "studio" / "recipes").rglob("*.yaml"))
    assert len(files) >= 2, "the two profiles must exist under studio/recipes/_profiles/"
    drive = re.compile(r"[A-Za-z]:[\\/]")
    unc = re.compile(r"\\\\[A-Za-z0-9._$-]+\\")
    posix = re.compile(r"(^|[\s\"'=(,:])/(home|Users|root|tmp|var|mnt|media|opt|srv|private|run)/")
    identities = [x.lower() for x in (socket.gethostname(), getpass.getuser(), Path.home().name) if len(x) >= 3]

    def strings(o: Any) -> list[str]:
        if isinstance(o, str):
            return [o]
        if isinstance(o, dict):
            return [s for k, v in o.items() for s in strings(k) + strings(v)]
        if isinstance(o, list):
            return [s for v in o for s in strings(v)]
        return []

    for f in files:
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for s in strings(doc):
            if f.parent.name == "_profiles" and s in (doc.get("store_default"),):
                continue  # the documented short store root is machine-neutral by design (D4)
            assert not drive.search(s) and not unc.search(s) and not posix.search(s), (f.name, s)
            assert not any(i in s.lower() for i in identities), (f.name, s)


@pytest.mark.req("DC-002-01")
def test_runner_packaging_console_script_and_dev_dependency() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["studio"] == "pitstudio.runner.cli:main"
    dev = pyproject["dependency-groups"]["dev"]
    assert any(re.match(r"networkx\b", d) for d in dev), (
        "networkx (test-only reference implementation) missing from dev"
    )
    extras = pyproject["project"]["optional-dependencies"]["runner"]
    assert {re.split(r"[<>=]", e)[0] for e in extras} >= {"filelock", "psutil", "nvidia-ml-py"}


@pytest.mark.req("DC-002-01")
@pytest.mark.req("DC-002-02")
@pytest.mark.req("DC-002-03")
@pytest.mark.parametrize("stem", STEMS)
def test_dc_002_generated_models_exist_and_import(stem: str) -> None:
    p = ROOT / "src" / "pitstudio" / "contracts" / "_generated" / f"{stem}.py"
    assert p.is_file(), f"{p.relative_to(ROOT)} not generated"
    head = p.read_text(encoding="utf-8").splitlines()[0]
    assert head.startswith(f"# Generated from contracts/{stem}.schema.json by tools/gen_types.py")
    sys.path.insert(0, str(ROOT / "src"))
    __import__(f"pitstudio.contracts._generated.{stem}")


# ---- FR-002-45: the loader rejects a profile that weakens a guard or breaks a rule ---------------------------------
def _mutate(**guards_or_top: Any) -> dict[str, Any]:
    prof = rw.profile_doc()
    for k, v in guards_or_top.items():
        if k in prof["guards"] or k in (
            "vram_margin_gib",
            "disk_margin_gib",
            "max_start_temp_c",
            "cooldown_wait_s",
            "lock_wait_s",
        ):
            prof["guards"][k] = v
        else:
            prof[k] = v
    return prof


WIN = rw.IS_WINDOWS
HOSTILE_PROFILES = [
    ("vram margin below 1.5 GiB", _mutate(vram_margin_gib=1.4), "vram_margin_gib"),
    ("disk margin below 20 GiB", _mutate(disk_margin_gib=19.9), "disk_margin_gib"),
    ("start temperature above 80 C", _mutate(max_start_temp_c=80.5), "max_start_temp_c"),
    ("telemetry_hz zero", _mutate(telemetry_hz=0), "telemetry_hz"),
    ("telemetry_hz five", _mutate(telemetry_hz=5), "telemetry_hz"),
    ("telemetry_hz not a number", _mutate(telemetry_hz="fast"), "telemetry_hz"),
    (
        "process control of the other OS",
        _mutate(process_control="process-group" if WIN else "job-object"),
        "process_control",
    ),
    ("unknown environment", _mutate(envs_enabled=["studio", "docker"]), "envs_enabled"),
    ("empty environments", _mutate(envs_enabled=[]), "envs_enabled"),
    (
        "user-specific store default",
        # built from two parts so that no committed literal is a machine path (tools/check_repo.py)
        _mutate(store_default="C:" + "/Users/alice/ps" if WIN else "/home" + "/alice/ps"),
        "store_default",
    ),
    ("relative store default", _mutate(store_default="ps"), "store_default"),
    ("store default with backslash", _mutate(store_default="C:\\ps" if WIN else "\\srv\\ps"), "store_default"),
    ("unknown field", _mutate(extra_field=1), "extra_field"),
    ("quota above 10,000 GiB", _mutate(quotas={"st55_sdg": 10001}), "quotas"),
    ("quota for a non-stage", _mutate(quotas={"not_a_stage": 5}), "quotas"),
    ("binary variable holding a path", _mutate(binaries={"ffmpeg": "C:/tools/ffmpeg.exe"}), "binaries"),
]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path, recipes=[rw.recipe("one-stage", [rw.stage("s10_preprocess")])])
    yield w
    rw.cleanup_world(w)


@pytest.mark.req("FR-002-45")
@pytest.mark.parametrize(("label", "prof", "field"), HOSTILE_PROFILES, ids=[h[0] for h in HOSTILE_PROFILES])
def test_fr_002_45_hostile_profile_is_rejected_with_exit_2(world, label: str, prof: dict[str, Any], field: str) -> None:
    world.write_profile(prof)
    before = world.snapshot_store()
    r = world.cli("plan", str(world.recipes["one-stage"]), "--profile", prof["id"])
    assert r.code == 2, f"{label}: exit {r.code}\n{r.text}"
    assert field in r.text, f"{label}: message must name {field!r}: {r.text!r}"
    assert len([ln for ln in r.text.splitlines() if ln.strip()]) <= 3
    assert world.snapshot_store() == before


@pytest.mark.req("FR-002-45")
@pytest.mark.parametrize(
    "prof",
    [
        _mutate(vram_margin_gib=1.5, disk_margin_gib=20, max_start_temp_c=80, telemetry_hz=1),
        _mutate(vram_margin_gib=256, disk_margin_gib=10000, max_start_temp_c=0, telemetry_hz=4),
    ],
    ids=["at-the-floors-hz-1", "at-the-caps-hz-4"],
)
def test_fr_002_45_profile_exactly_at_its_bounds_is_accepted(world, prof: dict[str, Any]) -> None:
    world.write_profile(prof)
    r = world.cli("plan", str(world.recipes["one-stage"]), "--profile", prof["id"])
    assert r.code == 0, r.text


@pytest.mark.req("FR-002-45")
def test_fr_002_45_unknown_profile_and_malformed_yaml_are_usage_errors(world) -> None:
    assert world.cli("plan", str(world.recipes["one-stage"]), "--profile", "nope").code == 2
    p = world.repo / "studio" / "recipes" / "_profiles" / "broken.yaml"
    for body in ["id: broken\n  bad: [", "id: &a broken\nos: *a\n", "\ufeffid: broken\n", "- not a mapping\n", ""]:
        p.write_text(body, encoding="utf-8")
        r = world.cli("plan", str(world.recipes["one-stage"]), "--profile", "broken")
        assert r.code == 2, (body, r.text)
