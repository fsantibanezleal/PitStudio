# ruff: noqa: E501, PT018
"""T-008-040: CPU generators and the studio-output collector; missing or tampered studio outputs -> `not-run`; byte-identical re-runs.

Requirements: FR-008-32, FR-008-35, FR-008-38, P-008-09, FR-008-15.

Spec: specs/008-data-pipeline/spec.md FR-008-32 (CPU sources: DES cycles, Kuz-Ram/KCO + Swebrec PSDs, Voight creep series,
Gaussian plume fields, `oreblocks` deposits and comminution sweeps; studio outputs collected as files with SHA-256 digests:
SDG images, sensor clouds, physics fields, Isaac Lab rollouts, hazard-question sets, plausibility pairs), FR-008-35 (a missing
output or a digest that differs from the studio manifest marks the set `not-run` with the reason, never a placeholder),
FR-008-38 and P-008-09 (same seeds and configuration give equal SHA-256 for every output; the manifest records
`determinism.class: bitwise`; for stochastic generators a different seed gives a different SHA-256), FR-008-15 (unsafe data
root refused by this stage too).

Oracle: double-run SHA-256 equality (`hashlib` over the files written by two independent runs in two separate data roots);
fixture studio outputs with digests computed in the test; a tampered byte; hand-built manifests.

Expected API of the implementation (module `pitstudio_pipeline.synthesize`):
- `run(generator, *, seed, config=None, data_root, repo_root=None, now=None) -> SynthResult` for the generator ids
  `des-cycles`, `kuz-ram-psd`, `voight-creep`, `gaussian-plume`, `oreblocks`, `comminution-sweep` (`config=None` = the
  generator's documented defaults). Files go to `<data_root>/synthetic/<generator>/`. `SynthResult`: `files` (list of Path),
  `sha256` (dict POSIX path relative to the data root -> hex digest, one entry per file), `records` (list of dicts, each with
  `"synthetic": True`), `synthetic` (True), `manifest` (dict with `determinism` = `{"class": "bitwise"}`). The stochastic
  generators are `des-cycles`, `voight-creep` and `oreblocks`.
- `collect_studio_outputs(studio_manifest, outputs_dir, *, needed) -> dict`: `studio_manifest` is a path to a JSON file
  `{"artefacts": [{"id", "path", "sha256", "bytes"}]}` (paths relative to `outputs_dir`), `needed` a list of artefact ids;
  returns id -> `{"status": "collected" | "not-run", "reason": str | None, "sha256": hex | None, "path": str | None}`. A missing
  file, a digest different from the manifest, an id absent from the manifest, or a path that is absolute or leaves
  `outputs_dir` gives `not-run` with a non-empty reason; nothing is created for it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import _p008_kit as kit
import pytest
from pitstudio_pipeline.errors import UnsafeDataRoot
from pitstudio_pipeline.synthesize import collect_studio_outputs, run

GENERATORS = ["des-cycles", "kuz-ram-psd", "voight-creep", "gaussian-plume", "oreblocks", "comminution-sweep"]
STOCHASTIC = ["des-cycles", "voight-creep", "oreblocks"]
STUDIO_SETS = [
    "sdg-images",
    "sensor-clouds",
    "physics-fields",
    "isaac-lab-rollouts",
    "hazard-question-sets",
    "plausibility-pairs",
]


def _go(tmp: Path, name: str, generator: str, seed: int):
    root = tmp / name
    return root, run(generator, seed=seed, config=None, data_root=root, now=kit.NOW)


# ------------------------------------------------------------------------------------------------ FR-008-32 / FR-008-38
@pytest.mark.req("FR-008-32")
@pytest.mark.parametrize("generator", GENERATORS)
def test_each_cpu_generator_writes_files_with_digests_and_synthetic_records(generator: str, tmp_path: Path) -> None:
    root, res = _go(tmp_path, "a", generator, 0)
    assert res.files and res.synthetic is True
    assert set(res.sha256) == {p.relative_to(root).as_posix() for p in res.files}
    for p in res.files:
        assert p.is_file() and root / "synthetic" / generator in p.parents
        assert res.sha256[p.relative_to(root).as_posix()] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert res.records and all(r["synthetic"] is True for r in res.records)


@pytest.mark.req("FR-008-38")
@pytest.mark.parametrize("generator", GENERATORS)
@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_same_seed_and_configuration_give_byte_identical_outputs(generator: str, seed: int, tmp_path: Path) -> None:
    root_a, a = _go(tmp_path, "a", generator, seed)
    root_b, b = _go(tmp_path, "b", generator, seed)
    assert a.sha256 == b.sha256
    for rel in a.sha256:
        assert (root_a / rel).read_bytes() == (root_b / rel).read_bytes()
    assert a.manifest["determinism"] == {"class": "bitwise"} == b.manifest["determinism"]


@pytest.mark.req("P-008-09")
@pytest.mark.parametrize("generator", STOCHASTIC)
def test_a_different_seed_gives_a_different_digest_for_stochastic_generators(generator: str, tmp_path: Path) -> None:
    digests = {tuple(sorted(_go(tmp_path, f"s{seed}", generator, seed)[1].sha256.values())) for seed in range(5)}
    assert len(digests) == 5, "five seeds, five different outputs"


@pytest.mark.req("FR-008-15")
def test_synthesis_refuses_an_unsafe_data_root(tmp_path: Path) -> None:
    repo = kit.make_repo(tmp_path)
    with pytest.raises(UnsafeDataRoot):
        run("kuz-ram-psd", seed=0, config=None, data_root=repo / "data", repo_root=repo, now=kit.NOW)
    assert kit.files_under(repo / "data") == []


@pytest.mark.req("FR-008-32")
def test_unknown_generator_and_hostile_seeds_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        run("no-such-generator", seed=0, config=None, data_root=tmp_path / "d", now=kit.NOW)
    for seed in (-1, 2**63, 1.5, None, float("nan")):
        with pytest.raises((ValueError, TypeError)):
            run("kuz-ram-psd", seed=seed, config=None, data_root=tmp_path / "d", now=kit.NOW)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------------ studio outputs
def _studio(
    tmp: Path,
    *,
    skip: set[str] = frozenset(),
    tamper: set[str] = frozenset(),
    absent_from_manifest: set[str] = frozenset(),
):
    out = tmp / "studio-out"
    out.mkdir()
    artefacts, contents = [], {}
    for i, sid in enumerate(STUDIO_SETS):
        data = kit.payload(300 + i, 50 + i)
        contents[sid] = data
        rel = f"{sid}/part-0001.bin"
        if sid not in absent_from_manifest:
            artefacts.append({"id": sid, "path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        if sid not in skip:
            (out / sid).mkdir()
            (out / rel).write_bytes(data[:-1] + bytes([data[-1] ^ 1]) if sid in tamper else data)
    manifest = tmp / "studio-manifest.json"
    manifest.write_text(json.dumps({"artefacts": artefacts}), encoding="utf-8")
    return manifest, out, contents


@pytest.mark.req("FR-008-32")
def test_intact_studio_outputs_are_collected_with_their_digests(tmp_path: Path) -> None:
    manifest, out, contents = _studio(tmp_path)
    res = collect_studio_outputs(manifest, out, needed=STUDIO_SETS)
    for sid in STUDIO_SETS:
        assert res[sid]["status"] == "collected" and res[sid]["sha256"] == hashlib.sha256(contents[sid]).hexdigest()


@pytest.mark.req("FR-008-35")
@pytest.mark.parametrize(
    "case",
    ["missing-file", "tampered-byte", "absent-from-manifest"],
)
def test_a_missing_or_tampered_output_marks_only_that_set_not_run(case: str, tmp_path: Path) -> None:
    kw = {
        "missing-file": {"skip": {"sensor-clouds"}},
        "tampered-byte": {"tamper": {"sensor-clouds"}},
        "absent-from-manifest": {"absent_from_manifest": {"sensor-clouds"}},
    }[case]
    manifest, out, _ = _studio(tmp_path, **kw)
    before = kit.tree_digest(out)
    res = collect_studio_outputs(manifest, out, needed=STUDIO_SETS)
    assert res["sensor-clouds"]["status"] == "not-run" and res["sensor-clouds"]["reason"]
    assert all(res[s]["status"] == "collected" for s in STUDIO_SETS if s != "sensor-clouds")
    assert kit.tree_digest(out) == before, "no placeholder or substitute file is created"


@pytest.mark.req("FR-008-35")
@pytest.mark.parametrize("bad_path", ["../outside.bin", "/abs/outside.bin", "C:/outside.bin", "a/../../outside.bin"])
def test_manifest_paths_that_escape_the_outputs_folder_are_not_collected(bad_path: str, tmp_path: Path) -> None:
    secret = tmp_path / "outside.bin"
    secret.write_bytes(b"secret")
    out = tmp_path / "studio-out"
    out.mkdir()
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "artefacts": [
                    {"id": "sdg-images", "path": bad_path, "sha256": hashlib.sha256(b"secret").hexdigest(), "bytes": 6}
                ]
            }
        )
    )
    res = collect_studio_outputs(manifest, out, needed=["sdg-images"])
    assert res["sdg-images"]["status"] == "not-run" and res["sdg-images"]["reason"]


@pytest.mark.req("FR-008-35")
@pytest.mark.parametrize("content", [b"", b"{", b"[]", b'{"artefacts": 7}', kit.payload(256, 1)])
def test_an_unreadable_studio_manifest_never_yields_collected_sets(content: bytes, tmp_path: Path) -> None:
    out = tmp_path / "studio-out"
    out.mkdir()
    manifest = tmp_path / "m.json"
    manifest.write_bytes(content)
    try:
        res = collect_studio_outputs(manifest, out, needed=["sdg-images"])
    except Exception:
        return
    assert res["sdg-images"]["status"] == "not-run" and res["sdg-images"]["reason"]
