"""Generate the Pydantic models of every contract schema, and check that the committed ones are not stale.

Usage:  python tools/gen_types.py [--check] [--contracts DIR] [--out DIR]
        (defaults: ``contracts`` and ``src/pitstudio/contracts/_generated`` of this repository)
One module ``<stem>.py`` per ``<stem>.schema.json`` (``-`` becomes ``_``) plus ``__init__.py``, produced with
datamodel-code-generator and the pinned options of data-model 7.1, then formatted with ``ruff format``. Everything is
generated into a temporary folder first: a failed run changes no file.
Exit:   0 ok (or no drift), 1 drift (``--check``), 2 usage error, 3 a schema cannot be generated.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from jsonschema import Draft202012Validator  # noqa: E402
from jsonschema.exceptions import SchemaError  # noqa: E402

from pitstudio.contracts import ContractError, load_json  # noqa: E402

DEFAULT_CONTRACTS = REPO / "contracts"
DEFAULT_OUT = REPO / "src/pitstudio/contracts/_generated"
HEADER = "# Generated from contracts/{file} by tools/gen_types.py. Do not edit."
OPTIONS = [
    "--input-file-type", "jsonschema",
    "--schema-version", "2020-12",
    "--output-model-type", "pydantic_v2.BaseModel",
    "--target-python-version", "3.12",
    "--use-annotated",
    "--use-standard-collections",
    "--use-union-operator",
    "--field-constraints",
    "--extra-fields", "forbid",
    "--enum-field-as-literal", "all",
    "--use-schema-description",
    "--disable-timestamp",
    "--formatters", "builtin",
]  # fmt: skip
WORKERS = max(1, min(12, os.cpu_count() or 1))
UNSUPPORTED_KEYS = ("prefixItems", "$dynamicRef", "$dynamicAnchor", "$recursiveRef")


class GenerationError(Exception):
    """A schema is invalid or uses a construct the generators do not support."""


def stem_of(schema_file: Path) -> str:
    return schema_file.name.removesuffix(".schema.json")


def walk(node: Any, path: str = "") -> Any:
    """Every (JSON pointer, key, value) of a schema document."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}/{key}", key, value
            yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}/{index}")


def vet(schema_file: Path) -> None:
    """Strict load, meta-schema check and the unsupported constructs of FR-001-46."""
    try:
        schema = load_json(schema_file)
    except ContractError as exc:
        raise GenerationError(f"{schema_file.name}: {exc.reason}") from None
    if not isinstance(schema, dict):
        raise GenerationError(f"{schema_file.name}: a schema must be a JSON object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise GenerationError(f"{schema_file.name}: not a valid 2020-12 schema ({exc.message[:120]})") from None
    own = str(schema.get("$id", "")).rsplit("/", 1)[0] + "/"
    for pointer, key, value in walk(schema):
        if key in UNSUPPORTED_KEYS:
            raise GenerationError(f"{schema_file.name}: unsupported construct {key} at {pointer}")
        if key == "$ref" and isinstance(value, str) and "://" in value and not value.startswith(own):
            raise GenerationError(f"{schema_file.name}: remote $ref {value[:80]} at {pointer}")


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "NO_COLOR": "1"}
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def generator_args(schema_name: str, target: str) -> list[str]:
    return [
        "--input", schema_name,
        *OPTIONS,
        "--custom-file-header", HEADER.format(file=schema_name),
        "--output", target,
    ]  # fmt: skip


