"""C1 slope section: strict loading, the guards of FR-010-07 and FR-010-43, and the normalised geometry (DC-010-01).

``parse_section`` validates a ``slope-section`` document (schema, finite numbers, the cross-field rules) and returns a
``Section``; ``prepare`` builds the same object without the schema pass for the inner solvers that run thousands of
times
on a section that was validated once. A section that faces -x (``crest_x_m > toe_x_m``) is stored as its mirror image
(x -> -x, ground reversed) so that the solvers only know one orientation; ``Section.mirrored`` tells the callers to map
circles and angles back.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as _SchemaError
from jsonschema.exceptions import best_match

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"  # not imported from pitstudio.contracts: the LEM core
# must stay importable in the Python 3.12 oracle environment of the pySlope comparison (SC-010-05)

MAX_CIRCLES = 100_000  # FR-010-07: more than 10^5 trial circles is rejected
_LAYER_PARAMETERS = (
    "cohesion_kpa",
    "friction_angle_deg",
    "gsi",
    "sigma_ci_mpa",
    "m_i",
    "disturbance_d",
    "unit_weight_kn_per_m3",
)


def pointer_of(parts: list[Any]) -> str:
    """RFC 6901 JSON pointer of a path (the empty path is the empty string)."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


class InvalidSectionError(ValueError):
    """A section was rejected: ``field`` is the JSON pointer, ``valid_range`` the range or enum that was violated."""

    error_class = "section-invalid"

    def __init__(self, field_pointer: str, valid_range: str, reason: str = "") -> None:
        self.field = field_pointer
        self.valid_range = valid_range
        self.reason = reason or "value outside the valid range"
        where = field_pointer or "/"
        super().__init__(f"{where}: {self.reason} (valid range: {valid_range})"[:400])


@dataclass(frozen=True)
class Material:
    """One horizontal layer (top to bottom). ``bottom_z_m`` is ``-inf`` for the lowest layer."""

    id: str
    model: str
    unit_weight: float
    bottom_z: float
    cohesion: float = 0.0
    friction_deg: float = 0.0
    gsi: float = 0.0
    m_i: float = 0.0
    sigma_ci_mpa: float = 0.0
    disturbance: float = 0.0

    @property
    def hoek_brown(self) -> bool:
        return self.model == "hoek-brown"


@dataclass(frozen=True)
class Section:
    """A validated section in the solver frame (facing +x)."""

    document: dict[str, Any]
    mirrored: bool
    ground_x: np.ndarray
    ground_z: np.ndarray
    crest_x: float
    toe_x: float
    materials: tuple[Material, ...]
    pore_pressure_ratio: float
    mode: str
    methods: tuple[str, ...]
    slices: int
    search: dict[str, Any]
    pof: dict[str, Any] | None
    section_id: str = ""
    _ground_cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def height(self) -> float:
        return float(self.ground_at(self.crest_x) - self.ground_at(self.toe_x))

    def ground_at(self, x: Any) -> Any:
        """Ground elevation by linear interpolation, held constant beyond the first and the last vertex."""
        return np.interp(x, self.ground_x, self.ground_z)

    def material_index(self, key: str) -> int | None:
        for i, m in enumerate(self.materials):
            if m.id == key:
                return i
        return None


# ----------------------------------------------------------------------------------------------------------------------
# schema


@cache
def _validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / "slope-section.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _describe(schema: Any) -> str:
    """The valid range or enum stated by one schema node, in words."""
    if not isinstance(schema, dict):
        return "see slope-section.schema.json"
    if "enum" in schema:
        return "one of " + ", ".join(str(v) for v in schema["enum"])
    if "const" in schema:
        return f"exactly {schema['const']}"
    parts: list[str] = []
    if "minimum" in schema:
        parts.append(f">= {schema['minimum']}")
    if "exclusiveMinimum" in schema:
        parts.append(f"> {schema['exclusiveMinimum']}")
    if "maximum" in schema:
        parts.append(f"<= {schema['maximum']}")
    if "exclusiveMaximum" in schema:
        parts.append(f"< {schema['exclusiveMaximum']}")
    if parts:
        kind = "integer" if schema.get("type") == "integer" else "number"
        return f"{kind} {' and '.join(parts)}"
    if "minItems" in schema or "maxItems" in schema:
        return f"array of {schema.get('minItems', 0)} to {schema.get('maxItems', 'any number of')} items"
    if "pattern" in schema:
        return f"string matching {schema['pattern']}"
    if "type" in schema:
        return f"type {schema['type']}"
    return "see slope-section.schema.json"


