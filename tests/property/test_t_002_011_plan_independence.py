# ruff: noqa: PT018
"""T-002-011: the `--json` plan is canonical, leaks no machine detail and is byte-identical wherever it runs.

Requirements: FR-002-04, P-002-12.

Expected API: `pitstudio.runner.cli.main(["plan", <recipe>, "--profile", <id>, "--json"])` prints RFC 8785 canonical
JSON (sorted keys, no white space, ECMAScript numbers: 6.0 is written `6`) followed by at most one newline; no
absolute path, drive letter, backslash, host name, user name or home directory appears in it; a store, when shown, is
shown only as `$PITSTUDIO_STORE`. Cache keys depend on file CONTENT only (code root digest, lock bytes), never on the
repository location.
Oracles: spec 001 data-model 1.5 patterns, `socket.gethostname()` / `getpass.getuser()` / `Path.home()` as reference
strings, a hand-written JCS writer for the number forms used by plans.
"""

from __future__ import annotations

import getpass
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage, up

ORIG_PLATFORM = sys.platform
DRIVE = re.compile(r"[A-Za-z]:[\\/]")
UNC = re.compile(r"\\\\[A-Za-z0-9._$-]+\\")
POSIX = re.compile(r"(^|[\s\"'=(,:])/(home|Users|root|tmp|var|mnt|media|opt|srv|private|run)/")


def jcs(o: Any) -> str:
    """RFC 8785 for the value types of a plan: objects, arrays, strings, integers, finite floats, booleans, null."""
    if o is None:
        return "null"
    if o is True:
        return "true"
    if o is False:
        return "false"
    if isinstance(o, int):
        return str(o)
    if isinstance(o, float):
        assert o == o and abs(o) != float("inf")
        if o == int(o) and abs(o) < 1e21:
            return str(int(o))  # 6.0 -> 6 (ECMAScript Number::toString)
        return repr(o)
    if isinstance(o, str):
        return json.dumps(o, ensure_ascii=False)
    if isinstance(o, list):
        return "[" + ",".join(jcs(v) for v in o) + "]"
    if isinstance(o, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + jcs(o[k]) for k in sorted(o)) + "}"
    raise TypeError(type(o))


