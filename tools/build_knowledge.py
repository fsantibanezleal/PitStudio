"""Build the knowledge bundle and the generated knowledge pages (DC-020-03, FR-020-32 to FR-020-40).

Usage:  python tools/build_knowledge.py [--tables DIR] [--out FILE] [--check] [--root DIR]
Inputs
  --tables DIR   the knowledge tables: parameters.yaml, equations.yaml and glossary.yaml (one list per file under the
                 keys `parameters`, `equations`, `glossary`; each row has the fields of the bundle row) and
                 references.bib (BibTeX; `doi`, `url` and `access` fields). Default: the `knowledge/` folder of the
                 `minephys` version pinned in uv.lock; a pin that ships none gives empty tables.
  data/sources.yaml and studio/tools.yaml of this repository give the datasets and frameworks sections.
Outputs
  default        web/public/knowledge/bundle.json and docs/knowledge/<section>.md (the generated pages);
  --out FILE     only the bundle, written to FILE (the pages are left alone; used with fixture tables).
  --check        regenerate in memory and compare the committed bundle and pages under --root (default: this
                 repository) with the fresh ones; exit 1 naming each file that differs, is missing or is not generated.
The bundle is deterministic: rows sorted by id (bibliography by key), keys sorted, LF, one final newline, so two
generations, or generations from tables whose rows are in another order, are byte-identical (P-020-31).
Findings (exit 1, one line each naming the file and the row): a row without citation, units, page or verification, a
verification other than `verified` or `UNVERIFIED`, a citation key missing from references.bib, a bibliography entry
with neither DOI nor URL, a glossary entry without ES text, a duplicate id, or a bundle that fails its schema.
Exit 0 = clean, 1 = findings or drift, 2 = usage error. Never a traceback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _registry as reg

REPO = reg.ROOT
BUNDLE_REL = Path("web") / "public" / "knowledge" / "bundle.json"
PAGES_REL = Path("docs") / "knowledge"
SCHEMA_VERSION = "1.0"
VERIFICATION = {"verified", "UNVERIFIED"}
BIB_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)^\}", re.S | re.M)
BIB_FIELD = re.compile(r"^\s*(\w+)\s*=\s*\{(.*)\}\s*,?\s*$", re.M)
SECTIONS = ("parameters", "equations", "glossary", "datasets", "frameworks", "bibliography")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def minephys_pin(root: Path) -> tuple[str, str]:
    """(version, commit) of the `minephys` entry of uv.lock."""
    lock = root / "uv.lock"
    text = lock.read_text(encoding="utf-8") if lock.is_file() else ""
    m = re.search(r'name = "minephys"\s+version = "([^"]+)"\s+source = \{ git = "[^"#]*#([0-9a-f]{40})" \}', text)
    if not m:
        raise reg.RegistryError("uv.lock has no pinned minephys entry")
    return m.group(1), m.group(2)


def default_tables() -> Path | None:
    """The `knowledge/` folder shipped by the installed, pinned minephys, if it ships one."""
    import importlib.util

    spec = importlib.util.find_spec("minephys")
    if spec is None or not spec.submodule_search_locations:
        return None
    for base in spec.submodule_search_locations:
        if (Path(base) / "knowledge").is_dir():
            return Path(base) / "knowledge"
    return None


def parse_bib(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    entries = []
    for etype, key, body in BIB_ENTRY.findall(text + "\n"):
        fields = {k: v.strip() for k, v in BIB_FIELD.findall(body)}
        entries.append({"entry_type": etype.lower(), "key": key, **fields})
    return entries


def _rows(tables: Path, key: str) -> list[dict[str, Any]]:
    f = tables / f"{key}.yaml"
    if not f.is_file():
        return []
    doc = reg.load_yaml(f)
    rows = doc.get(key) if isinstance(doc, dict) else None
    return [r for r in rows or [] if isinstance(r, dict)]


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def row_findings(tables_rows: dict[str, list[dict[str, Any]]], bib: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    keys = {e["key"] for e in bib}
    required = {
        "parameters": ("citation", "units", "page", "verification"),
        "equations": ("citation", "page", "verification"),
        "glossary": ("term_en", "term_es", "definition_en", "definition_es"),
    }
    for section, rows in tables_rows.items():
        seen: set[str] = set()
        for row in rows:
            rid = str(row.get("id"))
            where = f"{section}.yaml: {rid}"
            if rid in seen:
                out.append(f"{where}: duplicate id")
            seen.add(rid)
            out += [f"{where}: missing {f}" for f in required[section] if _blank(row.get(f))]
            if row.get("verification") is not None and row["verification"] not in VERIFICATION:
                out.append(f"{where}: verification {row['verification']!r} is neither verified nor UNVERIFIED")
            cite = row.get("citation")
            if not _blank(cite) and cite not in keys:
                out.append(f"{where}: citation key {cite} is missing from references.bib")
    seen_keys: set[str] = set()
    for e in bib:
        where = f"references.bib: {e['key']}"
        if e["key"] in seen_keys:
            out.append(f"{where}: duplicate key")
        seen_keys.add(e["key"])
        if _blank(e.get("doi")) and _blank(e.get("url")):
            out.append(f"{where}: neither a DOI nor a URL")
    return out


def _bib_row(e: dict[str, Any], cited: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "key": e["key"],
        "entry_type": e["entry_type"],
        "authors": e.get("authors") or e.get("author") or "",
        "title": e.get("title", ""),
        "access": e.get("access", ""),
        "cited_by": {
            "parameters": sorted(cited.get(e["key"], {}).get("parameters", [])),
            "equations": sorted(cited.get(e["key"], {}).get("equations", [])),
        },
    }
    year = e.get("year", "")
    row["year"] = int(year) if str(year).isdigit() else year
    for f in ("doi", "url"):
        if not _blank(e.get(f)):
            row[f] = e[f]
    return row


def _datasets(root: Path) -> list[dict[str, Any]]:
    f = root / "data" / "sources.yaml"
    doc = reg.load_yaml(f) if f.is_file() else {}
    out = []
    for s in (doc.get("sources") if isinstance(doc, dict) else None) or []:
        card = s.get("card", "")
        out.append(
            {
                "id": s.get("id"),
                "title": s.get("title"),
                "kind": s.get("kind"),
                "spdx": s.get("spdx"),
                "redistribution": s.get("redistribution"),
                "landing_url": s.get("landing_url"),
                "card": card,
            }
        )
    return out


GLOSSARY_REL = Path("docs") / "reference" / "glossary.md"
GLOSSARY_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|$")


def _slug(term: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-") or "term"
    if not base[0].isalpha():
        base = f"t-{base}"
    base = base[:90]
    out, n = base, 2
    while out in taken:
        out, n = f"{base}-{n}", n + 1
    taken.add(out)
    return out


def _docs_glossary(root: Path) -> list[dict[str, Any]]:
    """The glossary rows of docs/reference/glossary.md (EN term | ES term | definition), origin `docs`.

    The page holds one definition per term (English); it is used for both languages until a Spanish definition exists.
    """
    f = root / GLOSSARY_REL
    if not f.is_file():
        return []
    taken: set[str] = set()
    out: list[dict[str, Any]] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        m = GLOSSARY_ROW.match(line)
        if not m or m.group(1) == "EN term" or set(m.group(1)) <= set("-: "):
            continue
        en, es, definition = (g.strip() for g in m.groups())
        out.append(
            {
                "id": _slug(en, taken),
                "origin": "docs",
                "term_en": en,
                "term_es": es,
                "definition_en": definition,
                "definition_es": definition,
            }
        )
    return out


def _frameworks(root: Path) -> list[dict[str, Any]]:
    f = root / "studio" / "tools.yaml"
    doc = reg.load_yaml(f) if f.is_file() else {}
    return [
        {k: t.get(k) for k in ("id", "name", "category", "status", "licence_class")}
        for t in (doc.get("tools") if isinstance(doc, dict) else None) or []
        if isinstance(t, dict)
    ]


def build(root: Path, tables: Path | None) -> tuple[dict[str, Any], list[str]]:
    """(bundle, findings). The bundle is complete only when there are no findings."""
    inputs: list[Path] = []
    rows: dict[str, list[dict[str, Any]]] = {}
    bib: list[dict[str, Any]] = []
    if tables is not None:
        if not tables.is_dir():
            raise reg.RegistryError(f"{tables} is not a directory")
        for key in ("parameters", "equations", "glossary"):
            rows[key] = _rows(tables, key)
            if (tables / f"{key}.yaml").is_file():
                inputs.append(tables / f"{key}.yaml")
        if (tables / "references.bib").is_file():
            bib = parse_bib(tables / "references.bib")
            inputs.append(tables / "references.bib")
    else:
        rows = {"parameters": [], "equations": [], "glossary": []}
    glossary_md = root / GLOSSARY_REL
    if not rows["glossary"]:
        rows["glossary"] = _docs_glossary(root)
    findings = row_findings(rows, bib)
    cited: dict[str, dict[str, list[str]]] = {}
    for section in ("parameters", "equations"):
        for r in rows[section]:
            cited.setdefault(str(r.get("citation")), {}).setdefault(section, []).append(str(r["id"]))
    version, commit = minephys_pin(root)
    extra = [p for p in (root / "data" / "sources.yaml", root / "studio" / "tools.yaml") if p.is_file()]
    if rows["glossary"] and rows["glossary"][0].get("origin") == "docs" and glossary_md.is_file():
        extra.append(glossary_md)
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "minephys_version": version,
            "minephys_commit": commit,
            "inputs": sorted(
                [{"path": p.name, "sha256": sha256_of(p)} for p in inputs]
                + [{"path": p.relative_to(root).as_posix(), "sha256": sha256_of(p)} for p in extra],
                key=lambda i: i["path"],
            ),
        },
        "parameters": sorted(rows["parameters"], key=lambda r: str(r["id"])),
        "equations": sorted(rows["equations"], key=lambda r: str(r["id"])),
        "glossary": sorted(rows["glossary"], key=lambda r: str(r["id"])),
        "datasets": sorted(_datasets(root), key=lambda r: str(r["id"])),
        "frameworks": sorted(_frameworks(root), key=lambda r: str(r["id"])),
        "bibliography": sorted((_bib_row(e, cited) for e in bib), key=lambda r: r["key"]),
    }
    if not findings:
        findings = reg.schema_findings(root, "knowledge-bundle.schema.json", bundle, "bundle.json")
    return bundle, findings


def bundle_text(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _cell(v: Any) -> str:
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def pages(bundle: dict[str, Any]) -> dict[str, str]:
    """The generated Markdown pages, by file name."""
    src = bundle["source"]
    provenance = (
        f"Generated by `tools/build_knowledge.py` from `minephys` {src['minephys_version']} "
        f"(commit `{src['minephys_commit'][:12]}`). Do not edit; edit the source tables and regenerate."
    )
    spec: dict[str, tuple[str, list[str], Any]] = {
        "parameters": (
            "Parameters",
            ["id", "module", "value or range", "units", "citation", "page", "verification"],
            lambda r: [
                r["id"],
                r["module"],
                r.get("value", r.get("range")),
                r["units"],
                r["citation"],
                r["page"],
                r["verification"],
            ],
        ),
        "equations": (
            "Equations",
            ["id", "title", "module", "LaTeX", "citation", "page", "verification"],
            lambda r: [
                r["id"],
                r["title"],
                r["module"],
                f"`{r['latex']}`",
                r["citation"],
                r["page"],
                r["verification"],
            ],
        ),
        "glossary": (
            "Glossary",
            ["id", "EN term", "ES term", "definition (EN)", "definition (ES)"],
            lambda r: [r["id"], r["term_en"], r["term_es"], r["definition_en"], r["definition_es"]],
        ),
        "datasets": (
            "Datasets",
            ["id", "kind", "licence", "redistribution", "landing URL", "card"],
            lambda r: [r["id"], r["kind"], r["spdx"], r["redistribution"], r["landing_url"], r["card"]],
        ),
        "frameworks": (
            "Frameworks",
            ["id", "name", "category", "status", "licence class"],
            lambda r: [r["id"], r["name"], r["category"], r["status"], r["licence_class"]],
        ),
        "bibliography": (
            "Bibliography",
            ["key", "authors", "title", "year", "DOI or URL", "cited by"],
            lambda r: [
                r["key"],
                r["authors"],
                r["title"],
                r["year"],
                r.get("doi") or r.get("url"),
                ", ".join(r["cited_by"]["parameters"] + r["cited_by"]["equations"]),
            ],
        ),
    }
    out: dict[str, str] = {}
    for section, (title, headers, row_of) in spec.items():
        rows = bundle[section]
        body = (
            _table(headers, [row_of(r) for r in rows])
            if rows
            else "No rows yet: the pinned inputs of this section hold no entries."
        )
        out[f"{section}.md"] = f"# {title}\n\n> {provenance}\n\n{len(rows)} row(s).\n\n{body}\n"
    return out


def drift(root: Path, bundle: dict[str, Any]) -> list[str]:
    out: list[str] = []
    committed = root / BUNDLE_REL
    if not committed.is_file():
        out.append(f"{BUNDLE_REL.as_posix()}: missing")
    elif committed.read_bytes() != bundle_text(bundle).encode("utf-8"):
        out.append(f"{BUNDLE_REL.as_posix()}: differs from a fresh generation")
    want = pages(bundle)
    folder = root / PAGES_REL
    for name, text in sorted(want.items()):
        f = folder / name
        if not f.is_file():
            out.append(f"{(PAGES_REL / name).as_posix()}: missing")
        elif f.read_bytes() != text.encode("utf-8"):
            out.append(f"{(PAGES_REL / name).as_posix()}: differs from a fresh generation")
    if folder.is_dir():
        out += [
            f"{(PAGES_REL / f.name).as_posix()}: not a generated page"
            for f in sorted(folder.glob("*.md"))
            if f.name != "README.md" and f.name not in want
        ]
    return out


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--tables", type=Path, help="folder with the knowledge tables (default: the pinned minephys)")
    ap.add_argument("--out", type=Path, help="write only the bundle to this file")
    ap.add_argument("--check", action="store_true", help="compare the committed outputs with a fresh generation")
    ap.add_argument("--root", type=Path, default=REPO, help="repository whose committed outputs --check compares")
    args = ap.parse_args(argv)
    try:
        tables = args.tables if args.tables is not None else default_tables()
        bundle, findings = build(REPO, tables)
    except reg.ContentError as exc:
        return reg.report([str(exc)], "")
    except reg.RegistryError as exc:
        return reg.usage_error(f"build_knowledge: {exc}")
    if findings:
        return reg.report(findings, "")
    if args.check:
        return reg.report(drift(args.root, bundle), "KNOWLEDGE CHECK OK - committed outputs match a fresh generation")
    if args.out is not None:
        write(args.out, bundle_text(bundle))
        print(f"wrote {args.out}")
        return 0
    write(args.root / BUNDLE_REL, bundle_text(bundle))
    for name, text in pages(bundle).items():
        write(args.root / PAGES_REL / name, text)
    print(f"wrote {BUNDLE_REL.as_posix()} and {len(SECTIONS)} pages under {PAGES_REL.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
