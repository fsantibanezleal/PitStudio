"""Shared helpers and hand-written oracle tables of the spec 001-contracts tests (locked with T-001-004).

Nothing here imports first-party code: every table below is copied by hand from the normative data model
(specs/001-contracts/data-model.md) or from RFC / reference-library behaviour, never from the code under test.

Expected public API of the implementation (stated once, used by every test file of this spec):

* ``pitstudio.contracts`` exports ``load_json(path, *, max_bytes=None)``, ``load_yaml(path, *, max_bytes=None)``,
  ``dump_json(obj) -> bytes``, ``validate(document, schema_name) -> list`` of error objects with the attributes
  ``pointer``, ``keyword`` and ``message``, ``ContractError`` (a ``ValueError`` subclass whose ``error_class``
  attribute is the error class string, e.g. ``"privacy-leak"``; ``str(exc)`` names the file and the line or the JSON
  pointer),
  ``licence_class_of(classes) -> str`` and ``load_sources(path) -> dict`` (strict YAML load, schema validation and the
  per-file licence-class rule of FR-001-58).
* ``pitstudio.contracts.lane.lane_of(measurements) -> "live" | "replay"``; ``pitstudio.contracts.jcs.canonicalize(value)
  -> bytes`` (RFC 8785).
* ``tools/check_contracts.py [--root DIR] [--json] [--release-assets DIR]``: ``--root`` selects the tree whose documents
  are checked (default: the repository), the schemas always come from the repository's own ``contracts/`` folder,
  ``--json`` prints a JSON list of findings ``{"file", "rule", "pointer", "message", "error_class"}`` on stdout, exit
  code 0 (clean), 1 (findings), 2 (usage error). A finding of a cross-file rule carries that rule's id (``FR-001-13``,
  ``FR-001-15``, ...); a violation of a document's schema is a finding of any rule id (the tests only need its file and
  JSON pointer); ``error_class`` is null except for ``privacy-leak`` and ``source-class-too-permissive``.
* ``tools/gen_types.py [--check] [--contracts DIR] [--out DIR]``.
* ``schema_name`` of ``validate`` is the schema stem (``manifest``, ``recipe``, ``tools``, ``sources``,
  ``capabilities``) or ``<stem>#/$defs/<name>`` for one definition (e.g. ``recipe#/$defs/job_request``).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLEAN_REPO = FIXTURES / "repo" / "clean"
CHECKER = ROOT / "tools" / "check_contracts.py"
GEN_TYPES = ROOT / "tools" / "gen_types.py"
SCHEMA_STEMS = ("manifest", "recipe", "tools", "sources", "capabilities")
SCHEMA_ID = "https://fsantibanezleal.github.io/PitStudio/contracts/{name}.schema.json"
META_2020_12 = "https://json-schema.org/draft/2020-12/schema"

CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]  # data-model 1.6
LOCAL_ONLY = "measured locally, not published (licence)"  # data-model 1.6

# data-model 3.3: frozen stage ids and the environments each may run in
STAGE_ENVS: dict[str, set[str]] = {
    "s00_download": {"pipeline"},
    "s05_synthesize": {"pipeline"},
    "s10_preprocess": {"pipeline"},
    "s20_feature_extraction": {"pipeline"},
    "s30_train": {"pipeline"},
    "s40_infer": {"pipeline"},
    "s50_evaluate": {"pipeline"},
    "s60_export": {"pipeline"},
    "s62_accel": {"accel"},
    "s64_bench": {"accel", "pipeline"},
    "st10_terrain": {"studio"},
    "st20_pit_design": {"studio"},
    "st30_assets": {"studio"},
    "st40_compose": {"studio"},
    "st45_validate": {"studio"},
    "st45b_kit_validate": {"kit"},
    "st50_physics": {"studio"},
    "st52_rtx_render": {"isaac"},
    "st53_sensors": {"rtx"},
    "st54_vehicles": {"isaac"},
    "st55_sdg": {"isaac"},
    "st56_encode": {"studio"},
    "st57_rain_lidar": {"isaac"},
    "st58_kit_capture": {"kit"},
    "st58b_capture_splat": {"external"},
    "st59_reason_bench": {"reason"},
    "st59a_vqa": {"reason"},
    "st59b_plausibility": {"reason"},
    "st59c_captions": {"reason"},
    "st60_il_train": {"isaaclab"},
    "st61_il_mpm_eval": {"isaaclab"},
}
RECIPE_ENVS = ["studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"]  # data-model 1.6

# data-model 5.4: licence-class lattice (rank = position)
LICENCE_ORDER = [
    "public-domain",
    "open-no-attribution",
    "own",
    "attribution",
    "share-alike",
    "display-only",
    "reference-only",
]
LICENCE_RANK = {c: i for i, c in enumerate(LICENCE_ORDER)}
NO_ATTRIBUTION_CLASSES = {"public-domain", "open-no-attribution", "own"}

# data-model 5.2: SPDX allowlist; allowed licence classes of a source by (spdx, kind)
SPDX_ALLOWLIST = [
    "LicenseRef-USGov-PD",
    "CC0-1.0",
    "DL-DE-ZERO-2.0",
    "CC-BY-4.0",
    "LicenseRef-Copernicus-CLMS",
    "CC-BY-SA-3.0",
    "CC-BY-SA-4.0",
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "MPL-2.0",
    "LGPL-2.1-or-later",
    "LicenseRef-TOST-1.0",
    "LicenseRef-NVIDIA-Open-Model",
    "LicenseRef-NVIDIA-SLA",
    "LicenseRef-NvidiaProprietary",
    "LicenseRef-NVIDIA-Omniverse",
    "LicenseRef-TensorRT-SLA",
    "LicenseRef-TensorRT-RTX-SLA",
]
SOURCE_ALLOWED: dict[tuple[str, str], set[str]] = {
    ("LicenseRef-USGov-PD", "real"): {"public-domain"},
    ("CC0-1.0", "real"): {"open-no-attribution"},
    ("DL-DE-ZERO-2.0", "real"): {"open-no-attribution"},
    ("CC-BY-4.0", "real"): {"attribution"},
    ("LicenseRef-Copernicus-CLMS", "real"): {"attribution"},
    ("CC-BY-SA-3.0", "real"): {"share-alike"},
    ("CC-BY-SA-4.0", "real"): {"share-alike"},
    ("CC-BY-4.0", "synthetic"): {"own"},
    ("Apache-2.0", "synthetic"): {"own"},
    ("LicenseRef-NVIDIA-Open-Model", "synthetic"): {"display-only"},
}
# data-model 5.3: performance-restricted licences (a tool listing one must be `performance: local-only`)
PERFORMANCE_RESTRICTED = [
    "LicenseRef-NVIDIA-SLA",
    "LicenseRef-NvidiaProprietary",
    "LicenseRef-NVIDIA-Omniverse",
    "LicenseRef-TensorRT-RTX-SLA",
]
# data-model 4.3: the 20 studio tools and their status at first commit
STUDIO_TOOLS_NOT_YET_RUN = [
    "openusd",
    "warp",
    "newton",
    "mujoco-warp",
    "physx-ovphysx",
    "ovrtx",
    "isaac-sim-replicator",
    "isaac-lab",
    "kit-usd-composer-explorer",
    "cosmos-reason-2",
    "pytorch",
    "onnx-runtime",
    "tensorrt",
    "nvenc-ffmpeg",
    "nsight-nvml",
    "threejs-r3f-3d-tiles",
    "rapier-webgpu-pyodide",
]
STUDIO_TOOLS_NOT_ADOPTED = ["cuopt", "physicsnemo", "cosmos-predict-transfer"]

WINDOWS_DEVICE_NAMES = (
    ["CON", "PRN", "AUX", "NUL"] + [f"COM{i}" for i in range(1, 10)] + [f"LPT{i}" for i in range(1, 10)]
)

# data-model 1.3: shared patterns (identical text in every schema that defines them) and maxLength
PATTERNS: dict[str, tuple[str, int]] = {
    "slug": (r"^[a-z0-9][a-z0-9-]{0,63}$", 64),
    "tool_id": (r"^[a-z][a-z0-9-]{1,47}$", 48),
    "artefact_id": (r"^[a-z0-9][a-z0-9_-]{0,95}$", 96),
    "run_id": (r"^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$", 64),
    "variant": (r"^[a-z0-9][a-z0-9-]{0,31}$", 32),
    "sha256": (r"^[0-9a-f]{64}$", 64),
    "git_sha": (r"^[0-9a-f]{40}$", 40),
    "utc_timestamp": (
        r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?Z$",
        32,
    ),
    "date": (r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$", 10),
    "https_url": (
        r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
        2048,
    ),
    "release_tag": (r"^assets-v[0-9]+\.[0-9]{2}\.[0-9]{3}$", 32),
    "relpath": (
        r"^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        255,
    ),
    "relglob": (
        r"^[A-Za-z0-9_*?]([A-Za-z0-9._*? -]{0,98}[A-Za-z0-9_*?])?(/[A-Za-z0-9_*?]([A-Za-z0-9._*? -]{0,98}[A-Za-z0-9_*?])?){0,15}$",  # noqa: E501
        255,
    ),
    "module_path": (r"^[a-z_][a-z0-9_]{0,63}(\.[a-z_][a-z0-9_]{0,63}){0,7}$", 200),
    "semver": (r"^[0-9]+\.[0-9]+\.[0-9]+$", 32),
    "env_var": (r"^[A-Z][A-Z0-9_]{2,63}$", 64),
    "package": (r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", 100),
    "version": (r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$", 64),
    "python_version": (r"^3\.[0-9]{1,2}(\.[0-9]{1,3})?$", 10),
    "driver": (r"^[0-9]+(\.[0-9]+)+$", 32),
    "param_key": (r"^[a-z][a-z0-9_]{0,63}$", 64),
    "probe": (r"^[a-z][a-z0-9_]{0,31}$", 32),
    "binary_id": (r"^[a-z][a-z0-9-]{1,31}$", 32),
    "validator_id": (r"^[a-z][a-z0-9-]{1,47}$", 48),
}

# data-model 1.5: absolute-path rules of the privacy scan
ABS_PATH_RULES = [
    re.compile(r"[A-Za-z]:[\\/]"),
    re.compile(r"\\\\[A-Za-z0-9._$-]+\\"),
    re.compile(r"""(^|[\s"'=(,:])/(home|Users|root|tmp|var|mnt|media|opt|srv|private|run)/"""),
    re.compile(r"file:/"),
]


