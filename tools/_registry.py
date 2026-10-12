"""Shared helpers of the registry checkers (`check_cases`, `check_results`, `check_figures`, `build_knowledge`).

Strict YAML loading (duplicate mapping keys are an error, FR-001-06), JSON Schema 2020-12 validation against the
promoted schemas of `<root>/contracts/`, and one-line findings that name the offending id or JSON pointer. Not a CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]


class RegistryError(Exception):
    """A document that cannot be read (missing file, I/O error); the checkers exit 2."""


class ContentError(RegistryError):
    """A document that was read but is not well-formed (syntax, duplicate key, non-finite number); exit 1."""


class _StrictLoader(yaml.SafeLoader):
    """PyYAML safe loader that rejects duplicate mapping keys."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise ContentError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_yaml(path: Path) -> Any:
    """Read one YAML file strictly; a missing file, a syntax error or a duplicate key raises `RegistryError`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryError(f"{path.name}: cannot read ({exc.strerror or exc})") from exc
    try:
        return yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise ContentError(f"{path.name}: {str(exc).splitlines()[0]}") from exc
    except ContentError as exc:
        raise ContentError(f"{path.name}: {exc}") from exc


def _no_constant(token: str) -> Any:
    raise ValueError(f"non-finite number {token}")


def load_json(path: Path) -> Any:
    """Read one JSON file; NaN, Infinity and -Infinity are refused (they are not JSON)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=_no_constant)
    except OSError as exc:
        raise RegistryError(f"{path.name}: cannot read ({exc.strerror or exc})") from exc
    except ValueError as exc:
        raise ContentError(f"{path.name}: not valid JSON ({exc})") from exc


def contracts_dir(root: Path) -> Path:
    """`<root>/contracts` when the checked tree carries its own schemas, else the contracts of this repository."""
    return root / "contracts" if (root / "contracts").is_dir() else ROOT / "contracts"


def _contract_registry(root: Path) -> Registry:
    resources = []
    for f in sorted(contracts_dir(root).rglob("*.schema.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        resources.append((doc.get("$id", f.as_uri()), Resource.from_contents(doc, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def schema_of(root: Path, schema_name: str) -> dict[str, Any]:
    path = contracts_dir(root) / schema_name
    if not path.is_file():
        raise RegistryError(f"contracts/{schema_name} is missing")
    return json.loads(path.read_text(encoding="utf-8"))


def validator(root: Path, schema_name: str) -> Draft202012Validator:
    """Validator of `<root>/contracts/<schema_name>`; cross-file references resolve inside `<root>/contracts/`."""
    return Draft202012Validator(schema_of(root, schema_name), registry=_contract_registry(root))


def pointer(parts: list[Any]) -> str:
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def schema_findings(root: Path, schema_name: str, doc: Any, label: str) -> list[str]:
    """One line per schema violation: `label: <JSON pointer>: <message>`."""
    errors = validator(root, schema_name).iter_errors(doc)
    return [
        f"{label}: {pointer(list(e.absolute_path))}: {e.message[:200]}"
        for e in sorted(errors, key=lambda e: [str(p) for p in e.absolute_path])
    ]


def report(findings: list[str], ok_message: str) -> int:
    """Print the findings (exit 1) or the success line (exit 0)."""
    if findings:
        print(f"{len(findings)} finding(s):")
        for line in findings:
            print(f"  [x] {line}")
        return 1
    print(ok_message)
    return 0


def usage_error(message: str) -> int:
    print(message, file=sys.stderr)
    return 2