def generate_chunk(contracts: Path, jobs: list[tuple[str, str]]) -> list[tuple[str, str | None]]:
    """Vet and generate `jobs` (schema file name, target path) in ONE interpreter started with the pinned hash seed.

    Starting an interpreter costs about 1.5 s on Windows and the generator was started once per schema (89 schemas:
    almost 3 minutes), so the worker imports it once and calls the very entry point of the command line per schema.
    Returns, per job, ("ok", None), ("vet", reason) or ("generate", reason).
    """
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(contracts)]
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "NO_COLOR": "1"}
    done = subprocess.run(
        cmd, input=json.dumps(jobs), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    try:
        results = [(str(kind), reason) for kind, reason in json.loads(done.stdout.strip().splitlines()[-1])]
    except IndexError, ValueError:
        reason = (done.stderr.strip().splitlines() or ["generator worker failed"])[-1][:200]
        return [("generate", reason)] * len(jobs)
    return [(kind, None if reason is None else str(reason)[:200]) for kind, reason in results]


def worker(contracts: Path) -> int:
    """Worker mode: read the jobs from stdin, vet and generate each, print one JSON list of (kind, reason) pairs."""
    from datamodel_code_generator.__main__ import main as generator_main  # imported once per worker, not per schema

    jobs = json.load(sys.stdin)
    os.chdir(contracts)  # the generator resolves the relative --input against the working directory, as with the CLI
    results: list[tuple[str, str | None]] = []
    for schema_name, target in jobs:
        try:
            vet(contracts / schema_name)
        except GenerationError as exc:
            results.append(("vet", str(exc).removeprefix(f"{schema_name}: ")))
            continue
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = generator_main(generator_args(schema_name, target))
            failed = int(getattr(code, "value", code)) != 0 or not Path(target).is_file()
            reason = (err.getvalue().strip().splitlines() or ["generator failed"])[-1] if failed else None
        except BaseException:  # a crash of one schema must not hide the others
            reason = traceback.format_exc().strip().splitlines()[-1]
        results.append(("ok", None) if reason is None else ("generate", reason))
    print(json.dumps(results))
    return 0


def generate_modules(schemas: list[Path], targets: list[Path]) -> None:
    """Vet and generate every schema; as in a serial run, the first vet failure wins over a generation failure."""
    by_dir: dict[Path, list[int]] = {}
    for index, schema_file in enumerate(schemas):
        by_dir.setdefault(schema_file.parent, []).append(index)
    results: dict[int, tuple[str, str | None]] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = []
        for folder, indices in by_dir.items():
            size = -(-len(indices) // WORKERS)  # ceiling division: at most WORKERS interpreters per folder
            for start in range(0, len(indices), size):
                part = indices[start : start + size]
                jobs = [(schemas[i].name, str(targets[i])) for i in part]
                futures.append((part, pool.submit(generate_chunk, folder, jobs)))
        for part, future in futures:
            results.update(zip(part, future.result(), strict=True))
    for wanted in ("vet", "generate"):
        for index, schema_file in enumerate(schemas):
            kind, reason = results[index]
            if kind == wanted:
                raise GenerationError(f"{schema_file.name}: {reason}")


def format_with_ruff(files: list[Path]) -> None:
    if not files:
        return
    cmd = [sys.executable, "-m", "ruff", "format", "--config", str(REPO / "pyproject.toml"), *map(str, files)]
    done = run(cmd, files[0].parent)
    if done.returncode != 0:
        raise GenerationError(f"ruff format failed: {(done.stderr.strip() or done.stdout.strip())[:200]}")


def init_text(stems: list[str]) -> str:
    modules = [stem.replace("-", "_") for stem in stems]
    lines = [
        "# Generated by tools/gen_types.py from the schemas in contracts/. Do not edit.",
        '"""Pydantic models of every contract schema (one module per schema)."""',
        "",
        f"from . import {', '.join(modules)}",
        "",
        f"__all__ = [{', '.join(repr(m) for m in modules)}]",
        "",
    ]
    return "\n".join(lines)


def generate(contracts: Path, workdir: Path) -> dict[str, bytes]:
    """The expected content of every generated file, by file name. Raises ``GenerationError``."""
    schemas = sorted(contracts.glob("*.schema.json"))
    stems = [stem_of(s) for s in schemas]
    out = workdir / "generated"
    out.mkdir()
    produced = [out / f"{stem_of(s).replace('-', '_')}.py" for s in schemas]
    generate_modules(schemas, produced)
    init = out / "__init__.py"
    init.write_text(init_text(stems), encoding="utf-8", newline="\n")
    format_with_ruff([*produced, init])
    return {p.name: p.read_bytes().replace(b"\r\n", b"\n") for p in sorted(out.glob("*.py"))}


def existing(out: Path) -> dict[str, bytes]:
    if not out.is_dir():
        return {}
    return {p.name: p.read_bytes().replace(b"\r\n", b"\n") for p in sorted(out.glob("*.py"))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check the Pydantic models of the contract schemas.")
    parser.add_argument("--check", action="store_true", help="exit 1 listing every file that differs; write nothing")
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS, help="folder with the *.schema.json files")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)  # internal: one generator interpreter
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="folder of the generated modules")
    args = parser.parse_args(argv)
    if args.worker is not None:
        return worker(args.worker)
    if not args.contracts.is_dir():
        print(f"usage error: {args.contracts.name} is not a directory", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(dir=os.environ.get("PITSTUDIO_TMP") or None) as tmp:
        try:
            expected = generate(args.contracts, Path(tmp))
        except GenerationError as exc:
            print(f"generation failed: {exc}", file=sys.stderr)
            return 3
    current = existing(args.out)
    problems = [f"missing: {name}" for name in sorted(expected) if name not in current]
    problems += [f"differs: {name}" for name in sorted(expected) if name in current and current[name] != expected[name]]
    problems += [f"orphan: {name}" for name in sorted(current) if name not in expected]
    if args.check:
        if problems:
            print("generated types are stale (run: uv run python tools/gen_types.py):")
            print("\n".join(f"  {p}" for p in problems))
            return 1
        print("generated types are current")
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in expected.items():
        if current.get(name) != data:
            (args.out / name).write_bytes(data)
    for name in sorted(set(current) - set(expected)):
        (args.out / name).unlink()
    print(f"generated {len(expected)} modules in {args.out.name}" + (f" ({len(problems)} changed)" if problems else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
