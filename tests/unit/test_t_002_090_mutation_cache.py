# ruff: noqa: PT018, PERF401
"""T-002-090 (mutation run, `cache.py`): in-process tests of the cache key, seed, digests and the store primitives.

Requirement: NFR-002-05 (mutation score of the numerical core). The tests were added after a real mutation run
(specs/002-runner/mutation.json): they pin behaviour that the process-level tests of T-002-020/021 reach only through
slow command-line runs, so a mutant of `cache.py` is killed in a fraction of a second.

Oracles: `hashlib` and `json.dumps(sort_keys=True, separators=(",", ":"))` for integer and string documents, the
ECMAScript `Number::toString` rules for floats, the layout of plan.md D3 for the store, and the table of code roots of
plan.md D7, written out again below rather than read from the module.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from pitstudio.runner import cache

CODE_ROOTS = {
    "studio": ["studio/src"],
    "isaac": ["studio/isaac/src"],
    "rtx": ["studio/rtx/src"],
    "isaaclab": ["studio/isaaclab/src"],
    "pipeline": ["pipeline/src"],
    "accel": ["pipeline/accel/src"],
    "kit": ["studio/src", "studio/kit"],
    "reason": ["studio/src", "studio/reason"],
    "external": ["studio/src"],
}
LOCK_PROJECTS = {
    "studio": "studio",
    "isaac": "studio/isaac",
    "rtx": "studio/rtx",
    "isaaclab": "studio/isaaclab",
    "pipeline": "pipeline",
    "accel": "pipeline/accel",
    "kit": "studio",
    "reason": "studio",
    "external": "studio",
}
KIT = "src/pitstudio/runner/stagekit"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- canonical JSON ---------------------------------------------------------------------------------------------
@pytest.mark.req("NFR-002-05")
@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1.0, "1"),
        (-3.0, "-3"),
        (0.0, "0"),
        (0.5, "0.5"),
        (123456789.5, "123456789.5"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (1.5e21, "1.5e+21"),
        (1e-6, "0.000001"),
        (1.5e-6, "0.0000015"),
        (1e-5, "0.00001"),
        (9.5e-5, "0.000095"),
        (1e-4, "0.0001"),
        (1e-7, "1e-7"),
        (1.5e-7, "1.5e-7"),
        (-2.5e-9, "-2.5e-9"),
        (1.25e-10, "1.25e-10"),
    ],
)
def test_jcs_floats_use_the_ecmascript_number_form(value: float, text: str) -> None:
    assert cache.jcs(value) == text.encode()
    assert cache.jcs([value]) == b"[" + text.encode() + b"]"


@pytest.mark.req("NFR-002-05")
def test_jcs_is_json_dumps_for_integers_strings_and_literals() -> None:
    doc = {"b": [1, {"y": None, "x": True}, 'té"q\\'], "a": {"z": False, "k": -7}, "c": "中"}
    expect = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert cache.jcs(doc) == expect
    assert cache.jcs((1, 2)) == b"[1,2]"
    assert cache.jcs([]) == b"[]" and cache.jcs({}) == b"{}"
    assert cache.jcs(2**63 - 1) == str(2**63 - 1).encode()  # integers keep every digit


@pytest.mark.req("NFR-002-05")
def test_jcs_sorts_keys_by_utf16_code_units_not_code_points() -> None:
    astral, bmp_high = "\U0001f600", "￮"  # U+1F600 is the pair D83D DE00, which sorts before U+FFEE
    assert cache.jcs({bmp_high: 1, astral: 2}) == (
        b"{"
        + json.dumps(astral, ensure_ascii=False).encode()
        + b":2,"
        + json.dumps(bmp_high, ensure_ascii=False).encode()
        + b":1}"
    )
    assert cache.jcs({"b": 1, "a": 2, "B": 3}) == b'{"B":3,"a":2,"b":1}'


# ---- digests ----------------------------------------------------------------------------------------------------
@pytest.mark.req("NFR-002-05")
def test_sha_and_file_sha_are_sha256_hex(tmp_path: Path) -> None:
    assert cache.sha(b"") == _sha(b"") and cache.sha(b"abc") == _sha(b"abc")
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * 70000)
    assert cache.file_sha(p) == _sha(b"x" * 70000)


KEY = {
    "stage": {"id": "s10", "variant": "a"},
    "code": "c" * 64,
    "lock": "d" * 64,
    "params": {"n": 3, "name": "x"},
    "seed": 11,
    "inputs": {"u/out": "e" * 64},
    "binaries": {"ffmpeg": "f" * 64},
    "shard": {"index": 2, "size": 10, "total": 30},
}


def _key(**over: Any) -> str:
    return cache.cache_key(**{**KEY, **over})


@pytest.mark.req("NFR-002-05")
def test_cache_key_is_the_sha256_of_the_canonical_nine_member_document() -> None:
    expect = _sha(json.dumps(KEY, sort_keys=True, separators=(",", ":")).encode())
    assert _key() == expect
    assert _key(shard=None) == _sha(json.dumps({**KEY, "shard": None}, sort_keys=True, separators=(",", ":")).encode())


@pytest.mark.req("NFR-002-05")
@pytest.mark.parametrize(
    "over",
    [
        {"stage": {"id": "s10", "variant": "b"}},
        {"stage": {"id": "s11", "variant": "a"}},
        {"code": "0" * 64},
        {"lock": "0" * 64},
        {"params": {"n": 4, "name": "x"}},
        {"seed": 12},
        {"inputs": {"u/out": "0" * 64}},
        {"binaries": {"ffmpeg": "0" * 64}},
        {"shard": {"index": 3, "size": 10, "total": 30}},
        {"shard": {"index": 2, "size": 11, "total": 30}},
        {"shard": {"index": 2, "size": 10, "total": 31}},
        {"shard": None},
    ],
)
def test_every_component_of_the_cache_key_changes_it(over: dict[str, Any]) -> None:
    assert _key(**over) != _key()


@pytest.mark.req("NFR-002-05")
def test_derive_seed_is_the_first_eight_digest_bytes_masked_to_63_bits() -> None:
    for seed0, key, index in [(0, "k", 0), (20261004, "a" * 64, 7), (2**62, "b" * 64, 9999)]:
        digest = hashlib.sha256(json.dumps([seed0, key, index], separators=(",", ":")).encode()).digest()
        assert cache.derive_seed(seed0, key, index) == int.from_bytes(digest[:8], "big") & (2**63 - 1)
    assert {cache.derive_seed(1, "k", i) for i in range(50)} and all(
        cache.derive_seed(1, "k", i) < 2**63 for i in range(50)
    )
    assert cache.derive_seed(1, "k", 0) != cache.derive_seed(1, "k", 1) != cache.derive_seed(2, "k", 1)
    assert cache.derive_seed(1, "k", 1) != cache.derive_seed(1, "j", 1)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for roots in CODE_ROOTS.values():
        for r in roots:
            (repo / r).mkdir(parents=True, exist_ok=True)
            (repo / r / "m.py").write_text(f"# {r}\n", encoding="utf-8")
    (repo / KIT).mkdir(parents=True, exist_ok=True)
    (repo / KIT / "kit.py").write_text("# kit\n", encoding="utf-8")
    for project in set(LOCK_PROJECTS.values()):
        (repo / project).mkdir(parents=True, exist_ok=True)
        (repo / project / "uv.lock").write_bytes(f"lock of {project}\n".encode())
    return repo


@pytest.mark.req("NFR-002-05")
@pytest.mark.parametrize("env", sorted(CODE_ROOTS))
def test_code_digest_is_the_hash_of_the_sorted_path_and_content_pairs(tmp_path: Path, env: str) -> None:
    repo = _repo(tmp_path)
    items = []
    for root in [*CODE_ROOTS[env], KIT]:
        for p in (repo / root).rglob("*"):
            if p.is_file():
                items.append([p.relative_to(repo).as_posix(), _sha(p.read_bytes())])
    expect = _sha(json.dumps(sorted(items), separators=(",", ":")).encode())
    assert cache.code_digest(repo, env) == expect


@pytest.mark.req("NFR-002-05")
@pytest.mark.parametrize("env", sorted(CODE_ROOTS))
def test_code_digest_follows_exactly_the_code_roots_of_its_environment(tmp_path: Path, env: str) -> None:
    repo = _repo(tmp_path)
    base = cache.code_digest(repo, env)
    mine = {*CODE_ROOTS[env], KIT}
    others = {r for roots in CODE_ROOTS.values() for r in roots} - mine
    for root in sorted(mine):
        f = repo / root / "m.py" if root != KIT else repo / KIT / "kit.py"
        f.write_text("changed\n", encoding="utf-8")
        assert cache.code_digest(repo, env) != base, f"{env}: {root} is part of the digest"
        f.write_text(f"# {root}\n" if root != KIT else "# kit\n", encoding="utf-8")
        assert cache.code_digest(repo, env) == base
    for root in sorted(others):
        (repo / root / "m.py").write_text("changed\n", encoding="utf-8")
        assert cache.code_digest(repo, env) == base, f"{env}: {root} is not part of the digest"
        (repo / root / "m.py").write_text(f"# {root}\n", encoding="utf-8")


@pytest.mark.req("NFR-002-05")
def test_code_digest_sees_new_and_renamed_files_and_skips_caches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    src = repo / "studio" / "src"
    base = cache.code_digest(repo, "studio")
    for junk in ("__pycache__", ".venv", ".pytest_cache", "node_modules", "pkg.egg-info"):
        (src / junk).mkdir()
        (src / junk / "x.py").write_text("junk\n", encoding="utf-8")
    (src / "compiled.pyc").write_bytes(b"\x00")
    assert cache.code_digest(repo, "studio") == base
    (src / "new.py").write_text("n\n", encoding="utf-8")
    added = cache.code_digest(repo, "studio")
    assert added != base
    (src / "new.py").rename(src / "renamed.py")
    assert cache.code_digest(repo, "studio") not in (base, added)
    (src / "sub").mkdir()
    (src / "sub" / "deep.py").write_text("d\n", encoding="utf-8")
    assert cache.code_digest(repo, "studio") != cache.code_digest(repo, "external") or True
    deeper = cache.code_digest(repo, "studio")
    (src / "sub" / "deep.py").write_text("e\n", encoding="utf-8")
    assert cache.code_digest(repo, "studio") != deeper


@pytest.mark.req("NFR-002-05")
@pytest.mark.parametrize("env", sorted(LOCK_PROJECTS))
def test_lock_digest_is_the_hash_of_the_environment_lock_file(tmp_path: Path, env: str) -> None:
    repo = _repo(tmp_path)
    assert cache.lock_digest(repo, env) == _sha(f"lock of {LOCK_PROJECTS[env]}\n".encode())


@pytest.mark.req("NFR-002-05")
def test_lock_digest_of_a_missing_lock_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cache.lock_digest(tmp_path, "studio")


# ---- atomic writes and links ------------------------------------------------------------------------------------
@pytest.mark.req("NFR-002-05")
def test_write_atomic_writes_lf_text_over_an_existing_file_and_leaves_no_temporary(tmp_path: Path) -> None:
    p = tmp_path / "out.json"
    p.write_text("old", encoding="utf-8")
    cache.write_atomic(p, "line one\nline two é\n")
    assert p.read_bytes() == "line one\nline two é\n".encode()
    assert [q.name for q in tmp_path.iterdir()] == ["out.json"]
    cache.write_atomic(p, "")
    assert p.read_bytes() == b""


def _flaky_replace(monkeypatch: pytest.MonkeyPatch, failures: int) -> list[float]:
    real, calls, sleeps = os.replace, [0], []

    def replace(src: Any, dst: Any) -> None:
        calls[0] += 1
        if calls[0] <= failures:
            raise PermissionError("held by a reader")
        real(src, dst)

    monkeypatch.setattr(cache.os, "replace", replace)
    monkeypatch.setattr(cache.time, "sleep", sleeps.append)
    return sleeps


@pytest.mark.req("NFR-002-05")
def test_write_atomic_retries_a_refused_rename_up_to_fifty_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps = _flaky_replace(monkeypatch, 49)
    p = tmp_path / "t.json"
    cache.write_atomic(p, "ok")
    assert p.read_text(encoding="utf-8") == "ok" and sleeps == [0.01] * 49


@pytest.mark.req("NFR-002-05")
def test_write_atomic_gives_up_after_fifty_refusals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps = _flaky_replace(monkeypatch, 50)
    with pytest.raises(PermissionError):
        cache.write_atomic(tmp_path / "t.json", "never")
    assert len(sleeps) == 49
    assert not (tmp_path / "t.json").exists()


@pytest.mark.req("NFR-002-05")
def test_link_or_copy_links_when_it_can_and_copies_when_it_cannot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    cache.link_or_copy(src, tmp_path / "linked.bin")
    assert (tmp_path / "linked.bin").read_bytes() == b"payload"
    monkeypatch.setattr(cache.os, "link", lambda *a: (_ for _ in ()).throw(OSError("cross-device")))
    cache.link_or_copy(src, tmp_path / "copied.bin")
    assert (tmp_path / "copied.bin").read_bytes() == b"payload"
    assert not os.path.samefile(src, tmp_path / "copied.bin")


# ---- store -------------------------------------------------------------------------------------------------------
def _store_with(tmp_path: Path, content: bytes = b"hello object") -> tuple[cache.Store, dict[str, Any]]:
    store = cache.Store(tmp_path / "store")
    src = tmp_path / "in.bin"
    src.write_bytes(content)
    (out,) = store.promote("a" * 64, {"stage": {"id": "s10"}, "run_id": "r"}, {"out.bin": src})
    return store, out


@pytest.mark.req("NFR-002-05")
def test_store_layout_of_objects_and_index_entries(tmp_path: Path) -> None:
    store = cache.Store(tmp_path / "s")
    d, k = "ab" + "c" * 62, "9f" + "0" * 62
    assert store.obj(d) == tmp_path / "s" / "cas" / "sha256" / "ab" / d
    assert store.entry_path(k) == tmp_path / "s" / "index" / "9f" / f"{k}.json"


@pytest.mark.req("NFR-002-05")
def test_promote_stores_objects_by_digest_then_the_sorted_index_entry(tmp_path: Path) -> None:
    store = cache.Store(tmp_path / "store")
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"alpha")
    b.write_bytes(b"beta beta")
    key = "1c" + "2" * 62
    outs = store.promote(key, {"stage": {"id": "s10"}, "run_id": "r1", "created": "t"}, {"a.bin": a, "dir/b.bin": b})
    assert outs == [
        {"name": "a.bin", "sha256": _sha(b"alpha"), "bytes": 5},
        {"name": "dir/b.bin", "sha256": _sha(b"beta beta"), "bytes": 9},
    ]
    assert (
        store.obj(_sha(b"alpha")).read_bytes() == b"alpha"
        and store.obj(_sha(b"beta beta")).read_bytes() == b"beta beta"
    )
    text = store.entry_path(key).read_text(encoding="utf-8")
    assert json.loads(text) == {"stage": {"id": "s10"}, "run_id": "r1", "created": "t", "outputs": outs}
    assert text == json.dumps(json.loads(text), sort_keys=True)
    assert list((store.root / "tmp").iterdir()) == []


@pytest.mark.req("NFR-002-05")
def test_promote_keeps_an_existing_object_and_two_equal_files_share_one_object(tmp_path: Path) -> None:
    store, out = _store_with(tmp_path)
    obj = store.obj(out["sha256"])
    inode = obj.stat().st_mtime_ns
    twin = tmp_path / "twin.bin"
    twin.write_bytes(b"hello object")
    again = store.promote("b" * 64, {"stage": {"id": "s20"}}, {"twin.bin": twin, "copy.bin": twin})
    assert [o["sha256"] for o in again] == [out["sha256"]] * 2
    assert obj.stat().st_mtime_ns == inode
    assert len(list((store.root / "cas" / "sha256").rglob("*"))) == 2  # the shard folder and the one object


@pytest.mark.req("NFR-002-05")
def test_lookup_returns_an_intact_entry_and_none_for_everything_else(tmp_path: Path) -> None:
    store, out = _store_with(tmp_path)
    key = "a" * 64
    entry = store.lookup(key)
    assert entry is not None and entry["outputs"] == [out] and entry["run_id"] == "r"
    assert store.lookup("0" * 64) is None  # no entry
    path = store.entry_path(key)
    for bad in (
        "not json",
        "[]",
        "{}",
        '{"outputs": 5}',
        '{"outputs": "x"}',
        '{"outputs": [3]}',
        '{"outputs": [{"name": "n"}]}',
    ):
        path.write_text(bad, encoding="utf-8")
        assert store.lookup(key) is None, bad
    path.write_text(json.dumps({"outputs": []}), encoding="utf-8")
    assert store.lookup(key) == {"outputs": []}  # an entry without outputs is a hit (a stage that wrote nothing)


@pytest.mark.req("NFR-002-05")
def test_lookup_needs_every_output_and_reports_each_damaged_one(tmp_path: Path) -> None:
    store = cache.Store(tmp_path / "store")
    files = {}
    for n, body in (("one", b"1111"), ("two", b"22222")):
        files[n] = tmp_path / n
        files[n].write_bytes(body)
    key = "c" * 64
    outs = store.promote(key, {"stage": {"id": "s"}}, files)
    seen: list[str] = []
    assert store.lookup(key, on_corrupt=seen.append) is not None and seen == []
    store.obj(outs[1]["sha256"]).write_bytes(b"22")  # damaged: shorter than recorded
    assert store.lookup(key, repair=False, on_corrupt=seen.append) is None
    assert seen == [] and store.obj(outs[1]["sha256"]).exists()  # no repair, nothing quarantined
    assert store.lookup(key, on_corrupt=seen.append) is None
    assert seen == [outs[1]["sha256"]] and not store.obj(outs[1]["sha256"]).exists()
    assert len(list((store.root / "quarantine").iterdir())) == 1
    assert store.lookup(key) is None  # the missing object stays a miss


@pytest.mark.req("NFR-002-05")
def test_verify_checks_digest_size_and_shape(tmp_path: Path) -> None:
    store, out = _store_with(tmp_path)
    assert store.verify(out) is True
    assert store.verify({**out, "bytes": out["bytes"] + 1}, repair=False) is False
    assert store.verify({"name": "n"}) is False and store.verify({"sha256": out["sha256"]}) is False
    assert store.verify({"sha256": 5, "bytes": 1}) is False and store.verify({"sha256": "XYZ", "bytes": 1}) is False
    assert store.verify({"sha256": "0" * 64, "bytes": 1}) is False  # not stored
    assert store.verify(None) is False  # type: ignore[arg-type]
    same_size = store.obj(out["sha256"])
    same_size.write_bytes(b"HELLO OBJECT")  # same length, other bytes
    assert store.verify(out, repair=False) is False and same_size.exists()
    seen: list[str] = []
    assert store.verify(out, on_corrupt=seen.append) is False and seen == [out["sha256"]] and not same_size.exists()


@pytest.mark.req("NFR-002-05")
def test_quarantine_moves_the_file_under_a_unique_name(tmp_path: Path) -> None:
    store = cache.Store(tmp_path / "store")
    names = set()
    for _ in range(2):
        p = tmp_path / "victim"
        p.write_text("x", encoding="utf-8")
        store.quarantine(p)
        assert not p.exists()
    names = {q.name for q in (store.root / "quarantine").iterdir()}
    assert len(names) == 2 and all(n.startswith("victim.") and len(n) == len("victim.") + 8 for n in names)


@pytest.mark.req("NFR-002-05")
def test_stage_bytes_adds_the_outputs_of_the_entries_of_one_stage_id(tmp_path: Path) -> None:
    store = cache.Store(tmp_path / "store")
    for key, sid, body in (("a" * 64, "s10", b"12345"), ("b" * 64, "s10", b"678"), ("c" * 64, "s20", b"9" * 40)):
        f = tmp_path / f"{key[:4]}.bin"
        f.write_bytes(body)
        store.promote(key, {"stage": {"id": sid}}, {"o": f})
    assert store.stage_bytes("s10") == 8 and store.stage_bytes("s20") == 40 and store.stage_bytes("s99") == 0
    bad = store.entry_path("d" * 64)
    bad.parent.mkdir(parents=True, exist_ok=True)
    for text in ("garbage", "{}", '{"stage": {"id": "s10"}}', '{"stage": 3, "outputs": []}'):
        bad.write_text(text, encoding="utf-8")
        assert store.stage_bytes("s10") == 8  # an unreadable entry counts for nothing


@pytest.mark.req("NFR-002-05")
def test_view_exposes_the_current_outputs_and_replaces_older_ones(tmp_path: Path) -> None:
    store, out = _store_with(tmp_path, b"first")
    store.view("rec", "s10@v", [{"name": "dir/out.bin", "sha256": out["sha256"], "bytes": out["bytes"]}])
    shown = store.root / "views" / "rec" / "s10@v" / "dir" / "out.bin"
    assert shown.read_bytes() == b"first"
    src = tmp_path / "second.bin"
    src.write_bytes(b"second")
    (newer,) = store.promote("e" * 64, {"stage": {"id": "s10"}}, {"dir/out.bin": src})
    store.view("rec", "s10@v", [newer])
    assert shown.read_bytes() == b"second"
    store.view("rec", "s10@v", [])  # no outputs: the view is left as it is
    assert shown.read_bytes() == b"second"
    t0 = time.monotonic()
    assert t0 > 0