def has_absolute_path(text: str) -> bool:
    return any(rx.search(text) for rx in ABS_PATH_RULES)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------------------------------------------------
# schemas and the reference validator (python jsonschema)
# ----------------------------------------------------------------------------------------------------------------
def schema_path(stem: str) -> Path:
    return CONTRACTS / f"{stem}.schema.json"


def load_schema(stem: str) -> dict:
    p = schema_path(stem)
    if not p.is_file():
        raise FileNotFoundError(f"contracts/{stem}.schema.json does not exist (promoted by task T-001-001)")
    return json.loads(p.read_text(encoding="utf-8"))


def _registry() -> Registry:
    resources = []
    for p in sorted(CONTRACTS.glob("*.schema.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        if "$id" in s:
            resources.append((s["$id"], Resource.from_contents(s)))
    return Registry().with_resources(resources)


def validator_for(stem: str, target: str = "#", *, format_check: bool = False) -> Draft202012Validator:
    schema = load_schema(stem)
    kwargs: dict[str, Any] = {"registry": _registry()}
    if format_check:
        kwargs["format_checker"] = FormatChecker()
    if target == "#":
        return Draft202012Validator(schema, **kwargs)
    return Draft202012Validator({"$ref": schema["$id"] + target}, **kwargs)


def pointer_of(error: Any) -> str:
    parts = list(error.absolute_path)
    return "/" + "/".join(str(p) for p in parts) if parts else ""


def _flatten(error: Any, out: list) -> None:
    out.append(error)
    for sub in error.context or []:
        _flatten(sub, out)


def all_errors(stem: str, target: str, document: Any, *, format_check: bool = False) -> list[tuple[str, str, str]]:
    """Every error of the reference validator, nested ``context`` errors included: (pointer, keyword, message)."""
    errs: list = []
    for e in validator_for(stem, target, format_check=format_check).iter_errors(document):
        _flatten(e, errs)
    return sorted({(pointer_of(e), str(e.validator), e.message) for e in errs})


def error_pairs(stem: str, target: str, document: Any, **kw: Any) -> set[tuple[str, str]]:
    return {(p, k) for p, k, _ in all_errors(stem, target, document, **kw)}


def accepts(stem: str, target: str, document: Any, **kw: Any) -> bool:
    return not list(validator_for(stem, target, **kw).iter_errors(document))


# ----------------------------------------------------------------------------------------------------------------
# the conformance corpus (T-001-004)
# ----------------------------------------------------------------------------------------------------------------
def load_index() -> list[dict]:
    return json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))["fixtures"]


