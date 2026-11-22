"""Licence and honesty guards of the reason lane (FR-015-06, FR-015-39, FR-015-42).

- No model weight or conversion (`.gguf`, `.safetensors`, `.pt`, `.pth`, `.bin`, a Hugging Face cache folder) is
  tracked in git, listed for release upload or copied into the Pages artefact; an artefact of licence class
  `reference-only` never appears in a publish list.
- A stage `s05_*` to `s30_*` never takes an artefact produced by the Cosmos tool (the `st59*` stages) as input.
- No metric produced by the Cosmos tool is a headline KPI.
"""

from __future__ import annotations

import json
import posixpath
import re
import subprocess
import tarfile
import zipfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from pitstudio.contracts.validate import CONTRACTS_DIR

WEIGHT_EXTENSIONS = frozenset({".gguf", ".safetensors", ".pt", ".pth", ".bin"})
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
_HF_MODEL_FOLDER = re.compile(r"models--.+--.+")


@dataclass(frozen=True)
class Violation:
    """One offence: the offending path (or `archive!member`, or `<run>:<stage>`) and the rule it breaks."""

    path: str
    rule: str


def _path_violations(path: str) -> list[Violation]:
    parts = path.split("/")
    found = []
    if posixpath.splitext(parts[-1])[1].lower() in WEIGHT_EXTENSIONS:
        found.append(Violation(path, "weight-extension"))
    cache = any(_HF_MODEL_FOLDER.fullmatch(p) for p in parts) or any(
        a == ".cache" and b == "huggingface" for a, b in pairwise(parts)
    )
    if cache:
        found.append(Violation(path, "hf-cache-folder"))
    return found


def scan_tracked_files(paths: Iterable[str]) -> list[Violation]:
    """Violations among repository-relative POSIX paths."""
    return [v for p in paths for v in _path_violations(p)]


def scan_publish_list(entries: Iterable[Any]) -> list[Violation]:
    """Violations in a release-asset upload list: paths or `{"path", "licence_class"}` entries."""
    found: list[Violation] = []
    for entry in entries:
        if isinstance(entry, str):
            path, cls = entry, None
        elif isinstance(entry, Mapping) and isinstance(entry.get("path"), str):
            path, cls = entry["path"], entry.get("licence_class")
        else:
            raise ValueError(f"malformed publish-list entry: {entry!r}")
        found.extend(_path_violations(path))
        if cls == "reference-only":
            found.append(Violation(path, "reference-only"))
    return found


def _archive_members(path: Path) -> list[str]:
    name = path.name.lower()
    try:
        if name.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                return z.namelist()
        with tarfile.open(path) as t:
            return t.getnames()
    except zipfile.BadZipFile, tarfile.TarError, EOFError, OSError:
        return []


