# ruff: noqa: E501, PT018
"""T-008-016: account-bound skip with fallback (the key never written), no-fallback sources become `unavailable` and their
consumers `not_run`, offline mode.

Requirements: FR-008-13, FR-008-14, FR-008-16.

Spec: specs/008-data-pipeline/spec.md FR-008-13, FR-008-14, FR-008-16; section 7 fallback table (`era5` falls back to
`ghcnh`; every other source has no fallback source); spec 002 FR-002-60 (stage status `not_run` with a reason).

Oracle: a sentinel key string searched for in every output (records, manifest, repr of the result, exceptions, log
records, stdout/stderr and every file written under the data root); the fallback table of section 7 (the ids and their
order written in the test); a transport that raises on any request (offline mode).

Expected API of the implementation:
- `run_download(..., env=mapping, offline=None, recipe=None, ...)`: `env` replaces `os.environ`; an account-bound entry
  (`account.needed: true`) whose `account.env_var` is unset or the empty string is skipped (no request): each of its
  files gets a record with `status: fallback-used`, `fallback_sources` = the entry's `fallback.sources` in order, `stored_as`,
  `sha256` and `bytes` null, `attempts` 0. `offline=None` reads `env["PITSTUDIO_OFFLINE"] == "1"`.
- `result.unavailable`: list of source ids that are unavailable and have no fallback source; their records have status
  `unavailable` (or `skipped-no-account` when skipped for a missing account variable).
- `recipe` is a dict `{"stages": [{"id": <stage id>, "inputs": [{"id": <source id>, "sha256": ...} | {"stage": ...}], ...}]}`
  (spec 001 data-model section 3.2); `result.not_run` is a dict stage id -> reason (1 to 300 characters naming the source)
  for every stage that lists an unavailable source among its inputs. Stages with only available inputs are not listed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import _p008_kit as kit
import httpx
import pytest

ERA5_URL = "https://cds.example.org/api/era5-wind.nc"
GHCNH_URL = "https://noaa.example.org/ghcnh/station.psv"
SENTINEL = "SENTINEL-KEY-9f3a1c7e-do-not-leak"
ERA5, GHCNH = kit.payload(900, 1), kit.payload(700, 2)


def _entries(fallback_sources: list[str] | None = None):
    fb = ["ghcnh"] if fallback_sources is None else fallback_sources
    era5 = kit.entry(
        "era5",
        [kit.file_rec(ERA5_URL, ERA5)],
        access="account",
        spdx="CC-BY-4.0",
        licence_class="attribution",
        attribution="Contains modified reanalysis information (2026).",
        account={"needed": True, "env_var": "ERA5_API_KEY"},
        fallback={"sources": fb, "text": "station hourly records replace the reanalysis"},
    )
    ghcnh = kit.entry("ghcnh", [kit.file_rec(GHCNH_URL, GHCNH)])
    return [era5, ghcnh]


def _recipe() -> dict:
    return {
        "stages": [
            {"id": "s10_preprocess", "inputs": [{"id": "era5", "sha256": kit.sha256_hex(ERA5)}]},
            {"id": "s20_feature_extraction", "inputs": [{"id": "ghcnh", "sha256": kit.sha256_hex(GHCNH)}]},
            {"id": "s05_synthesize", "inputs": []},
        ]
    }


# ------------------------------------------------------------------------------------------------ FR-008-13
@pytest.mark.req("FR-008-13")
@pytest.mark.parametrize("env", [kit.env_with(), kit.env_with(ERA5_API_KEY="")], ids=["unset", "empty"])
def test_missing_account_key_skips_the_entry_and_applies_the_fallback(env: dict, tmp_path: Path) -> None:
    net = kit.Net({ERA5_URL: ERA5, GHCNH_URL: GHCNH})
    result = kit.run(tmp_path, _entries(), net, env=env)
    assert ERA5_URL not in net.urls, "an account-bound entry without its key is never requested"
    era5 = next(r for r in result.records if r["source"] == "era5")
    assert kit.schema_errors("fetch-record.schema.json", era5) == []
    assert era5["status"] == "fallback-used" and era5["fallback_sources"] == ["ghcnh"]
    assert era5["stored_as"] is None and era5["sha256"] is None and era5["bytes"] is None and era5["attempts"] == 0
    ghcnh = next(r for r in result.records if r["source"] == "ghcnh")
    assert ghcnh["status"] == "verified"
    assert result.exit_status == 0, "a declared fallback is an honest outcome, not a failure"
    assert not (tmp_path / "data" / "external" / "era5").exists()


@pytest.mark.req("FR-008-13")
def test_fallback_ids_keep_their_order_of_preference(tmp_path: Path) -> None:
    extra = kit.entry("isd-noaa", [kit.file_rec("https://noaa.example.org/isd/a.csv", b"abc")])
    entries = [*_entries(["isd-noaa", "ghcnh"]), extra]
    net = kit.Net({GHCNH_URL: GHCNH, "https://noaa.example.org/isd/a.csv": b"abc"})
    result = kit.run(tmp_path, entries, net)
    era5 = next(r for r in result.records if r["source"] == "era5")
    assert era5["fallback_sources"] == ["isd-noaa", "ghcnh"]


@pytest.mark.req("FR-008-13")
@pytest.mark.parametrize("scenario", ["unset", "key-ok", "key-denied"])
def test_the_key_value_never_appears_anywhere(scenario: str, tmp_path: Path, caplog, capsys) -> None:
    caplog.set_level(logging.DEBUG)
    env = kit.env_with() if scenario == "unset" else kit.env_with(ERA5_API_KEY=SENTINEL)
    routes = {
        ERA5_URL: ERA5 if scenario != "key-denied" else (lambda r: httpx.Response(401, content=b"denied")),
        GHCNH_URL: GHCNH,
    }
    result = kit.run(tmp_path, _entries(), kit.Net(routes), env=env)
    haystacks = [
        json.dumps(result.records, default=str),
        json.dumps(result.manifest, default=str),
        repr(result),
        " ".join(f"{type(e).__name__}: {e} {e!r}" for e in result.errors.values()),
        caplog.text,
        " ".join(r.getMessage() for r in caplog.records),
    ]
    out, err = capsys.readouterr()
    haystacks += [out, err]
    for path in kit.files_under(tmp_path / "data"):
        haystacks.append(path.read_bytes().decode("latin-1"))
    for h in haystacks:
        assert SENTINEL not in h


# ------------------------------------------------------------------------------------------------ FR-008-14
@pytest.mark.req("FR-008-14")
@pytest.mark.parametrize("no_fallback", [{"sources": [], "text": "no substitute"}], ids=["empty-sources"])
def test_no_fallback_source_makes_it_unavailable_and_its_consumers_not_run(no_fallback: dict, tmp_path: Path) -> None:
    entries = _entries()
    entries[0]["fallback"] = no_fallback
    net = kit.Net({ERA5_URL: ERA5, GHCNH_URL: GHCNH})
    result = kit.run(tmp_path, entries, net, recipe=_recipe())
    assert result.unavailable == ["era5"]
    era5 = next(r for r in result.records if r["source"] == "era5")
    assert era5["status"] in {"unavailable", "skipped-no-account"} and era5["fallback_sources"] == []
    assert set(result.not_run) == {"s10_preprocess"}
    reason = result.not_run["s10_preprocess"]
    assert 1 <= len(reason) <= 300 and "era5" in reason
    # no substitution: the other source is fetched for its own consumers only, nothing is copied under era5's name
    assert kit.files_under(tmp_path / "data" / "external" / "era5") == []
    assert kit.files_under(tmp_path / "data" / "raw" / "era5") == []


@pytest.mark.req("FR-008-14")
def test_a_source_without_any_fallback_key_that_fails_verification_is_unavailable(tmp_path: Path) -> None:
    entries = [kit.entry("lone", [kit.file_rec("https://example.org/lone.bin", ERA5)])]  # no `fallback` at all
    net = kit.Net({"https://example.org/lone.bin": kit.payload(900, 99)})  # tampered bytes
    recipe = {"stages": [{"id": "s10_preprocess", "inputs": [{"id": "lone", "sha256": kit.sha256_hex(ERA5)}]}]}
    result = kit.run(tmp_path, entries, net, recipe=recipe)
    assert result.unavailable == ["lone"] and result.exit_status != 0
    assert list(result.not_run) == ["s10_preprocess"]
    assert not (tmp_path / "data" / "raw" / "lone").exists()


@pytest.mark.req("FR-008-14")
def test_a_source_that_cannot_be_downloaded_is_unavailable_too(tmp_path: Path) -> None:
    entries = [kit.entry("gone", [kit.file_rec("https://example.org/gone.bin", ERA5)])]
    net = kit.Net({})  # 404
    recipe = {"stages": [{"id": "s20_feature_extraction", "inputs": [{"id": "gone", "sha256": kit.sha256_hex(ERA5)}]}]}
    result = kit.run(tmp_path, entries, net, recipe=recipe)
    assert result.unavailable == ["gone"] and list(result.not_run) == ["s20_feature_extraction"]


@pytest.mark.req("FR-008-14")
def test_a_fallback_declared_means_consumers_are_not_marked_not_run(tmp_path: Path) -> None:
    net = kit.Net({ERA5_URL: ERA5, GHCNH_URL: GHCNH})
    result = kit.run(tmp_path, _entries(), net, recipe=_recipe())
    assert result.unavailable == [] and result.not_run == {}


# ------------------------------------------------------------------------------------------------ FR-008-16
@pytest.mark.req("FR-008-16")
@pytest.mark.parametrize("how", ["env", "argument"])
def test_offline_mode_opens_no_connection_and_uses_verified_cache_only(how: str, tmp_path: Path) -> None:
    cached = tmp_path / "data" / "raw" / "ghcnh"
    cached.mkdir(parents=True)
    (cached / "station.psv").write_bytes(GHCNH)
    entries = [
        kit.entry("ghcnh", [kit.file_rec(GHCNH_URL, GHCNH)]),
        kit.entry("other", [kit.file_rec("https://example.org/other.bin", ERA5)]),
    ]
    recipe = {"stages": [{"id": "s10_preprocess", "inputs": [{"id": "other", "sha256": kit.sha256_hex(ERA5)}]}]}
    net = kit.Net({"https://example.org/other.bin": ERA5}, forbid=True)
    kwargs = {"env": kit.env_with(PITSTUDIO_OFFLINE="1")} if how == "env" else {"offline": True}
    result = kit.run(tmp_path, entries, net, recipe=recipe, **kwargs)
    assert net.requests == []
    by_source = {r["source"]: r for r in result.records}
    assert by_source["ghcnh"]["status"] == "verified"
    assert by_source["other"]["status"] in {"unavailable", "skipped-no-account"}
    assert result.unavailable == ["other"] and list(result.not_run) == ["s10_preprocess"]
    assert not (tmp_path / "data" / "raw" / "other").exists()


@pytest.mark.req("FR-008-16")
def test_offline_mode_does_not_trust_a_corrupted_cache_file(tmp_path: Path) -> None:
    cached = tmp_path / "data" / "raw" / "ghcnh"
    cached.mkdir(parents=True)
    (cached / "station.psv").write_bytes(GHCNH[:-1] + b"!")
    net = kit.Net(forbid=True)
    result = kit.run(tmp_path, [kit.entry("ghcnh", [kit.file_rec(GHCNH_URL, GHCNH)])], net, offline=True)
    assert net.requests == [] and result.exit_status != 0
    assert all(r["status"] != "verified" for r in result.records)


@pytest.mark.req("FR-008-16")
@pytest.mark.parametrize("value", ["0", "", "no"])
def test_offline_flag_other_than_one_does_not_block_the_network(value: str, tmp_path: Path) -> None:
    net = kit.Net({GHCNH_URL: GHCNH})
    result = kit.run(
        tmp_path, [kit.entry("ghcnh", [kit.file_rec(GHCNH_URL, GHCNH)])], net, env=kit.env_with(PITSTUDIO_OFFLINE=value)
    )
    assert result.exit_status == 0 and len(net.requests) == 1