def _range_of(error: _SchemaError) -> str:
    if error.validator == "required":
        wanted: list[str] = list(error.validator_value)  # type: ignore[arg-type]
        missing = [k for k in wanted if isinstance(error.instance, dict) and k not in error.instance]
        return "required fields: " + ", ".join(missing or wanted)
    if error.validator == "additionalProperties":
        return "only the properties of slope-section.schema.json"
    if error.validator == "not":
        return "a material states either Mohr-Coulomb or Hoek-Brown fields, never both"
    if error.validator == "type":
        return f"type {error.validator_value}"
    if error.validator in ("minItems", "maxItems"):
        return _describe({error.validator: error.validator_value})
    return _describe(error.schema)


def _schema_failure(document: Any) -> InvalidSectionError | None:
    errors = list(_validator().iter_errors(document))
    if not errors:
        return None
    error = best_match(errors) or errors[0]
    pointer = pointer_of(list(error.absolute_path))
    if error.validator == "additionalProperties" and isinstance(error.instance, dict):
        known = set((error.schema.get("properties") or {}).keys())
        extra = sorted(k for k in error.instance if k not in known)
        if extra:
            pointer = f"{pointer}/{extra[0]}"
    reason = error.message if len(error.message) < 120 else error.validator
    return InvalidSectionError(pointer, _range_of(error), str(reason))


def _non_finite(node: Any, path: list[Any]) -> InvalidSectionError | None:
    if isinstance(node, float) and not math.isfinite(node):
        return InvalidSectionError(pointer_of(path), "finite number", "non-finite number")
    if isinstance(node, dict):
        for key, value in node.items():
            if (found := _non_finite(value, [*path, key])) is not None:
                return found
    elif isinstance(node, list):
        for index, value in enumerate(node):
            if (found := _non_finite(value, [*path, index])) is not None:
                return found
    return None


# ----------------------------------------------------------------------------------------------------------------------
# normalisation


def _layers(document: dict[str, Any]) -> tuple[Material, ...]:
    out: list[Material] = []
    rows = document["materials"]
    for i, m in enumerate(rows):
        last = i == len(rows) - 1
        out.append(
            Material(
                id=m["id"],
                model=m["model"],
                unit_weight=float(m["unit_weight_kn_per_m3"]),
                bottom_z=-math.inf if last else float(m.get("bottom_z_m", -math.inf)),
                cohesion=float(m.get("cohesion_kpa", 0.0)),
                friction_deg=float(m.get("friction_angle_deg", 0.0)),
                gsi=float(m.get("gsi", 0.0)),
                m_i=float(m.get("m_i", 0.0)),
                sigma_ci_mpa=float(m.get("sigma_ci_mpa", 0.0)),
                disturbance=float(m.get("disturbance_d", 0.0)),
            )
        )
    return tuple(out)


def prepare(document: dict[str, Any] | Section) -> Section:
    """The solver-frame ``Section`` of a document that is already valid (no schema pass)."""
    if isinstance(document, Section):
        return document
    gx = np.asarray([p[0] for p in document["ground"]], dtype=float)
    gz = np.asarray([p[1] for p in document["ground"]], dtype=float)
    crest, toe = float(document["crest_x_m"]), float(document["toe_x_m"])
    mirrored = crest > toe
    if mirrored:
        gx, gz = -gx[::-1].copy(), gz[::-1].copy()
        crest, toe = -crest, -toe
    analysis = document["analysis"]
    return Section(
        document=document,
        mirrored=mirrored,
        ground_x=gx,
        ground_z=gz,
        crest_x=crest,
        toe_x=toe,
        materials=_layers(document),
        pore_pressure_ratio=float(document["pore_pressure_ratio"]),
        mode=analysis["mode"],
        methods=tuple(analysis["methods"]),
        slices=int(analysis["slices"]),
        search=dict(analysis["search"]),
        pof=analysis.get("pof"),
        section_id=str(document.get("section_id", "")),
    )


