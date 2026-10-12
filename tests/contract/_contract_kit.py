"""Shared helpers of the contract-schema acceptance tests of the area specs 004 to 020.

This module holds no test. It is imported by `tests/contract/test_t_0NN_00M_*.py` and is locked with the first of them.

What every schema task asserts (the oracle is the spec's own example corpus, `specs/NNN-*/contracts/examples/`):

1. `contracts/<name>.schema.json` exists, is JSON, declares JSON Schema 2020-12, passes the reference meta-schema
   check (`Draft202012Validator.check_schema`) and keeps the `$id` of its draft
   (`https://fsantibanezleal.github.io/PitStudio/contracts/<name>.schema.json`), because sibling schemas `$ref` it.
2. every `valid: true` entry of the spec's `examples/index*.json` is accepted by the promoted schema (at the entry's
   `target`, `#` or `#/$defs/x`).
3. every `valid: false` entry is rejected, and the rejection carries an error at the entry's JSON `pointer` with the
   entry's `keyword` (errors nested in `oneOf` / `anyOf` branches count). These pairs were hand-built by the spec author
   by construction; none of them comes from running the implementation.
4. generated Pydantic models exist at `src/pitstudio/contracts/_generated/<stem>.py` (`stem` = schema file name without
   `.schema.json`, `-` replaced by `_`; a package `<stem>/__init__.py` is accepted where the generator needs one),
   carry the repository-relative header of data-model 001 section 7.1, use LF only, import, and round-trip every
   root-level valid example (`model_validate` then `model_dump(by_alias=True, exclude_unset=True, mode="json")`
   equals the example, modulo instant and trailing-slash normalisation); a root-level unknown property is rejected
   (`extra="forbid"`).
5. generated TypeScript exists at `web/src/contracts/generated/<stem>.ts` (stem with `_` or `-`), carries the banner of
   data-model 001 section 7.2, is type-only (the TypeScript compiler emits no runtime statement for it), every
   root-level valid example type-checks against the type whose name is the PascalCase of the schema `title`
   (json-schema-to-typescript naming), and the same example with one extra property fails type-checking (FR-001-44).

Expected API of the implementation: files and layout above only. No first-party Python import is needed by this kit; the
generated models are imported in a child interpreter whose `sys.path` starts with `<repo>/src`, so a test run in a git
worktree never reads another checkout's sources.
"""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://fsantibanezleal.github.io/PitStudio/contracts/"
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
GEN_PY = ROOT / "src" / "pitstudio" / "contracts" / "_generated"
GEN_TS = ROOT / "web" / "src" / "contracts" / "generated"
UNKNOWN_PROPERTY = "zz_unknown_property_for_contract_test"


# --------------------------------------------------------------------------------------------------------------------
# Example corpus
# --------------------------------------------------------------------------------------------------------------------


def spec_dir(name: str) -> Path:
    d = ROOT / "specs" / name / "contracts"
    assert d.is_dir(), f"specs/{name}/contracts is missing"
    return d


def load_examples(spec: str, schemas: Iterable[str]) -> list[dict[str, Any]]:
    """Entries of the spec's `examples/index*.json` whose `schema` is one of `schemas` (paths under contracts/)."""
    wanted = set(schemas)
    d = spec_dir(spec)
    out: list[dict[str, Any]] = []
    for idx in sorted((d / "examples").glob("index*.json")):
        entries = json.loads(idx.read_text(encoding="utf-8"))["examples"]
        out.extend({**e, "path": d / "examples" / e["file"]} for e in entries if e["schema"] in wanted)
    found = {e["schema"] for e in out}
    assert found == wanted, f"examples missing for {sorted(wanted - found)} in specs/{spec}"
    return out


def example_params(spec: str, schemas: Iterable[str], *, valid: bool) -> list[Any]:
    return [pytest.param(e, id=e["file"]) for e in load_examples(spec, schemas) if e["valid"] is valid]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------------------------
# Promoted schemas and validation
# --------------------------------------------------------------------------------------------------------------------


