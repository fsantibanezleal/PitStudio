"""CI check for the case registry `studio/cases.yaml` (FR-018-10, DC-018-01).

Usage:  python tools/check_cases.py [--root DIR]
Checks, each finding on one line that names the offending id:
  1. the registry is strict YAML (a repeated case id is a duplicate key) and valid against contracts/cases.schema.json
     (categories A-E only, every case in its own category, the 12 case ids);
  1b. a KPI id repeated within one case is the finding `case-duplicate-kpi` naming the case and the id (FR-018-69; ids
     are scoped to their case);
  2. every method M1-M23 appears in at least one case and every studio tool in at least one case;
  3. every method, tool, data source and engine a case names exists: methods in studio/methods.yaml (M1-M23 when the
     file is absent), tools in studio/tools.yaml (the ids of data-model 001 section 4.3 when it is absent), sources in
     data/sources.yaml, engines in the `engine_id` enum of the schema.
Exit 0 = clean, 1 = findings, 2 = usage error (missing or unreadable input). Never a traceback.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _registry as reg

# data-model 001 section 4.3: the 17 studio tools every case set must cover, then the 3 evaluated-not-adopted entries
# and the component entries; used only while studio/tools.yaml is not committed.
STUDIO_TOOLS = [
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
OTHER_TOOLS = [
    "cuopt",
    "physicsnemo",
    "cosmos-predict-transfer",
    "pitstudio",
    "minephys",
    "minehaulsim",
    "oreblocks",
    "colmap",
    "brush",
]
METHOD_IDS = [f"M{i}" for i in range(1, 24)]


def _ids(doc: Any, *keys: str) -> set[str]:
    out: set[str] = set()
    if isinstance(doc, dict):
        for key in keys:
            for entry in doc.get(key) or []:
                if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    out.add(entry["id"])
    return out


def _known(root: Path) -> tuple[set[str], set[str], set[str], set[str]]:
    """(methods, studio tools, all tools, sources) from the registries that exist under `root`."""
    methods = set(METHOD_IDS)
    f = root / "studio" / "methods.yaml"
    if f.is_file():
        methods = _ids(reg.load_yaml(f), "methods")
    studio, tools = set(STUDIO_TOOLS), set(STUDIO_TOOLS) | set(OTHER_TOOLS)
    f = root / "studio" / "tools.yaml"
    if f.is_file():
        doc = reg.load_yaml(f)
        listed = [e for e in (doc.get("tools") or []) if isinstance(e, dict)] if isinstance(doc, dict) else []
        if listed:
            tools = _ids(doc, "tools", "components")
            studio = {
                e["id"]
                for e in listed
                if e.get("category", "studio-tool") == "studio-tool" and e.get("status") != "evaluated-not-adopted"
            }
    sources: set[str] = set()
    f = root / "data" / "sources.yaml"
    if f.is_file():
        sources = _ids(reg.load_yaml(f), "sources")
    return methods, studio, tools, sources


def check(root: Path) -> list[str]:
    doc = reg.load_yaml(root / "studio" / "cases.yaml")
    findings = reg.schema_findings(root, "cases.schema.json", doc, "studio/cases.yaml")
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), dict):
        return findings
    methods, studio, tools, sources = _known(root)
    engines = set(reg.schema_of(root, "cases.schema.json")["$defs"]["engine_id"]["enum"])
    used_methods: set[str] = set()
    used_tools: set[str] = set()
    for cid, case in doc["cases"].items():
        if not isinstance(case, dict):
            continue
        for m in case.get("methods") or []:
            used_methods.add(m)
            if m not in methods:
                findings.append(f"case {cid}: unknown method {m}")
        for t in case.get("tools") or {}:
            used_tools.add(t)
            if t not in tools:
                findings.append(f"case {cid}: unknown tool {t}")
        findings += [f"case {cid}: unknown data source {s}" for s in case.get("sources") or [] if s not in sources]
        findings += [f"case {cid}: unknown engine {e}" for e in case.get("engines") or [] if e not in engines]
        seen: set[str] = set()
        repeated: list[str] = []
        for kpi in case.get("kpis") or []:
            kid = kpi.get("id") if isinstance(kpi, dict) else None
            if isinstance(kid, str):
                if kid in seen and kid not in repeated:
                    repeated.append(kid)
                seen.add(kid)
        findings += [f"case {cid}: case-duplicate-kpi: KPI id {kid} is declared more than once" for kid in repeated]
        category = case.get("category")
        if category not in {"A", "B", "C", "D", "E"}:
            findings.append(f"case {cid}: category {category!r} is outside A-E")
    findings += [f"method {m} is in no case" for m in sorted(methods - used_methods, key=lambda x: (len(x), x))]
    findings += [f"studio tool {t} is in no case" for t in sorted(studio - used_tools)]
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--root", type=Path, default=reg.ROOT, help="repository root (default: this repository)")
    args = ap.parse_args(argv)
    try:
        findings = check(args.root)
    except reg.ContentError as exc:
        findings = [str(exc)]
    except reg.RegistryError as exc:
        return reg.usage_error(f"check_cases: {exc}")
    return reg.report(findings, "CASES CHECK OK")


if __name__ == "__main__":
    sys.exit(main())
