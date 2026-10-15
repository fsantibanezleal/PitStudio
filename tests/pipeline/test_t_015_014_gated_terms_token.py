# ruff: noqa: E501
"""T-015-014: the gated-terms "not run" degradation and the redaction of the Hugging Face token (canary test).

Requirements: FR-015-07, FR-015-08.

Spec: specs/015-vlm/spec.md
- FR-015-07: if no Hugging Face read token is available, or the hub answers 401 or 403 for the Cosmos repository, then every Cosmos arm is
  recorded "not run" with the reason "gated terms not accepted or token missing"; tasks A-C still run on the Qwen control and the baselines; the
  Cosmos panels and the Cosmos tool page show "not run" (the web part is tests/e2e T-015-063).
- FR-015-08: if the token value would appear in a log line, an exception message, a manifest or a record, the lane writes `<redacted>` in its place;
  a run with a canary token leaves zero occurrences of the canary in every output file.

Oracle: the exact reason text of the spec; the arm lists of FR-015-28 (Cosmos Q8_0 and BF16 are the Cosmos arms; the control and the two
baselines remain); a canary token string planted in the environment, in the fake hub's error messages and request records, searched for in every
byte of every output file, in captured log records and in formatted exception tracebacks; `str.replace` as the reference for redaction.

Expected API of the implementation (package `pitstudio_pipeline`), `pitstudio_pipeline.reason.hub`:
- `REDACTED == "<redacted>"`; `redact(text, token) -> str` (every occurrence of a non-empty token replaced; no-op for an empty token);
  `redact_obj(obj, token)` the same over the strings, keys and values of nested dicts, lists and tuples.
- `resolve_access(pins, *, env, hub, out_dir) -> dict`: `env` is an environment mapping (the token is `env["HF_TOKEN"]`); `hub.access(repository,
  revision, *, token) -> int` returns the HTTP status of the repository's metadata request. Returns
  `{"cosmos": {"status": "not_run", "reason": "gated terms not accepted or token missing"} | {"status": "available"}, "qwen": {"status": "available"}}`,
  and writes it to `out_dir / "access.json"` (token redacted). Without a token the hub is not asked about the Cosmos repository; status 401 and 403
  give "not_run"; the control never needs a token. Nothing it logs (logger `pitstudio_pipeline.reason`), writes or raises contains the token; errors raised
  from the hub are re-raised without the original text chained (`raise ... from None`).
- `runnable_arms(states) -> list[str]`: the arms to run, in the order "cosmos-q8_0", "cosmos-bf16", "qwen-base", "detector-rule", "constant", without the
  Cosmos arms when Cosmos is "not_run".
"""

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path

import _p015_pins_kit as kit
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pitstudio_pipeline.reason import hub as hubmod

REASON = "gated terms not accepted or token missing"
CANARY = "hf_CANARYtoken0123456789abcdefABCDEF"
ALL_ARMS = ["cosmos-q8_0", "cosmos-bf16", "qwen-base", "detector-rule", "constant"]


class AccessHub:
    """Fake hub metadata endpoint: `statuses[repo]` is the HTTP status; `explode` makes every call raise an error that quotes the token."""

    def __init__(self, statuses: dict | None = None, explode: bool = False) -> None:
        self.statuses = statuses or {}
        self.explode = explode
        self.calls: list[tuple[str, str, str | None]] = []

    def access(self, repository: str, revision: str, *, token: str | None) -> int:
        self.calls.append((repository, revision, token))
        if self.explode:
            raise RuntimeError(
                f"401 Client Error: Unauthorized for url https://huggingface.co/api/models/{repository} (Authorization: Bearer {token})"
            )
        return self.statuses.get(repository, 200)


@pytest.fixture
def env(tmp_path: Path) -> kit.Env:
    return kit.build_env(tmp_path)


def _cosmos_calls(h: AccessHub) -> list:
    return [c for c in h.calls if c[0] == kit.COSMOS_REPO]


@pytest.mark.req("FR-015-07")
def test_without_a_token_every_cosmos_arm_is_not_run_and_the_hub_is_not_asked_about_cosmos(
    env: kit.Env, tmp_path: Path
) -> None:
    h = AccessHub()
    states = hubmod.resolve_access(env.pins, env={}, hub=h, out_dir=tmp_path / "out")
    assert states["cosmos"] == {"status": "not_run", "reason": REASON}
    assert states["qwen"]["status"] == "available"
    assert _cosmos_calls(h) == []
    assert json.loads((tmp_path / "out" / "access.json").read_text(encoding="utf-8")) == states


@pytest.mark.req("FR-015-07")
@pytest.mark.parametrize("token", ["", "   "])
def test_an_empty_or_blank_token_counts_as_missing(env: kit.Env, tmp_path: Path, token: str) -> None:
    states = hubmod.resolve_access(env.pins, env={"HF_TOKEN": token}, hub=AccessHub(), out_dir=tmp_path / "out")
    assert states["cosmos"] == {"status": "not_run", "reason": REASON}


