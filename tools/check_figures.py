"""CI check for the figure registry `web/src/theory/figures.yaml` and the raster-image rule (DC-020-04).

Usage:  python tools/check_figures.py [--root DIR]
Reads <root>/web/src/theory/figures.yaml (strict YAML, valid against contracts/figures.schema.json) and scans the
Markdown pages under <root>/docs/ for raster images. Each finding is one line and names the figure id or the file:
  1. FR-020-09: a three-dimensional figure carries `justification3d` naming its third independent variable;
  2. FR-020-10: a colour map is one of viridis, cividis, inferno or magma (jet, rainbow, hsv, turbo and custom
     gradients are refused); a figure with no continuous colour mapping states `colormap: null`;
  3. FR-020-16: a page holds no raster image (png, jpg, gif, webp, ...) unless the registry lists that file as a
     `kind: photo` entry (which carries alt text and a licence).
Exit 0 = clean, 1 = findings, 2 = usage error (no registry, unreadable input). Never a traceback.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _registry as reg

COLOURMAPS = ("viridis", "cividis", "inferno", "magma")
RASTER = re.compile(r"\.(png|jpe?g|gif|webp|bmp|avif|tiff?)$", re.I)
MD_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
REGISTRY = Path("web") / "src" / "theory" / "figures.yaml"


def _figure_findings(doc: Any) -> list[str]:
    out: list[str] = []
    for fig in doc.get("figures") or [] if isinstance(doc, dict) else []:
        if not isinstance(fig, dict) or fig.get("kind") != "chart":
            continue
        fid = fig.get("id")
        if fig.get("plot") == "3d":
            third = (fig.get("justification3d") or {}).get("third_variable") if fig.get("justification3d") else None
            if not third:
                out.append(f"figure {fid}: three-dimensional but has no justification3d naming its third variable")
        cmap = fig.get("colormap")
        if cmap is not None and cmap not in COLOURMAPS:
            out.append(f"figure {fid}: colour map {cmap!r} is not one of {', '.join(COLOURMAPS)}")
    return out


def _labelled_schema_findings(root: Path, doc: Any) -> list[str]:
    """Schema findings with the figure id in place of the array index."""
    ids = (
        [f.get("id") if isinstance(f, dict) else None for f in (doc.get("figures") or [])]
        if isinstance(doc, dict)
        else []
    )
    out = []
    for line in reg.schema_findings(root, "figures.schema.json", doc, "figures.yaml"):
        m = re.match(r"figures\.yaml: /figures/(\d+)(/.*?)?:", line)
        if m and int(m.group(1)) < len(ids) and ids[int(m.group(1))]:
            line = line.replace(f"/figures/{m.group(1)}", f"figure {ids[int(m.group(1))]}:", 1).replace(": :", ":", 1)
        out.append(line)
    return out


def _photo_files(doc: Any) -> set[str]:
    files: set[str] = set()
    for fig in doc.get("figures") or [] if isinstance(doc, dict) else []:
        if isinstance(fig, dict) and fig.get("kind") == "photo" and isinstance(fig.get("file"), str):
            files.add(posixpath.normpath(fig["file"]))
    return files


def _raster_findings(root: Path, registered: set[str]) -> list[str]:
    out: list[str] = []
    docs = root / "docs"
    for page in sorted(docs.rglob("*.md")) if docs.is_dir() else []:
        text = page.read_text(encoding="utf-8", errors="replace")
        rel_page = page.relative_to(root).as_posix()
        for ref in MD_IMAGE.findall(text) + HTML_IMAGE.findall(text):
            target = ref.split("#", 1)[0].split("?", 1)[0]
            if not RASTER.search(target):
                continue
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):  # remote image: nothing to resolve, still a raster
                resolved = target
            else:
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel_page), target))
            if resolved not in registered:
                out.append(f"{rel_page}: raster image {target} is not a registered photo (FR-020-16)")
    return out


def check(root: Path) -> list[str]:
    doc = reg.load_yaml(root / REGISTRY)
    return _labelled_schema_findings(root, doc) + _figure_findings(doc) + _raster_findings(root, _photo_files(doc))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--root", type=Path, default=reg.ROOT, help="repository root (default: this repository)")
    args = ap.parse_args(argv)
    try:
        findings = check(args.root)
    except reg.ContentError as exc:
        findings = [str(exc)]
    except reg.RegistryError as exc:
        return reg.usage_error(f"check_figures: {exc}")
    return reg.report(findings, "FIGURES CHECK OK")


if __name__ == "__main__":
    sys.exit(main())