def fixture_file(entry: dict) -> Path:
    return FIXTURES / entry["file"]


def fixture_json(entry: dict) -> Any:
    """A fixture parsed with the standard library only (never with the loaders under test)."""
    return json.loads(fixture_file(entry).read_text(encoding="utf-8"))


def entries(
    *,
    schema: str | None = None,
    kind: str | None = None,
    valid: bool | None = None,
    tag_in: tuple[str, ...] = (),
    tag_not_in: tuple[str, ...] = (),
    rule: str | None = None,
) -> list[dict]:
    out = []
    for e in load_index():
        if schema and e["schema"] != schema:
            continue
        if kind and e["kind"] != kind:
            continue
        if valid is not None and e["valid"] != valid:
            continue
        if tag_in and not set(tag_in) & set(e["tags"]):
            continue
        if tag_not_in and set(tag_not_in) & set(e["tags"]):
            continue
        if rule and e["rule"] != rule:
            continue
        out.append(e)
    return out


def schema_level(*, schema: str | None = None) -> list[dict]:
    """Fixtures the JSON Schema alone decides: plain JSON files, no loader / post-schema / cross-file tag."""
    return [
        e
        for e in entries(schema=schema, tag_not_in=("loader", "post-schema", "cross-file"))
        if e["file"].endswith(".json")
    ]


