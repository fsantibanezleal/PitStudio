"""Task A on one arm: one request per query through a driver, parsing, records, metric rows (FR-015-28, 50).

`run_task_a` is the code path of `st59a_vqa` for one arm. It is driver-agnostic (`driver.ask(request) -> QueryResult`):
the real stage passes the loopback llama-server driver, the tests a fake. A fixture source (FR-015-50) runs the same
path but marks every record and row `fixture: true` and computes no accuracy.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pitstudio.reason import config, stats
from pitstudio.reason.fixture import is_fixture
from pitstudio.reason.parse import parse_answer


def build_request(
    prompts: Mapping[str, str],
    query: Mapping[str, Any],
    frame: Mapping[str, Any],
    *,
    image_root: Path | None = None,
    reasoning: bool = False,
) -> dict[str, Any]:
    """The chat request of one query: committed system prompt and type template, the frame image, greedy decoding."""
    settings = config.decoding_settings(reasoning)
    if image_root is None:
        url = frame["image"]["path"]  # reference only: nothing is read
    else:
        data = (Path(image_root) / frame["image"]["path"]).read_bytes()
        url = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    return {
        "messages": [
            {"role": "system", "content": prompts["system"]},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": prompts[f"task_a_type_{query['type']}"]},
                ],
            },
        ],
        "temperature": settings["temperature"],
        "top_k": settings["top_k"],
        "seed": settings["seed"],
        "max_tokens": settings["max_new_tokens"],
        "logprobs": True,
        "top_logprobs": 20,
    }


def run_task_a(
    queries: Mapping[str, Any],
    frames: Mapping[str, Mapping[str, Any]],
    *,
    driver: Any,
    arm: str,
    prompts: Mapping[str, str],
    out_dir: Path,
    source_path: Path,
    repo_root: Path,
    fixture: bool | None = None,
    image_root: Path | None = None,
    reasoning: bool = False,
    n_resamples: int = stats.DEFAULT_RESAMPLES,
) -> dict[str, Any]:
    """Run `queries["queries"]` through `driver`; write `records.jsonl` and `metrics.json` into `out_dir`."""
    is_fix = is_fixture(source_path, fixture=fixture, repo_root=repo_root)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for q in queries["queries"]:
        res = driver.ask(build_request(prompts, q, frames[q["frame_id"]], image_root=image_root, reasoning=reasoning))
        ok = res.status == "ok"
        parsed = parse_answer(res.text or "", reasoning=reasoning) if ok else "unparseable"
        record: dict[str, Any] = {
            "query_id": q["query_id"],
            "arm": arm,
            "question_type": q["type"],
            "condition": q["condition"],
            "output": res.text or "",
            "parsed": parsed,
            "truth": q["truth"],
            "correct": ok and parsed == q["truth"],
            "status": res.status,
            "attempts": res.attempts,
        }
        if ok and res.top_logprobs and q["type"] != 3:
            record["score"] = stats.answer_score(res.top_logprobs)
        if is_fix:
            record["fixture"] = True
        records.append(record)
    records_path = out / "records.jsonl"
    records_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")
    rows = _rows(records, arm=arm, fixture=is_fix, reasoning=reasoning, n_resamples=n_resamples)
    metrics = {"fixture": True, "rows": rows} if is_fix else {"rows": rows}
    metrics_path = out / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"fixture": is_fix, "n_records": len(records), "records_path": records_path, "metrics_path": metrics_path}


def _rows(
    records: Sequence[Mapping[str, Any]], *, arm: str, fixture: bool, reasoning: bool, n_resamples: int
) -> list[dict[str, Any]]:
    rows = []
    for qtype in sorted({r["question_type"] for r in records}):
        mine = [r for r in records if r["question_type"] == qtype]
        if fixture:
            rows.append(
                {
                    "arm": arm,
                    "type": qtype,
                    "n": len(mine),
                    "balanced_accuracy": None,
                    "f1": None,
                    "auroc": None,
                    "fixture": True,
                }
            )
            continue
        scored = stats.score_row(
            [
                {
                    k: v
                    for k, v in {
                        "truth": r["truth"],
                        "parsed": r["parsed"],
                        "condition": r["condition"],
                        "score": r.get("score"),
                        "status": "ok" if r["status"] == "ok" else "error",
                    }.items()
                    if v is not None
                }
                for r in mine
            ],
            arm=arm,
            qtype=qtype,
            reasoning=reasoning,
            n_resamples=n_resamples,
        )
        rows.append(
            {
                "arm": arm,
                "type": qtype,
                "n": scored["n"],
                "balanced_accuracy": scored["balanced_accuracy"]["value"],
                "f1": scored["f1"]["value"],
                "auroc": scored["auroc"],
            }
        )
    return rows