def promoted_path(rel: str) -> Path:
    return ROOT / "contracts" / rel


def load_promoted(rel: str) -> dict[str, Any]:
    p = promoted_path(rel)
    assert p.is_file(), f"contracts/{rel} is missing (promote the draft of the owning spec to contracts/)"
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"contracts/{rel} is not a JSON object"
    return doc


def assert_schema_promoted(rel: str) -> None:
    from jsonschema import Draft202012Validator

    schema = load_promoted(rel)
    assert schema.get("$schema") == DRAFT_2020_12, f"contracts/{rel}: $schema must be {DRAFT_2020_12}"
    Draft202012Validator.check_schema(schema)
    assert schema.get("$id") == BASE_URL + rel, f"contracts/{rel}: $id must be {BASE_URL + rel}"
    assert isinstance(schema.get("title"), str), f"contracts/{rel}: title is required"
    assert schema["title"], f"contracts/{rel}: title is required"


@functools.cache
def _registry() -> Any:
    """Promoted schemas first (also under the canonical URL); drafts only for sibling schemas not promoted yet."""
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    reg = Registry()
    seen: set[str] = set()
    for p in sorted((ROOT / "contracts").glob("**/*.schema.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        rel = p.relative_to(ROOT / "contracts").as_posix()
        res = Resource.from_contents(s, default_specification=DRAFT202012)
        for uri in {BASE_URL + rel, s.get("$id", BASE_URL + rel)}:
            reg = reg.with_resource(uri, res)
            seen.add(uri)
    for p in sorted((ROOT / "specs").glob("0*/contracts/**/*.schema.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        if s.get("$id") not in seen:
            reg = reg.with_resource(s["$id"], Resource.from_contents(s, default_specification=DRAFT202012))
    return reg


def _pointer(path: Iterable[Any]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in path)


def _flatten(err: Any, out: list[Any]) -> None:
    out.append(err)
    for c in err.context or ():
        _flatten(c, out)


def validation_errors(rel: str, target: str, doc: Any) -> list[tuple[str, str]]:
    """All (JSON pointer, keyword) pairs of the errors of `doc` against `contracts/<rel>` at `target`."""
    from jsonschema import Draft202012Validator

    load_promoted(rel)
    ref = BASE_URL + rel + ("" if target == "#" else target)
    v = Draft202012Validator({"$schema": DRAFT_2020_12, "$ref": ref}, registry=_registry())
    flat: list[Any] = []
    for e in v.iter_errors(doc):
        _flatten(e, flat)
    return [(_pointer(e.absolute_path), str(e.validator)) for e in flat]


def assert_valid_example(ex: dict[str, Any]) -> None:
    errs = validation_errors(ex["schema"], ex.get("target", "#"), read_json(ex["path"]))
    assert errs == [], f"{ex['file']} must be accepted by contracts/{ex['schema']}; errors: {sorted(set(errs))[:8]}"


def assert_hostile_example(ex: dict[str, Any]) -> None:
    errs = validation_errors(ex["schema"], ex.get("target", "#"), read_json(ex["path"]))
    want = (ex["pointer"], ex["keyword"])
    assert errs, f"{ex['file']} ({ex.get('class')}) must be rejected by contracts/{ex['schema']}"
    assert want in set(errs), (
        f"{ex['file']} ({ex.get('class')}): expected an error at pointer {want[0]!r} with keyword {want[1]!r}; "
        f"got {sorted(set(errs))[:8]}"
    )


def assert_hostile_classes(spec: str, schema: str, keywords: Iterable[str]) -> None:
    """Every named failure keyword has at least one hostile example, and the promoted schema rejects it with it."""
    hostile = [e for e in load_examples(spec, [schema]) if not e["valid"]]
    for kw in keywords:
        hits = [e for e in hostile if e["keyword"] == kw]
        assert hits, f"no hostile example of {schema} exercises keyword {kw}"
        for e in hits:
            assert_hostile_example(e)


# --------------------------------------------------------------------------------------------------------------------
# Generated files
# --------------------------------------------------------------------------------------------------------------------


def stem_of(rel: str) -> str:
    assert rel.endswith(".schema.json")
    return rel[: -len(".schema.json")]


def py_module_of(rel: str) -> str:
    return stem_of(rel).replace("-", "_")


def py_header(rel: str) -> str:
    return f"# Generated from contracts/{rel} by tools/gen_types.py. Do not edit."


def ts_banner(rel: str) -> str:
    return f"/* Generated from contracts/{rel} by web/scripts/gen-types.mjs. Do not edit. */"


def ts_file_of(rel: str) -> Path | None:
    stem = stem_of(rel)
    for cand in (GEN_TS / f"{stem.replace('-', '_')}.ts", GEN_TS / f"{stem}.ts"):
        if cand.is_file():
            return cand
    return None


def ts_type_name(title: str) -> str:
    """json-schema-to-typescript `toSafeString` for ASCII titles: separators dropped, each word capitalised."""
    s = re.sub(r"(^\s*[^a-zA-Z_$])|([^a-zA-Z_$\d])", " ", title)
    s = re.sub(r"^_[a-z]", lambda m: m.group(0).upper(), s)
    s = re.sub(r"_[a-z]", lambda m: m.group(0)[1:].upper(), s)
    s = re.sub(r"([\d$]+[a-zA-Z])", lambda m: m.group(0).upper(), s)
    s = re.sub(r"\s+([a-zA-Z])", lambda m: m.group(0).strip().upper(), s)
    s = re.sub(r"\s", "", s)
    return s[:1].upper() + s[1:]


def _root_examples(spec: str, rel: str) -> list[dict[str, Any]]:
    return [
        e
        for e in load_examples(spec, [rel])
        if e["valid"] and e.get("target", "#") == "#" and isinstance(read_json(e["path"]), dict)
    ]


_PY_RUNNER = r"""
import importlib, json, re, sys
from datetime import datetime

root, job_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, root + "/src")
jobs = json.load(open(job_path, encoding="utf-8"))
problems = []

def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def instant(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def same(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        if a == b or a.rstrip("/") == b.rstrip("/"):  # pydantic AnyUrl adds a trailing slash to bare hosts
            return True
        try:
            return instant(a) == instant(b)
        except ValueError:
            return False
    return a == b

for job in jobs:
    name = "pitstudio.contracts._generated." + job["module"]
    try:
        mod = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{job['module']}: import failed: {type(exc).__name__}: {str(exc)[:300]}")
        continue
    from pydantic import BaseModel, ValidationError
    classes = [v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, BaseModel) and v.__module__.startswith(mod.__name__)]
    if not classes:
        problems.append(f"{job['module']}: no pydantic model defined")
        continue
    by_title = [c for c in classes if norm(c.__name__) == norm(job["title"])]
    model = by_title[0] if by_title else classes[-1]
    for path in job["examples"]:
        doc = json.load(open(path, encoding="utf-8"))
        label = job["module"] + " <- " + path.rsplit("/", 1)[-1]
        try:
            obj = model.model_validate(doc)
        except ValidationError as exc:
            problems.append(f"{label}: valid example rejected by {model.__name__}: {str(exc)[:300]}")
            continue
        back = obj.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if not same(doc, back):
            problems.append(f"{label}: round trip differs")
        bad = dict(doc)
        bad[job["unknown"]] = 1
        try:
            model.model_validate(bad)
            problems.append(f"{label}: unknown root property accepted (extra must be forbidden)")
        except ValidationError:
            pass
print(json.dumps(problems))
"""


def assert_generated_python(spec: str, schemas: Iterable[str]) -> None:
    jobs = []
    problems: list[str] = []
    for rel in schemas:
        mod = py_module_of(rel)
        f = GEN_PY / f"{mod}.py"
        if not f.is_file():  # a schema whose cross-file refs force the generator into a package keeps its module name
            f = GEN_PY / mod / "__init__.py"
        if not f.is_file():
            problems.append(f"src/pitstudio/contracts/_generated/{mod}.py is missing")
            continue
        raw = f.read_bytes()
        text = raw.decode("utf-8")
        if text.splitlines()[0] != py_header(rel):
            problems.append(f"{mod}.py: first line must be {py_header(rel)!r}")
        if b"\r\n" in raw:
            problems.append(f"{mod}.py: line endings must be LF")
        if re.search(r"[A-Za-z]:[\\/]|/home/|/Users/", "\n".join(text.splitlines()[:3])):
            problems.append(f"{mod}.py: an absolute path reached the generated file header")
        jobs.append(
            {
                "module": mod,
                "title": load_promoted(rel)["title"],
                "examples": [str(e["path"]) for e in _root_examples(spec, rel)],
                "unknown": UNKNOWN_PROPERTY,
            }
        )
    if jobs:
        with tempfile.TemporaryDirectory() as td:
            jp = Path(td) / "jobs.json"
            jp.write_text(json.dumps(jobs), encoding="utf-8")
            r = subprocess.run(
                [sys.executable, "-I", "-c", _PY_RUNNER, str(ROOT), str(jp)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=600,
            )
        if r.returncode != 0:
            problems.append(f"generated-model runner crashed: {r.stderr[-600:]}")
        else:
            problems.extend(json.loads(r.stdout.strip().splitlines()[-1]))
    assert not problems, "generated Pydantic models:\n" + "\n".join(problems[:20])


def _tsc() -> list[str]:
    tsc = ROOT / "web" / "node_modules" / "typescript" / "bin" / "tsc"
    node = shutil.which("node")
    if not tsc.is_file() or node is None:
        pytest.fail("environment: node and web/node_modules/typescript are needed (run `pnpm install` in web/)")
    return [node, str(tsc)]


_STRIP_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def assert_generated_typescript(spec: str, schemas: Iterable[str]) -> None:
    problems: list[str] = []
    rels = list(schemas)
    files: dict[str, Path] = {}
    for rel in rels:
        f = ts_file_of(rel)
        if f is None:
            problems.append(f"web/src/contracts/generated/{stem_of(rel)}.ts (or with underscores) is missing")
            continue
        files[rel] = f
        text = f.read_text(encoding="utf-8")
        if ts_banner(rel) not in "\n".join(text.splitlines()[:4]):
            problems.append(f"{f.name}: banner {ts_banner(rel)!r} missing from the first lines")
        if "\r\n" in text:
            problems.append(f"{f.name}: line endings must be LF")
        if re.search(r"[A-Za-z]:[\\/]|/home/|/Users/", "\n".join(text.splitlines()[:3])):
            problems.append(f"{f.name}: an absolute path reached the generated file header")
        name = ts_type_name(load_promoted(rel)["title"])
        if not re.search(rf"export\s+(?:interface|type)\s+{re.escape(name)}\b", text):
            problems.append(f"{f.name}: no exported type named {name} (PascalCase of the schema title)")
    if problems:
        raise AssertionError("generated TypeScript:\n" + "\n".join(problems[:20]))
    tsc = _tsc()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "generated").mkdir()
        for f in files.values():  # each generated module is self-contained (cross-file refs are inlined)
            shutil.copy(f, tmp / "generated" / f.name)
        lines: list[str] = []
        expect_ok: dict[int, str] = {}
        expect_bad: dict[int, str] = {}
        for i, rel in enumerate(rels):
            mod = files[rel].stem
            name = ts_type_name(load_promoted(rel)["title"])
            lines.append(f'import type {{ {name} as T{i} }} from "./generated/{mod}";')
        for i, rel in enumerate(rels):
            for j, e in enumerate(_root_examples(spec, rel)):
                doc = read_json(e["path"])
                lines.append(f"const v{i}_{j}: T{i} = {json.dumps(doc, ensure_ascii=False, allow_nan=False)};")
                expect_ok[len(lines)] = e["file"]
                bad = {**doc, UNKNOWN_PROPERTY: 1}
                lines.append(f"const m{i}_{j}: T{i} = {json.dumps(bad, ensure_ascii=False, allow_nan=False)};")
                expect_bad[len(lines)] = e["file"]
        lines.append("export {};")
        (tmp / "check.ts").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (tmp / "tsconfig.json").write_text(
            json.dumps(
                {
                    "include": ["check.ts", "generated/**/*.ts"],
                    "compilerOptions": {
                        "strict": True,
                        "target": "ES2022",
                        "module": "ES2022",
                        "moduleResolution": "bundler",
                        "lib": ["ES2022"],
                        "types": [],
                        "skipLibCheck": True,
                        "outDir": "out",
                    },
                }
            ),
            encoding="utf-8",
        )
        r = subprocess.run(
            [*tsc, "-p", str(tmp / "tsconfig.json"), "--pretty", "false"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
            cwd=tmp,
        )
        diag = re.findall(r"^(\S+?)\((\d+),\d+\): error (TS\d+): ([^\n]*)", r.stdout, re.M)
        bad_lines = {int(ln) for fn, ln, _, _ in diag if fn.endswith("check.ts")}
        why = {int(ln): f"{code}: {msg[:160]}" for fn, ln, code, msg in diag if fn.endswith("check.ts")}
        other = [d for d in diag if not d[0].endswith("check.ts")]
        if other:
            problems.append(f"generated modules do not compile: {other[:5]}")
        for ln, f in expect_ok.items():
            if ln in bad_lines:
                problems.append(f"{f}: valid example does not type-check against its generated type ({why[ln]})")
        for ln, f in expect_bad.items():
            if ln not in bad_lines:
                problems.append(f"{f}: an extra root property must fail type-checking")
        if not diag and r.returncode not in (0, 2):
            problems.append(f"tsc failed unexpectedly: {(r.stdout + r.stderr)[-400:]}")
        for f in files.values():
            js = tmp / "out" / "generated" / (f.stem + ".js")
            body = _STRIP_COMMENTS.sub("", js.read_text(encoding="utf-8")).strip() if js.is_file() else ""
            if body not in ("", "export {};", "export {}"):
                problems.append(
                    f"{f.name}: generated TypeScript must be type-only; emitted runtime code: {body[:80]!r}"
                )
    assert not problems, "generated TypeScript:\n" + "\n".join(problems[:20])


def assert_gen_types_check_clean() -> None:
    """`python tools/gen_types.py --check` (FR-001-42) exits 0: no generated file drifts from its schema."""
    tool = ROOT / "tools" / "gen_types.py"
    assert tool.is_file(), "tools/gen_types.py is missing (spec 001, FR-001-40)"
    r = subprocess.run(
        [sys.executable, str(tool), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=900,
    )
    assert r.returncode == 0, f"gen_types.py --check exited {r.returncode}: {(r.stdout + r.stderr)[-500:]}"


# --------------------------------------------------------------------------------------------------------------------
# Strict YAML and tool runs (registry tasks)
# --------------------------------------------------------------------------------------------------------------------


def load_yaml_strict(path: Path) -> Any:
    """PyYAML safe loader that refuses duplicate mapping keys (FR-001-06) and aliases."""
    import yaml

    class Strict(yaml.SafeLoader):
        pass

    def mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for k, _ in node.value:
            key = loader.construct_object(k, deep=deep)
            assert key not in seen, f"{path.name}: duplicate key {key!r}"
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    assert path.is_file(), f"{path.relative_to(ROOT).as_posix()} is missing"
    return yaml.load(path.read_text(encoding="utf-8"), Loader=Strict)


def run_tool(script: str, *args: str, cwd: Path | None = None) -> tuple[int, str]:
    """Run `python tools/<script> args` and return (exit code, stdout + stderr). A missing tool is a red failure."""
    tool = ROOT / "tools" / script
    assert tool.is_file(), f"tools/{script} is missing"
    r = subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd or ROOT,
        timeout=600,
    )
    return r.returncode, r.stdout + r.stderr


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True)