@pytest.mark.req("FR-015-07")
@pytest.mark.parametrize("status", [401, 403])
def test_a_401_or_403_from_the_hub_for_cosmos_gives_not_run_with_the_same_reason(
    env: kit.Env, tmp_path: Path, status: int
) -> None:
    h = AccessHub({kit.COSMOS_REPO: status})
    states = hubmod.resolve_access(env.pins, env={"HF_TOKEN": CANARY}, hub=h, out_dir=tmp_path / "out")
    assert states["cosmos"] == {"status": "not_run", "reason": REASON}
    assert states["qwen"]["status"] == "available"
    assert [(c[0], c[1]) for c in _cosmos_calls(h)] == [
        (kit.COSMOS_REPO, kit.COSMOS_REV)
    ]  # asked once, at the pinned revision


@pytest.mark.req("FR-015-07")
def test_with_a_token_accepted_by_the_hub_cosmos_is_available(env: kit.Env, tmp_path: Path) -> None:
    h = AccessHub()
    states = hubmod.resolve_access(env.pins, env={"HF_TOKEN": CANARY}, hub=h, out_dir=tmp_path / "out")
    assert states["cosmos"] == {"status": "available"}
    assert states["qwen"] == {"status": "available"}
    assert _cosmos_calls(h)[0][2] == CANARY  # the token goes to the hub, and only there


@pytest.mark.req("FR-015-07")
def test_the_control_does_not_need_a_token(env: kit.Env, tmp_path: Path) -> None:
    h = AccessHub()
    hubmod.resolve_access(env.pins, env={}, hub=h, out_dir=tmp_path / "out")
    assert all(c[2] is None for c in h.calls if c[0] == kit.QWEN_REPO)


@pytest.mark.req("FR-015-07")
def test_tasks_still_run_on_the_control_and_the_baselines_when_cosmos_is_not_run() -> None:
    off = {"cosmos": {"status": "not_run", "reason": REASON}, "qwen": {"status": "available"}}
    on = {"cosmos": {"status": "available"}, "qwen": {"status": "available"}}
    assert hubmod.runnable_arms(off) == ["qwen-base", "detector-rule", "constant"]
    assert hubmod.runnable_arms(on) == ALL_ARMS


@pytest.mark.req("FR-015-08")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"token={CANARY}", "token=<redacted>"),
        (f"{CANARY}{CANARY}", "<redacted><redacted>"),
        (f"Authorization: Bearer {CANARY}\n", "Authorization: Bearer <redacted>\n"),
        ("no secret here", "no secret here"),
        ("", ""),
    ],
)
def test_redact_replaces_every_occurrence_of_the_token(text: str, expected: str) -> None:
    assert hubmod.REDACTED == "<redacted>"
    assert hubmod.redact(text, CANARY) == expected


@pytest.mark.req("FR-015-08")
def test_an_empty_token_redacts_nothing() -> None:
    assert hubmod.redact("abc", "") == "abc"
    assert hubmod.redact("abc", None) == "abc"  # type: ignore[arg-type]


@pytest.mark.req("FR-015-08")
def test_redact_obj_walks_nested_structures_including_keys() -> None:
    doc = {"a": CANARY, CANARY: [1, f"x{CANARY}y", {"k": (CANARY, 2.5, None, True)}], "n": 3}
    out = hubmod.redact_obj(doc, CANARY)
    assert CANARY not in json.dumps(out, default=str)
    assert out["a"] == "<redacted>"
    assert out["<redacted>"][1] == "x<redacted>y"
    assert out["n"] == 3
    inner = out["<redacted>"][2]["k"]
    assert inner[0] == "<redacted>"
    assert list(inner[1:]) == [2.5, None, True]


@pytest.mark.req("FR-015-08")
@given(
    st.text(min_size=0, max_size=40),
    st.text(min_size=0, max_size=40),
    st.text(min_size=8, max_size=24, alphabet="abcdefXYZ0123456789_"),
)
def test_property_redact_equals_replace_and_leaves_no_token_and_is_idempotent(a: str, b: str, token: str) -> None:
    text = f"{a}{token}{b}{token}"
    out = hubmod.redact(text, token)
    assert out == text.replace(token, "<redacted>")


def _all_bytes(folder: Path) -> list[tuple[Path, bytes]]:
    return [(p, p.read_bytes()) for p in sorted(folder.rglob("*")) if p.is_file()]


@pytest.mark.req("FR-015-08")
def test_a_run_with_a_canary_token_leaves_no_occurrence_in_any_output_file_log_record_or_exception(
    env: kit.Env, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    out = tmp_path / "out"
    texts: list[str] = []
    chained: list[BaseException | None] = []
    caplog.set_level(logging.DEBUG)
    for hub_obj in (
        AccessHub(),
        AccessHub({kit.COSMOS_REPO: 401}),
        AccessHub({kit.COSMOS_REPO: 403}),
        AccessHub(explode=True),
    ):
        try:
            states = hubmod.resolve_access(env.pins, env={"HF_TOKEN": CANARY}, hub=hub_obj, out_dir=out)
            texts.append(json.dumps(states))
        except Exception as e:
            chained.append(e.__cause__)  # the hub error that quoted the token must not be chained
            texts.append("".join(traceback.format_exception(e)))
            texts.append(str(e) + repr(e))
    assert all(c is None for c in chained)
    files = _all_bytes(out)
    assert files, "the run must write its manifest"
    for p, data in files:
        assert CANARY.encode() not in data, p
        assert CANARY.encode("utf-16-le") not in data, p
    for t in texts:
        assert CANARY not in t
    for rec in caplog.records:
        assert CANARY not in rec.getMessage()
        assert CANARY not in str(rec.__dict__)
    assert CANARY not in caplog.text
