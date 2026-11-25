# ruff: noqa: E501
"""T-015-011: model repository, revision and file-hash verification with a fake hub; hostile repositories.

Requirements: FR-015-03, FR-015-04.

Spec: specs/015-vlm/spec.md
- FR-015-03: the Cosmos arm uses weights only from `nvidia/Cosmos-Reason2-2B` at the pinned full 40-hex revision beginning `9ce19a1`, and
  the control only from `Qwen/Qwen3-VL-2B-Instruct` at its pinned revision, each downloaded file verified against the SHA-256 recorded in
  the pin file.
- FR-015-04: if a configuration names any other repository (including third-party GGUF conversions and modified or guardrail-removed
  variants), a revision other than the pinned one, or a downloaded file whose SHA-256 differs from its pin, then the lane refuses to load
  it, exits with code 2 and names the repository and file.

Oracle: SHA-256 of fixture bytes computed with `hashlib` (`_p015_pins_kit`); the exact repository strings and revisions of the spec; a
fake hub with recorded bytes (`FakeHub`, the hub's `fetch(repo, revision, name) -> bytes` is the only network seam); a hostile corpus of
repository names (the community GGUF of the method page, an "abliterated" variant, case and whitespace variants, path-like and URL-like
strings) and revisions (`main`, a short prefix, another full SHA, upper case, empty).

Expected API of the implementation (package `pitstudio_pipeline`), `pitstudio_pipeline.reason.hub`:
- `ProvenanceError(Exception)`: `exit_code == 2`, `repository`, `file` (None when the problem is not about one file), `reason`;
  `str(error)` names the repository and, when set, the file.
- `check_model_config(cfg, pins) -> None`: `cfg` is `{"cosmos": {"repository", "revision"}, "qwen": {"repository", "revision"}}` (either key may be
  absent); every present entry must equal the pinned repository and revision exactly, otherwise ProvenanceError.
- `download_model(pins, which, dest, *, hub) -> Path`: `which` is "cosmos" or "qwen"; for each file pinned for that model it calls
  `hub.fetch(repository, revision, name)` (only the pinned repository, revision and files), checks the byte count and the SHA-256 against the
  pin, and stores it as `dest / org / name / revision / file`; returns that snapshot folder. On any mismatch it raises ProvenanceError (the
  bad file is not left at its final path); a pin file whose repository is not the expected one, or whose file name is not a plain relative
  name, is refused before any hub call.
"""

from __future__ import annotations

import copy
from pathlib import Path

import _p015_pins_kit as kit
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.reason import hub as hubmod


@pytest.fixture
def env(tmp_path: Path) -> kit.Env:
    return kit.build_env(tmp_path)


def _expected_calls(pins: dict, which: str) -> list[tuple[str, str, str]]:
    m = pins["models"][which]
    return sorted((m["repository"], m["revision"], n) for n in m["files"])


@pytest.mark.req("FR-015-03")
@pytest.mark.parametrize(
    ("which", "repo", "rev"), [("cosmos", kit.COSMOS_REPO, kit.COSMOS_REV), ("qwen", kit.QWEN_REPO, kit.QWEN_REV)]
)
def test_each_model_is_downloaded_from_its_pinned_repository_and_revision_and_verified(
    env: kit.Env, tmp_path: Path, which: str, repo: str, rev: str
) -> None:
    h = kit.default_hub()
    dest = tmp_path / "hub"
    snap = hubmod.download_model(env.pins, which, dest, hub=h)
    org, name = repo.split("/")
    assert snap == dest / org / name / rev
    assert sorted(h.calls) == _expected_calls(
        env.pins, which
    )  # only the pinned files, from the pinned repository and revision
    for fname, data in kit.MODEL_FILES[repo].items():
        assert (snap / fname).read_bytes() == data


@pytest.mark.req("FR-015-03")
def test_the_cosmos_revision_begins_with_9ce19a1_and_is_a_full_40_hex_sha(env: kit.Env) -> None:
    rev = env.pins["models"]["cosmos"]["revision"]
    assert rev.startswith("9ce19a1")
    assert len(rev) == 40
    assert set(rev) <= set("0123456789abcdef")


COSMOS = {"repository": kit.COSMOS_REPO, "revision": kit.COSMOS_REV}
QWEN = {"repository": kit.QWEN_REPO, "revision": kit.QWEN_REV}


@pytest.mark.req("FR-015-04")
def test_the_exact_pinned_configuration_is_accepted(env: kit.Env) -> None:
    hubmod.check_model_config({"cosmos": COSMOS, "qwen": QWEN}, env.pins)
    hubmod.check_model_config({"qwen": QWEN}, env.pins)
    hubmod.check_model_config({"cosmos": COSMOS}, env.pins)


