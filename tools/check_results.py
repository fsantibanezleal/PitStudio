"""CI check for the published results bundles `web/public/results/<comparison-id>.json` (DC-020-02).

Usage:  python tools/check_results.py FILE...
Each file is read as JSON (NaN, Infinity and -Infinity are refused), validated against contracts/results.schema.json,
and checked against the rules the schema cannot state. Findings are one line each and name the bundle id and the row:
  1. FR-020-22/23: the stored verdict of a paired row equals the one derived from the oriented 95 % interval
     (challenger better only when lo > 0, baseline better only when hi < 0, otherwise no significant difference, an
     interval touching 0 included); lo <= hi; a paired claim has n >= 2; a metric has an orientation;
  2. FR-020-22: a McNemar row stores the exact two-sided p-value of its discordant counts (b, c); it is significant only
     when p < 0.05 and the direction comes from b versus c;
  3. FR-020-29: no entry carries performance data of TensorRT for RTX, Isaac Sim, Kit, Replicator or ovrtx, in the
     versions of its conditions or as the model of a row (FR-000-08).
Exit 0 = every file clean, 1 = findings, 2 = usage error (no file, unreadable file). Never a traceback.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _registry as reg

ALPHA = 0.05
P_TOLERANCE = (
    0.005  # a stored p-value is rounded to two decimals (as in the spec corpus); the exact p is recomputed here
)
RESTRICTED = re.compile(r"(?<![a-z0-9])(ovrtx|isaac-?sim|kit|replicator|tensorrt-?rtx)(?![a-z0-9])")


def derived_verdict(lo: float, hi: float, orientation: str) -> str:
    """FR-020-22: the interval of challenger - baseline is oriented so that positive means the challenger is better."""
    olo, ohi = (lo, hi) if orientation == "higher-is-better" else (-hi, -lo)
    if olo > 0:
        return "challenger-better"
    if ohi < 0:
        return "baseline-better"
    return "no-significant-difference"


def exact_mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p: 2 * P(X <= min(b, c)), X ~ Binomial(b + c, 1/2), capped at 1."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _row_findings(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    kind = row.get("kind")
    metric = row.get("metric") if isinstance(row.get("metric"), dict) else {}
    orientation = metric.get("orientation")
    if kind == "paired":
        interval = row.get("interval") if isinstance(row.get("interval"), dict) else {}
        lo, hi = interval.get("lo"), interval.get("hi")
        if not (_finite(lo) and _finite(hi)):
            out.append("interval bound is missing or not finite")
        elif lo > hi:
            out.append(f"interval lo {lo} is above hi {hi}")
        elif orientation in {"higher-is-better", "lower-is-better"}:
            want = derived_verdict(lo, hi, orientation)
            if row.get("verdict") != want:
                out.append(f"stored verdict {row.get('verdict')!r} differs from the derived {want!r}")
        if orientation not in {"higher-is-better", "lower-is-better"}:
            out.append("metric has no orientation")
        n = row.get("n")
        if not isinstance(n, int) or n < 2:
            out.append(f"a paired claim needs n >= 2 (n = {n!r})")
    elif kind == "mcnemar":
        b, c = row.get("b"), row.get("c")
        if isinstance(b, int) and isinstance(c, int) and _finite(row.get("p_value")):
            p = exact_mcnemar_p(b, c)
            if abs(p - row["p_value"]) > P_TOLERANCE:
                out.append(f"stored p-value {row['p_value']} differs from the exact McNemar p {p:.6g} (b={b}, c={c})")
            want = ("challenger-better" if b > c else "baseline-better") if p < ALPHA else "no-significant-difference"
            if row.get("verdict") != want:
                out.append(f"stored verdict {row.get('verdict')!r} differs from the derived {want!r}")
    return out


def _restricted(text: Any) -> bool:
    return isinstance(text, str) and RESTRICTED.search(text.lower()) is not None


def check_document(doc: Any, label: str) -> list[str]:
    """Rule findings of one parsed bundle, each prefixed with the bundle id."""
    out: list[str] = []
    if not isinstance(doc, dict):
        return out
    for i, row in enumerate(doc.get("rows") or []):
        if not isinstance(row, dict):
            continue
        mid = (row.get("metric") or {}).get("id") if isinstance(row.get("metric"), dict) else row.get("model")
        where = f"{label}: rows/{i} ({mid})"
        out += [f"{where}: {m}" for m in _row_findings(row)]
        if _restricted(row.get("model")):
            out.append(f"{where}: model {row['model']!r} is licence-restricted software (FR-020-29)")
    versions = (doc.get("conditions") or {}).get("versions") if isinstance(doc.get("conditions"), dict) else None
    for key in versions or {}:
        if _restricted(key):
            out.append(f"{label}: conditions/versions/{key}: performance data of restricted software (FR-020-29)")
    return out


def check_file(root: Path, path: Path) -> list[str]:
    label = path.stem
    try:
        doc = reg.load_json(path)
    except reg.ContentError as exc:
        return [str(exc)]
    if isinstance(doc, dict) and isinstance(doc.get("id"), str):
        label = doc["id"]
    return reg.schema_findings(root, "results.schema.json", doc, label) + check_document(doc, label)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path, metavar="FILE", help="results bundle JSON files")
    ap.add_argument(
        "--root", type=Path, default=reg.ROOT, help="repository root holding contracts/ (default: this one)"
    )
    args = ap.parse_args(argv)
    findings: list[str] = []
    try:
        for f in args.files:
            findings += check_file(args.root, f)
    except reg.RegistryError as exc:
        return reg.usage_error(f"check_results: {exc}")
    return reg.report(findings, f"RESULTS CHECK OK - {len(args.files)} file(s)")


if __name__ == "__main__":
    sys.exit(main())
