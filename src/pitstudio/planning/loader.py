"""Strict loaders for block models and MineLib instances (FR-017-27): a rejected file produces no model."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.planning.bev import to_cents

DESTINATIONS = ("mill", "waste", "leach", "stockpile")
BOUNDS = {"python": 2**62, "web": 2**53}
_DRIVE = re.compile(r"^[A-Za-z]:")


class BlockModelError(ValueError):
    """A hostile block model or MineLib file; `.reason` names the cause."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class LoadedModel:
    ids: list[int]
    values_cents: np.ndarray
    arcs: np.ndarray
    tonnage: np.ndarray


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BlockModelError(f"{what} is not a number: {value!r}")
    if not math.isfinite(value):
        raise BlockModelError(f"{what} is not finite")
    return float(value)


def _cents(values: list[float], engine: str) -> np.ndarray:
    try:
        cents = to_cents(np.asarray(values, dtype=np.float64))
    except ValueError as exc:
        raise BlockModelError(f"sum of absolute values: {exc}") from exc
    if sum(abs(int(c)) for c in cents) >= BOUNDS[engine]:
        raise BlockModelError(
            f"sum of absolute values in cents reaches the {engine} bound 2^{BOUNDS[engine].bit_length() - 1}"
        )
    return cents


def load_block_model(doc: Mapping[str, Any], *, engine: str = "python") -> LoadedModel:
    """DC-017-02 document to integer-cent values, index-pair arcs and tonnage."""
    if engine not in BOUNDS:
        raise ValueError(f"engine must be one of {', '.join(BOUNDS)}")
    blocks = doc.get("blocks") if isinstance(doc, Mapping) else None
    if not isinstance(blocks, list) or not blocks or not all(isinstance(b, Mapping) for b in blocks):
        raise BlockModelError("blocks must be a non-empty list of block objects")
    ids: list[int] = []
    for b in blocks:
        if isinstance(b.get("id"), bool) or not isinstance(b.get("id"), int):
            raise BlockModelError("every block needs an integer id (blocks malformed)")
        ids.append(b["id"])
    if len(set(ids)) != len(ids):
        raise BlockModelError("duplicate block id")
    index = {block_id: i for i, block_id in enumerate(ids)}
    values: list[float] = []
    tonnage: list[float] = []
    arcs: list[tuple[int, int]] = []
    for b in blocks:
        if "tonnage_t" not in b or "values_usd" not in b:
            raise BlockModelError(f"block {b['id']} lacks tonnage_t or values_usd (blocks malformed)")
        t = _number(b["tonnage_t"], f"tonnage of block {b['id']}")
        if t < 0:
            raise BlockModelError(f"negative tonnage in block {b['id']}")
        tonnage.append(t)
        if "grade" in b and b["grade"] is not None:
            g = _number(b["grade"], f"grade of block {b['id']}")
            if not 0.0 <= g <= 1.0:
                raise BlockModelError(f"grade {g} of block {b['id']} is outside [0, 1]")
        per_destination = b["values_usd"]
        if not isinstance(per_destination, Mapping) or not per_destination:
            raise BlockModelError(f"block {b['id']} has no destination values (blocks malformed)")
        for destination in per_destination:
            if destination not in DESTINATIONS:
                raise BlockModelError(f"unknown destination {destination!r} in block {b['id']}")
        values.append(max(_number(v, f"value of block {b['id']}") for v in per_destination.values()))
        for required in b.get("prec", []) or []:
            if isinstance(required, bool) or required not in index:
                raise BlockModelError(f"precedence of block {b['id']} names an unknown block {required!r}")
            arcs.append((index[b["id"]], index[required]))
    return LoadedModel(
        ids,
        _cents(values, engine),
        np.asarray(arcs, dtype=np.int64).reshape(-1, 2),
        np.asarray(tonnage, dtype=np.float64),
    )


def _checked_path(root: Path, name: str) -> Path:
    if (
        not isinstance(name, str)
        or not name
        or name.startswith(("/", "\\"))
        or "\\" in name
        or _DRIVE.match(name)
        or ".." in name.split("/")
    ):
        raise BlockModelError(f"file path {name!r} is absolute, has a drive, a backslash or `..`")
    return Path(root) / name


def _float_token(token: str, where: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise BlockModelError(f"parse error in {where}: {token!r}") from exc
    if not math.isfinite(value):
        raise BlockModelError(f"{where}: value {token!r} is not finite")
    return value


def _int_token(token: str, where: str) -> int:
    try:
        return int(token)
    except ValueError as exc:
        raise BlockModelError(f"parse error in {where}: {token!r}") from exc


def load_minelib(root: Path, blocks: str, prec: str, upit: str) -> LoadedModel:
    """A MineLib UPIT instance (`.blocks`, `.prec`, `.upit`) read from `root`."""
    paths = [_checked_path(root, n) for n in (blocks, prec, upit)]
    try:
        texts = [p.read_text(encoding="ascii") for p in paths]
    except (OSError, UnicodeDecodeError) as exc:
        raise BlockModelError(f"parse error: cannot read the instance files ({type(exc).__name__})") from exc
    ids: list[int] = []
    tonnage: list[float] = []
    for line in filter(None, (ln.strip() for ln in texts[0].splitlines())):
        parts = line.split()
        if len(parts) < 4:
            raise BlockModelError(f"parse error in .blocks: {line!r}")
        ids.append(_int_token(parts[0], ".blocks"))
        for token in parts[1:4]:
            _float_token(token, ".blocks")
        tonnage.append(_float_token(parts[5], ".blocks") if len(parts) > 5 else float("nan"))
    if len(set(ids)) != len(ids):
        raise BlockModelError("duplicate block id in the .blocks file")
    index = {block_id: i for i, block_id in enumerate(ids)}
    arcs: list[tuple[int, int]] = []
    for line in filter(None, (ln.strip() for ln in texts[1].splitlines())):
        parts = line.split()
        if len(parts) < 2:
            raise BlockModelError(f"parse error in .prec: {line!r}")
        block, count = _int_token(parts[0], ".prec"), _int_token(parts[1], ".prec")
        if block not in index:
            raise BlockModelError(f"unknown block {block} in the .prec file")
        if len(parts) != 2 + count:
            raise BlockModelError(
                f"parse error in .prec: row of block {block} lists {len(parts) - 2} of {count} predecessors"
            )
        for token in parts[2:]:
            required = _int_token(token, ".prec")
            if required not in index:
                raise BlockModelError(f"unknown block {required} in the .prec file")
            arcs.append((index[block], index[required]))
    expected = None
    values = [0.0] * len(ids)
    in_objective = False
    for line in filter(None, (ln.strip() for ln in texts[2].splitlines())):
        if not in_objective:
            if line.upper().startswith("OBJECTIVE_FUNCTION"):
                in_objective = True
            elif line.upper().startswith("NBLOCKS"):
                expected = _int_token(line.split(":", 1)[1].strip(), ".upit NBLOCKS")
            continue
        parts = line.split()
        if len(parts) != 2:
            raise BlockModelError(f"parse error in .upit: {line!r}")
        block = _int_token(parts[0], ".upit")
        if block not in index:
            raise BlockModelError(f"unknown block {block} in the .upit file")
        values[index[block]] = _float_token(parts[1], ".upit")
    if expected is not None and expected != len(ids):
        raise BlockModelError(f"the .blocks file has {len(ids)} rows but NBLOCKS is {expected} (blocks count)")
    return LoadedModel(
        ids, _cents(values, "python"), np.asarray(arcs, dtype=np.int64).reshape(-1, 2), np.asarray(tonnage)
    )
