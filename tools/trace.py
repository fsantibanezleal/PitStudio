"""Generate the requirement traceability matrix (specs/traceability.md + specs/requirements.index.json).

Usage:  python tools/trace.py            # regenerate the files
        python tools/trace.py --check    # CI: exit 1 on orphans or unknown/retired references
IDs (never reused): US-NNN-x, FR-/NFR-/SC-/P-/DC-NNN-xx, tasks T-NNN-xxx. A requirement is DEFINED
where it appears as the first cell of a table row in specs/**/spec.md; it is RETIRED when written
~~ID~~ there. Tests reference IDs with @pytest.mark.req("ID") or a TS test title starting "ID · ".
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID = r"(?:US-\d{3}-\d{1,2}|(?:FR|NFR|SC|P|DC)-\d{3}-\d{2})"
DEF_ROW = re.compile(rf"^\|\s*(~~)?({ID})(~~)?\s*\|", re.M)
STATUS = re.compile(r"^Status:\s*([A-Za-z]+)", re.M)  # Draft/Clarified specs are not yet held to orphan checks
TASK_LINE = re.compile(r"^\s*-\s*\[[ xX]\]\s*(T-\d{3}-\d{3})(.*)$", re.M)
ANY_ID = re.compile(rf"\b{ID}\b")
PY_REQ = re.compile(rf"""\.mark\.req\(\s*["']({ID})["']""")
TS_REQ = re.compile(rf"""\b(?:it|test)\s*\(\s*[`"']({ID})\s*·""")
TEST_DIRS = ["tests", "web/src", "web/tests", "web/e2e", "pipeline/tests"]


def scan() -> dict:
    reqs: dict[str, dict] = {}
    for spec in sorted(ROOT.glob("specs/**/spec.md")):
        if "_templates" in spec.parts:
            continue
        feature = spec.parent.name
        text = spec.read_text(encoding="utf-8")
        sm = STATUS.search(text)
        draft = bool(sm and sm.group(1).lower() in {"draft", "clarified"})
        for m in DEF_ROW.finditer(text):
            rid = m.group(2)
            reqs[rid] = {"spec": feature, "retired": bool(m.group(1)), "draft": draft, "tasks": [], "tests": []}
    tasks: dict[str, list[str]] = {}
    for tf in sorted(ROOT.glob("specs/**/tasks.md")):
        for m in TASK_LINE.finditer(tf.read_text(encoding="utf-8")):
            tasks[m.group(1)] = ANY_ID.findall(m.group(2))
    unknown: list[str] = []
    for tid, ids in tasks.items():
        for rid in ids:
            if rid in reqs:
                reqs[rid]["tasks"].append(tid)
            else:
                unknown.append(f"task {tid} references unknown {rid}")
    for d in TEST_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if f.suffix not in {".py", ".ts", ".tsx"} or "node_modules" in f.parts:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            for rid in PY_REQ.findall(text) + TS_REQ.findall(text):
                r = f.relative_to(ROOT).as_posix()
                if rid in reqs:
                    if r not in reqs[rid]["tests"]:
                        reqs[rid]["tests"].append(r)
                else:
                    unknown.append(f"test {r} references unknown {rid}")
    return {"requirements": reqs, "tasks": tasks, "unknown": unknown}


def problems(data: dict) -> list[str]:
    out = list(data["unknown"])
    for rid, r in data["requirements"].items():
        if r["retired"]:
            if r["tests"]:
                out.append(f"retired {rid} is still referenced by tests {r['tests']}")
            continue
        if r.get("draft"):
            continue
        if not r["tasks"]:
            out.append(f"{rid} has no task")
        if not r["tests"] and not rid.startswith("US-"):
            out.append(f"{rid} has no test")
    return out


def render(data: dict) -> str:
    lines = [
        f"# Traceability matrix — generated {dt.date.today().isoformat()} by tools/trace.py (do not edit)",
        "",
        "| Req ID | Spec | Status | Tasks | Tests |",
        "|---|---|---|---|---|",
    ]
    for rid in sorted(data["requirements"]):
        r = data["requirements"][rid]
        status = "retired" if r["retired"] else ("draft" if r.get("draft") else "active")
        lines.append(
            f"| {rid} | {r['spec']} | {status} | {', '.join(r['tasks']) or '-'} | {', '.join(r['tests']) or '-'} |"
        )
    probs = problems(data)
    lines += ["", f"Problems: {len(probs)}"] + [f"- {p}" for p in probs]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv[1:])
    data = scan()
    (ROOT / "specs").mkdir(exist_ok=True)
    (ROOT / "specs" / "traceability.md").write_text(render(data), encoding="utf-8", newline="\n")
    (ROOT / "specs" / "requirements.index.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    probs = problems(data)
    if a.check and probs:
        print(f"TRACE CHECK FAIL ({len(probs)}):")
        for p in probs:
            print(f"  [x] {p}")
        return 1
    print(
        f"TRACE OK - {len(data['requirements'])} requirement(s), {len(data['tasks'])} task(s), {len(probs)} problem(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
