"""Parity fixtures of the browser engines (DC-018-04, FR-018-67): write, pin and check.

Usage:
  python tools/make_parity_fixtures.py check --root DIR [--engines a,b]
  python tools/make_parity_fixtures.py generate --root DIR [--engines a,b]   (needs the reference: minephys)

Fixtures live in `<root>/<engine-id>/<fixture>.json[.gz]` (default root `web/tests/fixtures/parity`);
`<root>/SHA256SUMS` pins the stored bytes (sha256sum format). `check` exits 0 when clean, 1 with one
`<path>: <rule>: <message>` line per defect on stderr, 2 for a usage error. A fixture that fails its schema or its pin,
or an engine with no fixture, fails the suite: no engine passes on an empty or invalid set.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _registry as reg

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "web" / "tests" / "fixtures" / "parity"
SCHEMA_VERSION = "1.0"
ENGINE_VERSION = "1.0.0"
PINS = "SHA256SUMS"
BOM = b"\xef\xbb\xbf"


class Problem:
    """One defect; a plain class because the module is loaded by path (no entry in sys.modules)."""

    def __init__(self, path: str, rule: str, message: str) -> None:
        self.path, self.rule, self.message = path, rule, message

    def __repr__(self) -> str:
        return f"Problem({self.path!r}, {self.rule!r}, {self.message!r})"

    def __str__(self) -> str:
        return f"{self.path}: {self.rule}: {self.message}"


def engine_ids() -> list[str]:
    schema = reg.schema_of(ROOT, "cases.schema.json")
    return list(schema["$defs"]["engine_id"]["enum"])


def build_fixture(
    engine: str, function: str, fixture: str, reference: dict[str, Any], tolerance: dict[str, Any], cases: list[dict]
) -> dict[str, Any]:
    """The DC-018-04 document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "engine": engine,
        "fixture": fixture,
        "function": function,
        "reference": reference,
        "tolerance": tolerance,
        "cases": cases,
    }


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_pins(root: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    f = root / PINS
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, _, name = line.partition("  ")
                pins[name.strip()] = digest.strip()
    return pins


def _write_pins(root: Path, pins: dict[str, str]) -> None:
    text = "".join(f"{d}  {n}\n" for n, d in sorted(pins.items()))
    (root / PINS).write_text(text, encoding="utf-8", newline="\n")


def write_fixture(root: Path, doc: dict[str, Any], *, gzip: bool = False) -> Path:
    """Deterministic bytes (UTF-8, LF, gzip with mtime 0) and the SHA256SUMS pin of the stored bytes."""
    root = Path(root)
    text = json.dumps(doc, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    data = text.encode("utf-8")
    name = f"{doc['fixture']}.json"
    if gzip:
        import gzip as gz_mod

        buf = io.BytesIO()
        with gz_mod.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as handle:
            handle.write(data)
        data = buf.getvalue()
        name += ".gz"
    path = root / doc["engine"] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    pins = _read_pins(root)
    pins[f"{doc['engine']}/{name}"] = _sha(data)
    _write_pins(root, pins)
    return path


class _Dup(Exception):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise _Dup(f"duplicate key {k!r}")
        out[k] = v
    return out


def _no_constant(token: str) -> Any:
    raise ValueError(f"non-finite number {token}")


def _load(path: Path) -> Any:
    """FR-001-05 loader rules: UTF-8 without BOM, valid gzip, one JSON value, no duplicate key, no NaN or Infinity."""
    raw = path.read_bytes()
    if path.suffix == ".gz":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as exc:
            raise ValueError(f"malformed gzip ({exc})") from exc
    if raw.startswith(BOM):
        raise ValueError("byte order mark")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8") from exc
    if not text.strip():
        raise ValueError("empty file")
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
    except _Dup as exc:
        raise ValueError(str(exc)) from exc
    except ValueError as exc:
        raise ValueError(f"not valid JSON ({exc})") from exc


def _engine_validator(engine: str, kind: str) -> Draft202012Validator:
    schema = reg.schema_of(ROOT, f"engines/{engine}.schema.json")
    sub = {"$ref": f"#/$defs/{kind}", "$defs": schema["$defs"]}
    return Draft202012Validator(sub, registry=reg._contract_registry(ROOT))


GRID_DIMS = {"rows": "ny", "cols": "nx"}  # a non-constant dimension of a result buffer is named by an input field


def _buffer_descriptors(schema: Any, payload: Any, inputs: dict[str, Any] | None = None) -> Any:
    """A typed buffer travels as a descriptor in a message (dtype, shape, byte_length); a fixture holds its numbers
    as a flat list, so the check swaps each such list for the descriptor the schema asks for."""
    if not isinstance(schema, dict) or not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for key, prop in (schema.get("properties") or {}).items():
        if not (isinstance(prop, dict) and "byte_length" in (prop.get("required") or [])):
            continue
        values = out.get(key)
        if not isinstance(values, list):
            continue
        shape_schema = (prop.get("properties") or {}).get("shape", {})
        dims = shape_schema.get("required") or []
        props = shape_schema.get("properties") or {}
        fixed = 1
        shape: dict[str, int] = {}
        for d in dims:
            spec = props.get(d, {})
            if "const" in spec:
                shape[d] = int(spec["const"])
                fixed *= shape[d]
            elif inputs and GRID_DIMS.get(d) in inputs:
                shape[d] = int(inputs[GRID_DIMS[d]])
                fixed *= shape[d]
        for d in dims:
            if d not in shape:
                shape[d] = len(values) // max(fixed, 1)
        out[key] = {"dtype": "float64", "shape": shape, "byte_length": 8 * len(values)}
    return out


def _engine_problems(rel: str, engine: str, doc: dict[str, Any]) -> list[Problem]:
    out: list[Problem] = []
    function = doc.get("function")
    if function is None:
        return out
    try:
        vin = _engine_validator(engine, "input")
        vout = _engine_validator(engine, "output")
    except reg.RegistryError as exc:
        return [Problem(rel, "engine-schema", str(exc))]
    envelope = {"engine": engine, "engine_version": ENGINE_VERSION, "function": function}
    defs = reg.schema_of(ROOT, f"engines/{engine}.schema.json")["$defs"]
    for i, case in enumerate(doc.get("cases", [])):
        for kind, validator, key in (("input", vin, "args"), ("output", vout, "result")):
            payload = _buffer_descriptors(defs.get(f"{function}_{key}"), case.get(kind), case.get("input"))
            msg = {"kind": kind, **envelope, key: payload}
            errs = sorted(validator.iter_errors(msg), key=lambda e: [str(p) for p in e.absolute_path])
            if errs:
                e = max(errs, key=lambda x: len(x.absolute_path))  # the deepest violation names the real cause
                where = reg.pointer(list(e.absolute_path))
                out.append(Problem(rel, "engine-schema", f"vector {i} {kind}: {where}: {e.message[:140]}"))
        if len(out) >= 10:
            break
    return out


def check_fixtures(root: Path, engines: list[str] | None = None) -> list[Problem]:
    root = Path(root)
    problems: list[Problem] = []
    known = set(engine_ids())
    pins = _read_pins(root)
    present: dict[str, list[Path]] = {}
    if root.is_dir():
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            present[folder.name] = sorted(
                f for f in folder.iterdir() if f.is_file() and (f.name.endswith(".json") or f.name.endswith(".json.gz"))
            )
    for name in sorted(present):
        if name not in known:
            problems.append(Problem(name, "unknown-engine", f"{name} is not an engine id of spec 018 section 7.1"))  # noqa: PERF401
    stored: set[str] = set()
    schema_validator = reg.validator(ROOT, "parity-fixture.schema.json")
    for name in sorted(present):
        for f in present[name]:
            rel = f"{name}/{f.name}"
            stored.add(rel)
            data = f.read_bytes()
            if rel not in pins:
                problems.append(Problem(rel, "unpinned", "no line in SHA256SUMS"))
            elif pins[rel] != _sha(data):
                problems.append(Problem(rel, "sha256-mismatch", "the bytes differ from the pin in SHA256SUMS"))
            if name not in known:
                continue
            try:
                doc = _load(f)
            except ValueError as exc:
                problems.append(Problem(rel, "loader", str(exc)))
                continue
            errs = sorted(schema_validator.iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path])
            for e in errs[:5]:
                problems.append(Problem(rel, "schema", f"{reg.pointer(list(e.absolute_path))}: {e.message[:160]}"))  # noqa: PERF401
            if not isinstance(doc, dict):
                continue
            stem = f.name.removesuffix(".gz").removesuffix(".json")
            if doc.get("fixture") != stem or doc.get("engine") != name:
                problems.append(
                    Problem(rel, "name-mismatch", f"fixture {doc.get('fixture')!r} / engine {doc.get('engine')!r}")
                )
            if errs or doc.get("engine") != name:
                continue
            problems.extend(_engine_problems(rel, name, doc))
    for rel in sorted(set(pins) - stored):
        if not (root / rel).exists():
            problems.append(Problem(rel, "missing-file", "pinned in SHA256SUMS but not on disk"))  # noqa: PERF401
    for engine in engines if engines is not None else sorted(present):
        if not present.get(engine):
            problems.append(Problem(engine, "empty-fixture-set", f"engine {engine} has no fixture file"))  # noqa: PERF401
    return problems


def _cmd_check(args: argparse.Namespace) -> int:
    engines = [e for e in args.engines.split(",") if e] if args.engines else None
    problems = check_fixtures(Path(args.root), engines)
    for p in problems:
        print(p, file=sys.stderr)
    if not problems:
        print(f"parity fixtures ok ({args.root})")
    return 1 if problems else 0


def _cmd_generate(args: argparse.Namespace) -> int:
    import parity_references  # tools/parity_references.py: the reference runs of section 7.1 (pipeline environment)

    return int(parity_references.generate(Path(args.root), [e for e in args.engines.split(",") if e] or None))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_parity_fixtures.py", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    for name, fn in (("check", _cmd_check), ("generate", _cmd_generate)):
        p = sub.add_parser(name)
        p.add_argument("--root", default=str(DEFAULT_ROOT))
        p.add_argument("--engines", default="")
        p.set_defaults(fn=fn)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    if not getattr(args, "fn", None):
        parser.print_usage(sys.stderr)
        return 2
    try:
        return int(args.fn(args))
    except reg.RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