BAD_REPOS = [
    "apolo13x/Cosmos-Reason2-2B-GGUF",  # the community GGUF named on the method page
    "nvidia/Cosmos-Reason2-2B-GGUF",
    "nvidia/Cosmos-Reason2-2B-abliterated",
    "nvidia/Cosmos-Reason2-2B-uncensored",
    "someone/Cosmos-Reason2-2B-no-guardrails",
    "nvidia/Cosmos-Reason2-8B",
    "nvidia/Cosmos-Reason1-7B",
    "nvidia/cosmos-reason2-2b",  # case variant
    "NVIDIA/Cosmos-Reason2-2B",
    " nvidia/Cosmos-Reason2-2B",
    "nvidia/Cosmos-Reason2-2B ",
    "nvidia/Cosmos-Reason2-2B/",
    "https://huggingface.co/nvidia/Cosmos-Reason2-2B",
    "../nvidia/Cosmos-Reason2-2B",
    "nvidia/Cosmos-Reason2-2B\u200b",
    "nvidia\\Cosmos-Reason2-2B",
    "Qwen/Qwen3-VL-2B-Instruct",  # the control's repository in the Cosmos slot
    "",
]


@pytest.mark.req("FR-015-04")
@pytest.mark.parametrize("repo", BAD_REPOS, ids=lambda r: (r or "empty").replace("/", "_")[:40])
def test_any_other_repository_in_the_cosmos_slot_is_refused_naming_it(env: kit.Env, repo: str) -> None:
    with pytest.raises(hubmod.ProvenanceError) as exc:
        hubmod.check_model_config({"cosmos": {"repository": repo, "revision": kit.COSMOS_REV}}, env.pins)
    assert exc.value.exit_code == 2
    assert exc.value.repository == repo
    assert repo in str(exc.value)


@pytest.mark.req("FR-015-04")
@pytest.mark.parametrize(
    "repo",
    [
        "Qwen/Qwen3-VL-2B-Instruct-GGUF",
        "Qwen/Qwen3-VL-2B-Thinking",
        "Qwen/Qwen3-VL-4B-Instruct",
        "qwen/qwen3-vl-2b-instruct",
        "unsloth/Qwen3-VL-2B-Instruct",
        kit.COSMOS_REPO,
    ],
)
def test_any_other_repository_in_the_control_slot_is_refused(env: kit.Env, repo: str) -> None:
    with pytest.raises(hubmod.ProvenanceError) as exc:
        hubmod.check_model_config({"qwen": {"repository": repo, "revision": kit.QWEN_REV}}, env.pins)
    assert exc.value.exit_code == 2
    assert repo in str(exc.value)


BAD_REVISIONS = [
    "main",
    "9ce19a1",  # the short prefix is not a full revision
    "9ce19a1" + "f" * 33,  # a different full SHA with the right prefix
    kit.COSMOS_REV.upper(),
    kit.COSMOS_REV[:-1],
    kit.COSMOS_REV + "0",
    "0" * 40,
    "",
    " " + kit.COSMOS_REV,
    kit.QWEN_REV,
    "refs/pr/1",
]


@pytest.mark.req("FR-015-04")
@pytest.mark.parametrize("rev", BAD_REVISIONS, ids=lambda r: (r or "empty")[:24].replace("/", "_"))
def test_a_revision_other_than_the_pinned_one_is_refused_naming_the_repository(env: kit.Env, rev: str) -> None:
    with pytest.raises(hubmod.ProvenanceError) as exc:
        hubmod.check_model_config({"cosmos": {"repository": kit.COSMOS_REPO, "revision": rev}}, env.pins)
    assert exc.value.exit_code == 2
    assert kit.COSMOS_REPO in str(exc.value)


@pytest.mark.req("FR-015-04")
@pytest.mark.parametrize("rev", ["main", kit.COSMOS_REV, "", "9ce19a1", kit.QWEN_REV[:-1]])
def test_the_control_revision_must_be_exactly_its_pin(env: kit.Env, rev: str) -> None:
    with pytest.raises(hubmod.ProvenanceError):
        hubmod.check_model_config({"qwen": {"repository": kit.QWEN_REPO, "revision": rev}}, env.pins)


@pytest.mark.req("FR-015-04")
@pytest.mark.parametrize(
    "bad",
    [
        None,
        5,
        [],
        "nvidia/Cosmos-Reason2-2B",
        {"repository": kit.COSMOS_REPO},
        {"revision": kit.COSMOS_REV},
        {"repository": 3, "revision": kit.COSMOS_REV},
    ],
)
def test_a_malformed_configuration_entry_is_refused(env: kit.Env, bad: object) -> None:
    with pytest.raises(hubmod.ProvenanceError):
        hubmod.check_model_config({"cosmos": bad}, env.pins)


