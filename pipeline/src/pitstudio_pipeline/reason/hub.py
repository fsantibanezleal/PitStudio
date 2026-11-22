"""Model provenance and gated access (FR-015-03, FR-015-04, FR-015-07, FR-015-08).

The Cosmos arm uses weights only from `nvidia/Cosmos-Reason2-2B` at the pinned full revision, the control only from
`Qwen/Qwen3-VL-2B-Instruct` at its pinned revision; every downloaded file is verified against the SHA-256 and byte count
of the pin file and is stored only after it matched. Anything else is a `ProvenanceError` (exit code 2). The hub is a
seam: `hub.fetch(repository, revision, name) -> bytes` (or `hub.fetch_to(repository, revision, name, path)` for large
files) and `hub.access(repository, revision, *, token) -> int` (HTTP status of the metadata request).

The Hugging Face token never reaches a log line, an exception, a manifest or a record: `redact` replaces it by
`<redacted>` and errors from the hub are re-raised without chaining the original text.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pitstudio_pipeline.download.hashing import sha256_file

LOG = logging.getLogger("pitstudio_pipeline.reason")
REDACTED = "<redacted>"
EXIT_CODE = 2
COSMOS_REPOSITORY = "nvidia/Cosmos-Reason2-2B"
QWEN_REPOSITORY = "Qwen/Qwen3-VL-2B-Instruct"
GATED_REASON = "gated terms not accepted or token missing"
EXPECTED = {"cosmos": COSMOS_REPOSITORY, "qwen": QWEN_REPOSITORY}
ARM_ORDER = ("cosmos-q8_0", "cosmos-bf16", "qwen-base", "detector-rule", "constant")
_REVISION = {"cosmos": re.compile(r"9ce19a1[0-9a-f]{33}"), "qwen": re.compile(r"[0-9a-f]{40}")}
_PLAIN_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*(/[A-Za-z0-9_][A-Za-z0-9._-]*)*")


class ProvenanceError(Exception):
    """A repository, revision or file is not the pinned one; `repository` and `file` name it."""

    exit_code = EXIT_CODE

    def __init__(self, repository: str, reason: str, file: str | None = None) -> None:
        where = f"{repository}:{file}" if file is not None else repository
        super().__init__(f"{where}: {reason}")
        self.repository = repository
        self.file = file
        self.reason = reason


# ------------------------------------------------------------------------------------------------ redaction
def redact(text: str, token: str | None) -> str:
    """Replace every occurrence of a non-empty token by `<redacted>`."""
    if not token:
        return text
    return text.replace(token, REDACTED)


def redact_obj(obj: Any, token: str | None) -> Any:
    """`redact` over the strings, keys and values of nested dicts, lists and tuples."""
    if isinstance(obj, str):
        return redact(obj, token)
    if isinstance(obj, dict):
        return {redact_obj(k, token): redact_obj(v, token) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v, token) for v in obj]
    if isinstance(obj, tuple):
        return tuple(redact_obj(v, token) for v in obj)
    return obj


# ------------------------------------------------------------------------------------------------ provenance
def check_model_config(cfg: Mapping[str, Any], pins: Mapping[str, Any]) -> None:
    """Every present entry (`cosmos`, `qwen`) must equal the pinned repository and revision exactly."""
    for slot, entry in cfg.items():
        if slot not in EXPECTED:
            raise ProvenanceError(str(slot), "this slot is not part of the lane (only cosmos and qwen)")
        pin = pins["models"][slot]
        if not isinstance(entry, Mapping) or not isinstance(entry.get("repository"), str):
            raise ProvenanceError(str(slot), "the configuration entry needs a repository and a revision")
        repo, rev = entry["repository"], entry.get("revision")
        if repo != pin["repository"]:
            raise ProvenanceError(repo, f"is not the pinned repository {pin['repository']}")
        if rev != pin["revision"]:
            raise ProvenanceError(repo, f"revision {rev!r} is not the pinned revision {pin['revision']}")


def _check_pin_entry(pins: Mapping[str, Any], which: Any) -> tuple[str, str, Mapping[str, Any]]:
    if which not in EXPECTED:
        raise ProvenanceError(str(which), "unknown model slot (cosmos or qwen)")
    pin = pins["models"][which]
    repo, rev = pin["repository"], pin["revision"]
    if repo != EXPECTED[which]:
        raise ProvenanceError(str(repo), f"the pin names another repository than {EXPECTED[which]}")
    if not _REVISION[which].fullmatch(str(rev)):
        raise ProvenanceError(repo, f"revision {rev!r} is not a full pinned revision")
    for name in pin["files"]:
        if not isinstance(name, str) or not _PLAIN_NAME.fullmatch(name) or ".." in name.split("/"):
            raise ProvenanceError(repo, "the pinned file name is not a plain relative name", file=str(name))
    return repo, rev, pin["files"]


def _verify_file(path: Path, repo: str, name: str, pin: Mapping[str, Any]) -> None:
    if path.stat().st_size != pin["bytes"]:
        raise ProvenanceError(repo, f"{path.stat().st_size} bytes, the pin says {pin['bytes']}", file=name)
    if sha256_file(path) != pin["sha256"]:
        raise ProvenanceError(repo, "SHA-256 differs from the pin", file=name)


def download_model(pins: Mapping[str, Any], which: str, dest: Path, *, hub: Any) -> Path:
    """Download the pinned files of one model into `dest/<org>/<name>/<revision>/`, verified before they are kept."""
    repo, rev, files = _check_pin_entry(pins, which)
    org, name = repo.split("/")
    snapshot = Path(dest) / org / name / rev
    for fname in sorted(files):
        final = snapshot / fname
        part = final.with_name(final.name + ".part")
        part.parent.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(hub, "fetch_to"):
                hub.fetch_to(repo, rev, fname, part)
            else:
                part.write_bytes(hub.fetch(repo, rev, fname))
        except FileNotFoundError:
            part.unlink(missing_ok=True)
            raise ProvenanceError(repo, "the hub has no such file at the pinned revision", file=fname) from None
        except PermissionError:
            part.unlink(missing_ok=True)
            raise ProvenanceError(repo, "the hub refused access (gated terms or token)", file=fname) from None
        try:
            _verify_file(part, repo, fname, files[fname])
        except ProvenanceError:
            part.unlink(missing_ok=True)
            raise
        part.replace(final)
    return snapshot


def verify_snapshot(snapshot: Path, pins: Mapping[str, Any], which: str) -> None:
    """Every pinned file of a model is in `snapshot` with its pinned byte count and SHA-256."""
    repo, _, files = _check_pin_entry(pins, which)
    for fname, pin in files.items():
        path = Path(snapshot) / fname
        if not path.is_file():
            raise ProvenanceError(repo, "missing from the snapshot", file=fname)
        _verify_file(path, repo, fname, pin)


# ----------------------------------------------------------------------------------- gated access and arms
def _token(env: Mapping[str, str]) -> str | None:
    value = env.get("HF_TOKEN")
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve_access(pins: Mapping[str, Any], *, env: Mapping[str, str], hub: Any, out_dir: Path) -> dict[str, Any]:
    """Which models can be used: the control never needs a token; Cosmos needs a read token the hub accepts. Writes
    `access.json` (token redacted) and returns the states."""
    token = _token(env)
    states: dict[str, Any] = {}
    cosmos = pins["models"]["cosmos"]
    if token is None:
        states["cosmos"] = {"status": "not_run", "reason": GATED_REASON}
    else:
        try:
            code = hub.access(cosmos["repository"], cosmos["revision"], token=token)
        except Exception as exc:
            raise ProvenanceError(cosmos["repository"], redact(f"{type(exc).__name__}: {exc}", token)) from None
        if code == 200:
            states["cosmos"] = {"status": "available"}
        elif code in (401, 403):
            states["cosmos"] = {"status": "not_run", "reason": GATED_REASON}
        else:
            states["cosmos"] = {"status": "not_run", "reason": f"hub answered HTTP {code} for the Cosmos repository"}
    qwen = pins["models"]["qwen"]
    try:
        code = hub.access(qwen["repository"], qwen["revision"], token=None)
    except Exception as exc:
        raise ProvenanceError(qwen["repository"], redact(f"{type(exc).__name__}: {exc}", token)) from None
    states["qwen"] = (
        {"status": "available"}
        if code == 200
        else {"status": "not_run", "reason": f"hub answered HTTP {code} for the control repository"}
    )
    LOG.info("model access: cosmos %s, qwen %s", states["cosmos"]["status"], states["qwen"]["status"])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "access.json").write_text(json.dumps(redact_obj(states, token), indent=2) + "\n", encoding="utf-8")
    return states


def runnable_arms(states: Mapping[str, Any]) -> list[str]:
    """The arms to run, in the order of FR-015-28; the Cosmos arms need Cosmos, the control needs Qwen."""
    cosmos_ok = states["cosmos"]["status"] == "available"
    qwen_ok = states["qwen"]["status"] == "available"
    return [
        a
        for a in ARM_ORDER
        if not (a.startswith("cosmos") and not cosmos_ok) and not (a == "qwen-base" and not qwen_ok)
    ]


class HfHub:
    """The real hub seam (huggingface_hub): metadata status and file download with the token, never logged."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def access(self, repository: str, revision: str, *, token: str | None) -> int:
        import httpx

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = f"https://huggingface.co/api/models/{repository}/revision/{revision}"
        return httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True).status_code

    def fetch_to(self, repository: str, revision: str, name: str, path: Path) -> None:
        import httpx

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        url = f"https://huggingface.co/{repository}/resolve/{revision}/{name}"
        digest = hashlib.sha256()
        with httpx.stream("GET", url, headers=headers, timeout=60.0, follow_redirects=True) as response:
            if response.status_code in (401, 403):
                raise PermissionError(response.status_code)
            if response.status_code == 404:
                raise FileNotFoundError(name)
            response.raise_for_status()
            with Path(path).open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    digest.update(chunk)
                    handle.write(chunk)