# ----------------------------------------------------------------------------------------------------------------------
# the guards


def _cross_field(document: dict[str, Any]) -> InvalidSectionError | None:
    ground = document["ground"]
    for i in range(1, len(ground)):
        if not ground[i][0] > ground[i - 1][0]:
            return InvalidSectionError(
                f"/ground/{i}/0", "ground x strictly increasing", "ground x is not strictly increasing"
            )
    x_first, x_last = ground[0][0], ground[-1][0]
    rng = f"within the ground x range [{x_first}, {x_last}]"
    for key in ("crest_x_m", "toe_x_m"):
        if not x_first <= document[key] <= x_last:
            return InvalidSectionError(f"/{key}", rng, f"{key} is outside the ground x range")
    gx = np.asarray([p[0] for p in ground], dtype=float)
    gz = np.asarray([p[1] for p in ground], dtype=float)
    height = float(np.interp(document["crest_x_m"], gx, gz) - np.interp(document["toe_x_m"], gx, gz))
    if not height > 0.0:
        return InvalidSectionError(
            "/crest_x_m", "slope height z(crest) - z(toe) > 0", f"slope height {height:g} m is not positive"
        )
    search = document["analysis"]["search"]
    if not search["rho_min"] < search["rho_max"]:
        return InvalidSectionError("/analysis/search/rho_min", "rho_min < rho_max", "rho_min is not below rho_max")
    total = search["entry_points"] * search["exit_points"] * search["radius_ratios"]
    if total > MAX_CIRCLES:
        return InvalidSectionError(
            "/analysis/search",
            f"entry x exit x radius ratios <= {MAX_CIRCLES} trial circles",
            f"{total} trial circles exceed the limit",
        )
    ids: dict[str, int] = {}
    for i, m in enumerate(document["materials"]):
        if m["id"] in ids:
            return InvalidSectionError(
                f"/materials/{i}/id", "unique material ids", f"id {m['id']!r} repeats /materials/{ids[m['id']]}/id"
            )
        ids[m["id"]] = i
    bottoms = [m.get("bottom_z_m") for m in document["materials"][:-1]]
    for i, b in enumerate(bottoms):
        if b is None or (i > 0 and not b < bottoms[i - 1]):
            return InvalidSectionError(
                f"/materials/{i}/bottom_z_m",
                "bottom_z_m on every layer but the lowest, strictly decreasing",
                "layer bottom missing or not below the layer above",
            )
    pof = document["analysis"].get("pof")
    if pof is not None:
        for i, d in enumerate(pof["distributions"]):
            material = d.get("material_id")
            if material is not None and material not in ids:
                return InvalidSectionError(
                    f"/analysis/pof/distributions/{i}/material_id",
                    "a material id defined in /materials",
                    f"material {material!r} is not defined",
                )
    return None


def parse_section(document: Any) -> Section:
    """Validate a DC-010-01 document (FR-010-07, FR-010-43) and return the solver-frame section.

    Raises ``InvalidSectionError`` naming the first violated field and its valid range; nothing is returned for a
    rejected document."""
    if not isinstance(document, dict):
        raise InvalidSectionError("", "a JSON object (slope-section.schema.json)", "the section is not an object")
    if (found := _non_finite(document, [])) is not None:
        raise found
    if (failure := _schema_failure(document)) is not None:
        raise failure
    if (failure := _cross_field(document)) is not None:
        raise failure
    return prepare(document)


def load_section(path: str | Path) -> Section:
    """Read a section file through the strict contract loader, then ``parse_section`` it."""
    from pitstudio.contracts.io import load_json

    return parse_section(load_json(Path(path)))  # a malformed file raises the loader's ContractError (a ValueError)
