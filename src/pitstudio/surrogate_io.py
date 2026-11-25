"""Surrogate input/output description loader (DC-011-02; FR-011-46, FR-011-47).

`load_surrogate_io(source)` returns the validated document of a dict or a JSON file. Everything it rejects raises
`SurrogateIoError` with `error_class == "surrogate-io-invalid"` and a message that names the offending field
(`outputs[0].quantiles`, `inputs[1].name`, ...). Beyond the JSON Schema it enforces what a schema cannot express:
quantile
levels strictly increasing inside (0, 1), tensor names unique over inputs and outputs together, channel names unique
inside
a tensor.
"""

from __future__ import annotations

import copy
import json
import math
import os
from collections import Counter
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ERROR_CLASS = "surrogate-io-invalid"
_SCHEMA = "surrogate-io.schema.json"


class SurrogateIoError(ValueError):
    """A surrogate I/O document is invalid; `error_class` is always "surrogate-io-invalid"."""

    error_class = ERROR_CLASS


@cache
def load_contract_schema(name: str) -> dict[str, Any]:
    """The JSON Schema `<name>.schema.json`: the promoted `contracts/` copy first, then the spec 011 draft.

    Found by walking up from this module (a checkout); `PITSTUDIO_CONTRACTS` names a directory that overrides the
    search.
    """
    file = f"{name}.schema.json"
    override = os.environ.get("PITSTUDIO_CONTRACTS")
    if override:
        candidates = [Path(override) / file]
    else:
        relative = (Path("contracts") / file, Path("specs") / "011-surrogates" / "contracts" / file)
        candidates = [parent / rel for parent in Path(__file__).resolve().parents for rel in relative]
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"schema {file} not found (set PITSTUDIO_CONTRACTS)")


def _where(path: Any) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "<document>"


def _read(source: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(source, dict):
        return copy.deepcopy(source)
    try:
        text = Path(source).read_text(encoding="utf-8")
        doc = json.loads(text)
    except (OSError, UnicodeDecodeError) as exc:
        raise SurrogateIoError(f"<file>: cannot read {source}: {exc}") from None
    except ValueError as exc:
        raise SurrogateIoError(f"<file>: not valid JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise SurrogateIoError("<document>: must be a JSON object")
    return doc


def load_surrogate_io(source: dict[str, Any] | str | Path) -> dict[str, Any]:
    """Validate a DC-011-02 document (a dict, or a path to its JSON file) and return it; the argument is not
    modified."""
    doc = _read(source)
    errors = sorted(
        Draft202012Validator(load_contract_schema("surrogate-io")).iter_errors(doc),
        key=lambda e: [str(p) for p in e.path],
    )
    if errors:
        first = errors[0]
        raise SurrogateIoError(f"{_where(first.path)}: {first.message}")
    _check_quantiles(doc)
    _check_names(doc)
    return doc


def _check_quantiles(doc: dict[str, Any]) -> None:
    for group in ("inputs", "outputs"):
        for i, tensor in enumerate(doc[group]):
            levels = tensor.get("quantiles")
            if levels is None:
                continue
            where = f"{group}[{i}].quantiles"
            if not all(isinstance(v, int | float) and math.isfinite(v) and 0.0 < v < 1.0 for v in levels):
                raise SurrogateIoError(f"{where}: every level must be a finite number inside (0, 1)")
            if any(b <= a for a, b in pairwise(levels)):
                raise SurrogateIoError(f"{where}: the levels must increase strictly, got {levels}")


def _check_names(doc: dict[str, Any]) -> None:
    names = Counter(t["name"] for group in ("inputs", "outputs") for t in doc[group])
    for name, count in names.items():
        if count > 1:
            raise SurrogateIoError(
                f"tensor name {name!r} is used {count} times; names must be unique over inputs and outputs"
            )
    for group in ("inputs", "outputs"):
        for i, tensor in enumerate(doc[group]):
            channels = Counter(c["name"] for c in tensor.get("channels", []))
            for name, count in channels.items():
                if count > 1:
                    raise SurrogateIoError(
                        f"{group}[{i}].channels: channel name {name!r} is repeated; names must be unique"
                    )