def scan_directory(root: Path) -> list[Violation]:
    """The same rules over every file below `root` (the Pages artefact) and over the members of its archives."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")
    found: list[Violation] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        found.extend(_path_violations(rel))
        if path.name.lower().endswith(ARCHIVE_SUFFIXES):
            found.extend(
                Violation(f"{rel}!{member}", "archive-member")
                for member in _archive_members(path)
                if _path_violations(member)
            )
    return found


def _git_ls_files(repo_root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"], capture_output=True, check=True, timeout=120
    ).stdout
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def check_repository(repo_root: Path, *, ls_files: Callable[[Path], Sequence[str]] | None = None) -> list[Violation]:
    """`scan_tracked_files` over the tracked files of the repository (`git ls-files`, or the injected listing)."""
    return scan_tracked_files((ls_files or _git_ls_files)(Path(repo_root)))


# ------------------------------------------------------------------------------------ display-only (FR-015-39)
COSMOS_STAGE_PREFIX = "st59"
_CHECKED_STAGE = re.compile(r"s(\d{2})_.+")
CHECKED_RANGE = (5, 30)


def _stages(manifest: Any) -> list[Mapping[str, Any]]:
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("stages"), list):
        raise ValueError("a run manifest needs a `stages` list")
    stages = manifest["stages"]
    for stage in stages:
        key = stage.get("key") if isinstance(stage, Mapping) else None
        if not isinstance(key, Mapping) or not isinstance(key.get("id"), str):
            raise ValueError("every stage needs `key.id`")
    return stages


def check_display_only(manifests: Sequence[Mapping[str, Any]]) -> list[Violation]:
    """One violation per input of a stage `s05_*` to `s30_*` that is an output of a Cosmos (`st59*`) stage, matched by
    SHA-256 or by name. The producing stage and its consumer may sit in different manifests."""
    parsed = [(m, _stages(m)) for m in manifests]
    shas: set[str] = set()
    names: set[str] = set()
    for _, stages in parsed:
        for stage in stages:
            if stage["key"]["id"].startswith(COSMOS_STAGE_PREFIX):
                for out in stage.get("outputs") or []:
                    shas.update(x for x in (out.get("sha256"),) if x)
                    names.update(x for x in (out.get("name"),) if x)
    found = []
    for manifest, stages in parsed:
        for stage in stages:
            sid = stage["key"]["id"]
            match = _CHECKED_STAGE.fullmatch(sid)
            if not match or not CHECKED_RANGE[0] <= int(match.group(1)) <= CHECKED_RANGE[1]:
                continue
            found.extend(
                Violation(f"{manifest.get('run_id', '')}:{sid}", "cosmos-output-as-input")
                for inp in stage.get("inputs") or []
                if inp.get("sha256") in shas or inp.get("id") in names
            )
    return found


# ------------------------------------------------------------------------------- not a headline KPI (FR-015-42)
_METRIC_OBJECTS = ("row_a", "row_b", "row_c", "gate", "bench_path")
_NOT_A_METRIC = frozenset(
    {
        "arm",
        "reasoning",
        "type",
        "status",
        "reason",
        "n",
        "input_mode",
        "n_pairs",
        "verdict",
        "path",
        "context_tokens",
        "gpu",
        "n_captions",
        "threshold",
        "q8_0_path",
    }
)
_MEASURED = frozenset(
    {
        "balanced_accuracy",
        "f1",
        "auroc",
        "unparseable_rate",
        "error_rate",
        "accuracy",
        "position_bias",
        "single_clip_auroc",
        "detection_rate",
        "chair_i",
        "chair_s",
        "recall",
        "no_object_rate",
        "condition_ba",
        "agreement",
        "vram_peak_bytes",
        "prefill_tokens_per_s",
        "decode_tokens_per_s",
        "wall_s_per_query",
    }
)
COSMOS_KPI_PREFIXES = ("cosmos_", "vlm_")


def cosmos_metric_ids() -> frozenset[str]:
    """The ids of the metrics the Cosmos tool produces: the measured properties of the rows, gate and bench objects of
    `contracts/vlm-metrics.schema.json` (plus the quantities of FR-015-13, FR-015-14 and FR-015-30)."""
    schema = json.loads((CONTRACTS_DIR / "vlm-metrics.schema.json").read_text(encoding="utf-8"))
    names: set[str] = set()
    for obj in _METRIC_OBJECTS:
        names.update(schema["$defs"][obj]["properties"])
    return frozenset(names - _NOT_A_METRIC) | _MEASURED


def check_not_headline(registry: Any) -> list[Violation]:
    """One violation per headline KPI of the case registry whose id is a Cosmos metric or begins `cosmos_` / `vlm_`."""
    if not isinstance(registry, Mapping) or not isinstance(registry.get("cases"), Mapping):
        raise ValueError("the KPI registry needs a `cases` mapping")
    ids = cosmos_metric_ids()
    found = []
    for case, body in registry["cases"].items():
        kpis = body.get("kpis", []) if isinstance(body, Mapping) else None
        if not isinstance(kpis, list):
            raise ValueError(f"case {case}: `kpis` must be a list")
        for kpi in kpis:
            if not isinstance(kpi, Mapping) or not isinstance(kpi.get("id"), str):
                raise ValueError(f"case {case}: every KPI needs an `id`")
            kid = kpi["id"]
            if kpi.get("headline") is True and (kid in ids or kid.startswith(COSMOS_KPI_PREFIXES)):
                found.append(Violation(f"{case}:{kid}", "cosmos-metric-is-headline"))
    return found


def check_registry_file(path: Path) -> list[Violation]:
    """Load the YAML case registry and apply `check_not_headline`."""
    return check_not_headline(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