@pytest.mark.req("FR-015-04")
@pytest.mark.parametrize("name", sorted(kit.MODEL_FILES[kit.COSMOS_REPO]))
@pytest.mark.parametrize("how", ["flipped", "appended", "truncated", "empty", "same-size-other-content"])
def test_a_downloaded_file_whose_sha256_differs_from_its_pin_is_refused_naming_repository_and_file(
    env: kit.Env, tmp_path: Path, name: str, how: str
) -> None:
    h = kit.default_hub()
    good = kit.MODEL_FILES[kit.COSMOS_REPO][name]
    bad = {
        "flipped": good[:10] + bytes([good[10] ^ 0x20]) + good[11:],
        "appended": good + b"\n",
        "truncated": good[:-1],
        "empty": b"",
        "same-size-other-content": bytes(reversed(good)),
    }[how]
    assert bad != good
    h.files[(kit.COSMOS_REPO, kit.COSMOS_REV)][name] = bad
    dest = tmp_path / "hub"
    with pytest.raises(hubmod.ProvenanceError) as exc:
        hubmod.download_model(env.pins, "cosmos", dest, hub=h)
    assert exc.value.exit_code == 2
    assert exc.value.repository == kit.COSMOS_REPO
    assert exc.value.file == name
    assert kit.COSMOS_REPO in str(exc.value)
    assert name in str(exc.value)
    final = dest / "nvidia" / "Cosmos-Reason2-2B" / kit.COSMOS_REV / name
    assert not final.exists(), "a file that failed verification must not be left where the lane would load it"


@pytest.mark.req("FR-015-03")
def test_a_pin_file_naming_another_repository_is_refused_before_any_hub_call(env: kit.Env, tmp_path: Path) -> None:
    pins = copy.deepcopy(env.pins)
    pins["models"]["cosmos"]["repository"] = "apolo13x/Cosmos-Reason2-2B-GGUF"
    h = kit.default_hub()
    with pytest.raises(hubmod.ProvenanceError):
        hubmod.download_model(pins, "cosmos", tmp_path / "hub", hub=h)
    assert h.calls == []


@pytest.mark.req("FR-015-03")
@pytest.mark.parametrize(
    "fname", ["../escape.bin", "..\\escape.bin", "/abs.bin", "a/../../b.bin", "C:/x.bin", "", "x\x00y"]
)
def test_a_pinned_file_name_that_is_not_a_plain_relative_name_is_refused_and_nothing_is_written_outside_the_destination(
    env: kit.Env, tmp_path: Path, fname: str
) -> None:
    pins = copy.deepcopy(env.pins)
    pins["models"]["cosmos"]["files"][fname] = {"sha256": kit.sha256_hex(b"x"), "bytes": 1}
    h = kit.default_hub()
    h.files[(kit.COSMOS_REPO, kit.COSMOS_REV)][fname] = b"x"
    dest = tmp_path / "hub"
    before = {p for p in tmp_path.rglob("*")}
    with pytest.raises(hubmod.ProvenanceError):
        hubmod.download_model(pins, "cosmos", dest, hub=h)
    new = {p for p in tmp_path.rglob("*")} - before
    assert all(dest in p.parents or p == dest for p in new)
    assert not (tmp_path / "escape.bin").exists()


@pytest.mark.req("FR-015-03")
def test_a_file_missing_on_the_hub_is_an_error_naming_it_not_a_silent_skip(env: kit.Env, tmp_path: Path) -> None:
    h = kit.default_hub()
    del h.files[(kit.QWEN_REPO, kit.QWEN_REV)]["model.safetensors"]
    with pytest.raises(hubmod.ProvenanceError) as exc:
        hubmod.download_model(env.pins, "qwen", tmp_path / "hub", hub=h)
    assert exc.value.file == "model.safetensors"


@pytest.mark.req("FR-015-03")
@pytest.mark.parametrize("which", ["", "gemma", "COSMOS", None])
def test_an_unknown_model_slot_is_refused(env: kit.Env, tmp_path: Path, which: object) -> None:
    with pytest.raises((hubmod.ProvenanceError, ValueError, KeyError)):
        hubmod.download_model(env.pins, which, tmp_path / "hub", hub=kit.default_hub())  # type: ignore[arg-type]


@pytest.mark.req("FR-015-04")
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text(max_size=60), st.text(max_size=60))
def test_property_only_the_exact_pair_of_repository_and_revision_is_accepted(env: kit.Env, repo: str, rev: str) -> None:
    exact = repo == kit.COSMOS_REPO and rev == kit.COSMOS_REV
    try:
        hubmod.check_model_config({"cosmos": {"repository": repo, "revision": rev}}, env.pins)
    except hubmod.ProvenanceError:
        assert not exact
    else:
        assert exact