def get(obj: Any, name: str) -> Any:
    """Attribute or mapping access (the validate() error objects may be either)."""
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


# ----------------------------------------------------------------------------------------------------------------
# repository trees for the checker
# ----------------------------------------------------------------------------------------------------------------
def clean_repo(tmp: Path) -> Path:
    """A fresh copy of the committed clean repository fixture (it must pass every checker rule)."""
    dst = tmp / "repo"
    shutil.copytree(CLEAN_REPO, dst)
    return dst


def write_file(root: Path, rel: str, content: Any) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    elif isinstance(content, str):
        p.write_text(content, encoding="utf-8", newline="\n")
    else:
        p.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return p


def edit_json(root: Path, rel: str, fn: Any) -> Any:
    p = root / rel
    doc = json.loads(p.read_text(encoding="utf-8"))
    out = fn(doc)
    doc = doc if out is None else out
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return doc


def edit_yaml(root: Path, rel: str, fn: Any) -> Any:
    p = root / rel
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    out = fn(doc)
    doc = doc if out is None else out
    p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8", newline="\n")
    return doc


def refresh_served(root: Path) -> None:
    """After editing the web index, a run manifest or the files they serve: recompute every digest and size."""
    index_p = root / "web/public/assets/manifest.json"
    index = json.loads(index_p.read_text(encoding="utf-8"))
    for a in index["artefacts"]:
        f = root / "web/public" / a["path"]
        if a["asset_host"] == "git" and f.is_file():
            data = f.read_bytes()
            a["bytes"], a["sha256"] = len(data), sha256_hex(data)
    for r in index["runs"]:
        manifest = root / "web/public/assets/runs" / r["manifest"]
        if manifest.is_file():
            r["sha256"] = sha256_hex(manifest.read_bytes())
    index_p.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


class CheckResult:
    def __init__(self, code: int, stdout: str, stderr: str, findings: list[dict] | None) -> None:
        self.code, self.stdout, self.stderr, self.findings = code, stdout, stderr, findings

    def of(self, rule: str) -> list[dict]:
        assert self.findings is not None, f"no findings parsed; exit {self.code}\n{self.stdout}\n{self.stderr}"
        return [f for f in self.findings if f["rule"] == rule]

    def at(self, rule: str, pointer_prefix: str) -> list[dict]:
        return [f for f in self.of(rule) if f["pointer"].startswith(pointer_prefix)]

    def in_file(self, file: str, pointer_prefix: str = "") -> list[dict]:
        """Findings of any rule (schema violations included) for ``file`` at or below ``pointer_prefix``."""
        assert self.findings is not None, f"no findings parsed; exit {self.code}\n{self.stdout}\n{self.stderr}"
        return [f for f in self.findings if f["file"] == file and f["pointer"].startswith(pointer_prefix)]


def run_checker(root: Path, *args: str, env: dict[str, str] | None = None, timeout: int = 300) -> CheckResult:
    assert CHECKER.is_file(), "tools/check_contracts.py does not exist (task T-001-030)"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), environment.get("PYTHONPATH", "")]))
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(env or {})
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), "--json", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        cwd=ROOT,
        timeout=timeout,
    )
    findings = None
    if proc.returncode in (0, 1):
        findings = json.loads(proc.stdout)
    return CheckResult(proc.returncode, proc.stdout, proc.stderr, findings)


def deep(doc: Any) -> Any:
    return copy.deepcopy(doc)