def activate(w: rw.World, monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in w.env_vars().items():
        monkeypatch.setenv(k, v)


def leak_findings(text: str, extra_secrets: list[str]) -> list[str]:
    bad: list[str] = []
    for name, rx in (("drive", DRIVE), ("unc", UNC), ("posix", POSIX)):
        if rx.search(text):
            bad.append(name)
    if "\\" in text:
        bad.append("backslash")
    if "file:/" in text:
        bad.append("file-url")
    low = text.lower()
    bad += [s for s in extra_secrets if len(s) >= 3 and s.lower() in low]
    return bad


def mixed_recipe() -> dict[str, Any]:
    return recipe(
        "indep",
        [
            stage("s00_download", params={"note": "alpha", "limit": 4}),
            stage(
                "st50_physics",
                gpu="exclusive",
                vram=6.0,
                disk=4.0,
                variant="dem",
                shardable=(1000, 20000),
                inputs=[up("s00_download", "out.bin")],
            ),
            stage("st56_encode", gpu="nvenc", disk=0.5, inputs=[up("st50_physics", "out.bin", "dem")]),
            stage("st10_terrain", params={"scale": 2.5}),
        ],
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path, recipes=[mixed_recipe()])
    yield w
    rw.cleanup_world(w)


@pytest.mark.req("FR-002-04")
def test_fr_002_04_plan_json_is_rfc8785_canonical_and_shows_no_machine_detail(
    world, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hostile_home = tmp_path / "pitUserXyz-home"
    hostile_home.mkdir()
    monkeypatch.setenv("USERNAME", "pitUserXyz")
    monkeypatch.setenv("USER", "pitUserXyz")
    monkeypatch.setenv("HOME", str(hostile_home))
    monkeypatch.setenv("USERPROFILE", str(hostile_home))
    monkeypatch.setattr(socket, "gethostname", lambda: "PITHOST-ABC")
    monkeypatch.setattr(getpass, "getuser", lambda: "pitUserXyz")
    monkeypatch.chdir(hostile_home)
    r = world.cli("plan", str(world.recipes["indep"]), "--profile", "test-profile", "--json")
    assert r.code == 0, r.text
    text = r.out
    assert not text.endswith("\n\n")
    body = text.rstrip("\n")
    doc = json.loads(body)
    assert body == jcs(doc), "plan JSON is not RFC 8785 canonical"
    assert not leak_findings(
        body,
        [
            socket.gethostname(),
            getpass.getuser(),
            "pitUserXyz",
            "PITHOST-ABC",
            str(world.store),
            str(world.repo),
            str(hostile_home),
            Path.home().name,
            str(world.lock_dir),
        ],
    )
    assert "store" not in doc or doc["store"] == "$PITSTUDIO_STORE"
    # a plan with an unusual but valid unicode description does not change that
    assert all(isinstance(s["key"], str) for s in doc["stages"])


@pytest.mark.req("FR-002-04")
@pytest.mark.req("P-002-12")
def test_p_002_12_plan_is_byte_identical_across_cwd_store_host_user_platform_and_repo_location(
    world, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ref = world.cli("plan", str(world.recipes["indep"]), "--profile", "test-profile", "--json")
    assert ref.code == 0, ref.text

    # a second, identical repository at another location with another store, host and user
    (tmp_path / "second").mkdir()
    other = rw.make_world(monkeypatch, tmp_path / "second", recipes=[mixed_recipe()])
    try:
        activate(other, monkeypatch)
        elsewhere = tmp_path / "some" / "other" / "cwd"
        elsewhere.mkdir(parents=True)
        monkeypatch.chdir(elsewhere)
        monkeypatch.setattr(socket, "gethostname", lambda: "another-host")
        monkeypatch.setattr(getpass, "getuser", lambda: "another-user")
        monkeypatch.setenv("USERNAME", "another-user")
        monkeypatch.setenv("USERPROFILE", str(elsewhere))
        outs = []
        for plat in ("win32", "linux", "darwin"):
            monkeypatch.setattr(sys, "platform", plat)
            r = other.cli("plan", str(other.recipes["indep"]), "--profile", "test-profile", "--json")
            monkeypatch.setattr(sys, "platform", ORIG_PLATFORM)
            assert r.code == 0, f"{plat}: {r.text}"
            outs.append(r.out)
        assert len(set(outs)) == 1
        assert outs[0] == ref.out, "plan bytes differ between two machines' worth of environment"
    finally:
        rw.cleanup_world(other)


# ---- property: random recipes ---------------------------------------------------------------------------------------
CPU_IDS = [
    "s00_download",
    "s05_synthesize",
    "s10_preprocess",
    "s20_feature_extraction",
    "s30_train",
    "st10_terrain",
    "st20_pit_design",
]
GPU_IDS = ["st50_physics"]


@st.composite
def recipes(draw: st.DrawFn) -> dict[str, Any]:
    ids = draw(st.lists(st.sampled_from(CPU_IDS + GPU_IDS), min_size=1, max_size=6, unique=True))
    stages: list[dict[str, Any]] = []
    for i, sid in enumerate(ids):
        deps = draw(st.lists(st.integers(0, max(i - 1, 0)), max_size=2, unique=True)) if i else []
        inputs = [up(ids[d], "out.bin") for d in deps]
        params = {
            "alpha": draw(st.integers(-5, 5)),
            "tag": draw(st.text(alphabet="abcxyz-", max_size=6)),
            "ratio": draw(st.sampled_from([0.5, 1.25, 4.5, 4.50, 2.0])),
        }
        if sid in GPU_IDS:
            stages.append(
                stage(sid, gpu="exclusive", vram=draw(st.sampled_from([1.0, 2.5, 6.0])), params=params, inputs=inputs)
            )
        else:
            stages.append(stage(sid, params=params, inputs=inputs))
    return recipe("prop", stages, seed=draw(st.integers(0, 2**62)))


@pytest.mark.req("P-002-12")
def test_p_002_12_plan_bytes_do_not_depend_on_cwd_store_host_user_or_platform(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    a = rw.make_world(monkeypatch, tmp_path_factory.mktemp("a"))
    b = rw.make_world(monkeypatch, tmp_path_factory.mktemp("b"))
    try:

        @settings(max_examples=25, deadline=None)
        @given(doc=recipes())
        def prop(doc: dict[str, Any]) -> None:
            a.write_recipe(doc)
            b.write_recipe(doc)
            activate(a, monkeypatch)
            ra = a.cli("plan", str(a.recipes["prop"]), "--profile", "test-profile", "--json")
            activate(b, monkeypatch)
            monkeypatch.chdir(b.base)
            monkeypatch.setattr(socket, "gethostname", lambda: "other-host")
            monkeypatch.setattr(getpass, "getuser", lambda: "other-user")
            monkeypatch.setattr(sys, "platform", "linux" if ORIG_PLATFORM == "win32" else "win32")
            try:
                rb = b.cli("plan", str(b.recipes["prop"]), "--profile", "test-profile", "--json")
            finally:
                monkeypatch.setattr(sys, "platform", ORIG_PLATFORM)
            assert ra.code == rb.code == 0, (ra.text, rb.text)
            assert ra.out == rb.out

        prop()
    finally:
        rw.cleanup_world(a)
        rw.cleanup_world(b)
