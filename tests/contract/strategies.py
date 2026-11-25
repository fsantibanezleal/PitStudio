"""Hypothesis strategies per contract document kind (data-model 8.3), locked with T-001-004.

Every strategy draws only values inside the patterns and bounds of data-model 1-6, so every drawn document must
validate against its schema; the ``MUTATIONS`` tables then break exactly one rule of a drawn document and name the
JSON pointer and keyword the first error must have. The strategies use nothing from ``pitstudio``.

Expected use: ``@given(strategies.recipes())`` ... ``Draft202012Validator`` accepts the document;
``strategies.MUTATIONS["recipe"]`` -> list of ``(name, fn(doc) -> doc, pointer, keyword)``.
"""

from __future__ import annotations

import copy
import datetime
import re
import string
from typing import Any

import contract_support as cs
import yaml
from hypothesis import strategies as st

DEVICE = {n.upper() for n in cs.WINDOWS_DEVICE_NAMES}
WORD = st.from_regex(r"[a-z][a-z0-9]{2,8}", fullmatch=True).filter(lambda s: s.upper() not in DEVICE)
SLUG = st.from_regex(r"[a-z0-9][a-z0-9-]{0,15}", fullmatch=True).filter(lambda s: s.upper() not in DEVICE)
RUN_SLUG = st.from_regex(r"[a-z0-9]([a-z0-9-]{0,14}[a-z0-9])?", fullmatch=True)  # path segments may not end in "-"
TOOL_ID = st.from_regex(r"[a-z][a-z0-9-]{1,15}", fullmatch=True).filter(lambda s: s.upper() not in DEVICE)
SHA = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
GIT_SHA = st.text(alphabet="0123456789abcdef", min_size=40, max_size=40)
TEXT = (
    st.text(alphabet=string.ascii_letters + string.digits + " .,-", min_size=1, max_size=60).map(str.strip).filter(bool)
)
LONG_TEXT = (
    st.text(alphabet=string.ascii_letters + " .,-", min_size=10, max_size=120)
    .map(str.strip)
    .filter(lambda s: len(s) >= 10)
)
SEED = st.integers(min_value=0, max_value=2**63 - 1)
QUARTERS = st.integers(min_value=1, max_value=1024).map(lambda x: x / 4)  # 0.25 ... 256.0 exactly representable
THOUSANDTHS = st.integers(min_value=0, max_value=1000).map(lambda x: x / 1000)


def _unique(draw: Any, strategy: st.SearchStrategy, n: int) -> list:
    return draw(st.lists(strategy, min_size=n, max_size=n, unique=True))


def run_id(draw: Any) -> str:
    stamp = draw(st.datetimes(min_value=datetime.datetime(2026, 1, 1), max_value=datetime.datetime(2030, 1, 1)))
    return stamp.strftime("%Y%m%dT%H%M%SZ") + "-" + draw(RUN_SLUG)


# ----------------------------------------------------------------------------------------------------------------
# recipes and job requests
# ----------------------------------------------------------------------------------------------------------------
@st.composite
def params(draw: Any) -> dict:
    keys = draw(st.lists(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True), max_size=4, unique=True))
    scalar = st.one_of(
        st.integers(-(10**6), 10**6), st.integers(-(10**6), 10**6).map(lambda x: x / 8), st.booleans(), st.none(), TEXT
    )
    out: dict[str, Any] = {}
    for k in keys:
        out[k] = draw(
            st.one_of(
                scalar,
                st.lists(st.integers(0, 1000), max_size=5),
                st.dictionaries(st.just("inner"), scalar, max_size=1),
            )
        )
    return out


@st.composite
def determinism(draw: Any) -> Any:
    kind = draw(st.sampled_from(["short", "bitwise", "statistical", "none"]))
    if kind == "short":
        return "bitwise"
    if kind == "bitwise":
        return {"class": "bitwise"}
    if kind == "statistical":
        names = draw(
            st.lists(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True), min_size=1, max_size=3, unique=True)
        )
        return {
            "class": "statistical",
            "observables": {n: {"rtol": draw(THOUSANDTHS), "atol": draw(THOUSANDTHS)} for n in names},
        }
    return {"class": "none", "reason": draw(LONG_TEXT)}


@st.composite
def recipe_stage(draw: Any, index: int, stage_id: str, earlier: list[str]) -> dict:
    gpu = draw(st.sampled_from(["exclusive", "nvenc", "none"]))
    resources: dict[str, Any] = {"gpu": gpu}
    if gpu == "exclusive" or (gpu == "nvenc" and draw(st.booleans())):
        resources["vram_gib_est"] = draw(QUARTERS)
    if draw(st.booleans()):
        resources["disk_gib_est"] = draw(st.integers(0, 40000).map(lambda x: x / 4))
    if draw(st.booleans()):
        resources["cpu"] = draw(st.integers(1, 256))
    inputs: list[dict] = [{"id": draw(SLUG), "sha256": draw(SHA)} for _ in range(draw(st.integers(0, 2)))]
    if earlier and draw(st.booleans()):
        inputs.append({"stage": draw(st.sampled_from(earlier))})
    stage: dict[str, Any] = {
        "id": stage_id,
        "env": draw(st.sampled_from(sorted(cs.STAGE_ENVS[stage_id]))),
        "tool": draw(TOOL_ID),
        "entry": draw(st.from_regex(r"[a-z_][a-z0-9_]{0,10}(\.[a-z_][a-z0-9_]{0,10}){0,3}", fullmatch=True)),
        "inputs": inputs,
        "resources": resources,
        "determinism": draw(determinism()),
        "timeout_s": draw(st.integers(1, 604800)),
        "outputs": [
            {
                "path": f"{index}/{k}-{draw(WORD)}.{draw(st.sampled_from(['json', 'parquet', 'mp4']))}",
                "schema": draw(TOOL_ID),
            }
            for k in range(draw(st.integers(1, 3)))
        ],
    }
    if draw(st.booleans()):
        stage["params"] = draw(params())
    if draw(st.booleans()):
        stage["requires"] = draw(
            st.lists(st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True), max_size=3, unique=True)
        )
    if draw(st.booleans()):
        stage["binaries"] = [{"id": draw(TOOL_ID), "sha256": draw(SHA)}]
    return stage


@st.composite
def recipes(draw: Any) -> dict:
    ids = draw(st.lists(st.sampled_from(sorted(cs.STAGE_ENVS)), min_size=1, max_size=4, unique=True))
    stages = [draw(recipe_stage(i, sid, ids[:i])) for i, sid in enumerate(ids)]
    doc: dict[str, Any] = {
        "id": draw(SLUG),
        "case": draw(st.sampled_from([*cs.CASE_IDS, "bench"])),
        "seed": draw(SEED),
        "stages": stages,
    }
    if draw(st.booleans()):
        doc["description"] = draw(TEXT)
    return doc


@st.composite
def job_requests(draw: Any) -> dict:
    doc: dict[str, Any] = {"recipe": draw(SLUG), "profile": draw(SLUG)}
    if draw(st.booleans()):
        keys = draw(
            st.lists(
                st.tuples(st.sampled_from(sorted(cs.STAGE_ENVS)), st.one_of(st.none(), SLUG)),
                min_size=1,
                max_size=5,
                unique=True,
            )
        )
        doc["stages"] = [{"id": i} if v is None else {"id": i, "variant": v} for i, v in keys]
    if draw(st.booleans()):
        doc["force"] = draw(st.booleans())
    if draw(st.booleans()):
        doc["rerun_check"] = draw(st.booleans())
    return doc


# ----------------------------------------------------------------------------------------------------------------
# tool and source registries
# ----------------------------------------------------------------------------------------------------------------
TOOL_CLASS_OPTIONS = {  # data-model 5.2, "tools" column
    "Apache-2.0": ["attribution", "own"],
    "MIT": ["attribution"],
    "BSD-2-Clause": ["attribution"],
    "BSD-3-Clause": ["attribution"],
    "MPL-2.0": ["attribution"],
    "LGPL-2.1-or-later": ["attribution"],
    "LicenseRef-TOST-1.0": ["attribution"],
    "LicenseRef-NVIDIA-Open-Model": ["reference-only"],
    "LicenseRef-NVIDIA-SLA": ["reference-only"],
    "LicenseRef-NvidiaProprietary": ["reference-only"],
    "LicenseRef-NVIDIA-Omniverse": ["reference-only"],
    "LicenseRef-TensorRT-SLA": ["reference-only"],
    "LicenseRef-TensorRT-RTX-SLA": ["reference-only"],
}


@st.composite
def tool_entry(draw: Any, tool_id: str) -> dict:
    category = draw(st.sampled_from(["studio-tool", "component"]))
    status = (
        draw(st.sampled_from(["not-yet-run", "done", "evaluated-not-adopted"])) if category == "studio-tool" else "done"
    )
    spdx = draw(st.lists(st.sampled_from(sorted(TOOL_CLASS_OPTIONS)), min_size=1, max_size=3, unique=True))
    classes = [draw(st.sampled_from(TOOL_CLASS_OPTIONS[s])) for s in spdx]
    restricted = any(s in cs.PERFORMANCE_RESTRICTED for s in spdx)
    envs = draw(
        st.lists(
            st.sampled_from(
                ["root", "runner", "studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "web"]
            ),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    version = draw(
        st.one_of(
            st.builds(
                lambda p: {"from_lock": "uv.lock", "package": p}, st.from_regex(r"[a-z][a-z0-9-]{1,20}", fullmatch=True)
            ),
            st.just({"own": True}),
            st.builds(
                lambda r, h: {"from_binary": "tool-bin", "release": r, "sha256": h},
                st.from_regex(r"[0-9]\.[0-9]\.[0-9]", fullmatch=True),
                SHA,
            ),
            st.builds(
                lambda t: {"from_git_tag": t, "repository": "https://example.org/repo/tool"},
                st.from_regex(r"v[0-9]\.[0-9]\.[0-9]", fullmatch=True),
            ),
        )
    )
    if "from_binary" in version:
        envs = [*envs[:3], "external"] if "external" not in envs and len(envs) < 4 else envs
    entry: dict[str, Any] = {
        "id": tool_id,
        "name": draw(TEXT)[:64],
        "category": category,
        "envs": envs,
        "version": version,
        "spdx": spdx,
        "osi": draw(st.booleans()),
        "licence_class": max(classes, key=cs.LICENCE_RANK.__getitem__),
        "ring": draw(st.sampled_from(["Adopt", "Trial", "Assess", "Hold"])),
        "lane": draw(st.sampled_from(["live", "replay", "local-only"])),
        "performance": "local-only" if restricted else draw(st.sampled_from(["public", "local-only"])),
        "role": draw(TEXT),
        "cases": draw(st.lists(st.sampled_from(cs.CASE_IDS), max_size=4, unique=True)),
        "produces": draw(
            st.lists(
                st.sampled_from(["video", "image", "figure", "onnx", "table", "trace", "usd"]), max_size=4, unique=True
            )
        ),
        "status": status,
    }
    if category == "studio-tool":
        entry["docs_page"] = (
            f"docs/frameworks/not-adopted-{tool_id}.md"
            if status == "evaluated-not-adopted"
            else f"docs/frameworks/{tool_id}.md"
        )
    if status == "evaluated-not-adopted":
        entry["reason"] = draw(LONG_TEXT.filter(lambda s: len(s) >= 20).map(lambda s: s + " (reason)"))
    if draw(st.booleans()):
        entry["notice"] = draw(TEXT)
    return entry


@st.composite
def tools_registries(draw: Any) -> dict:
    ids = draw(st.lists(TOOL_ID, min_size=1, max_size=4, unique=True))
    return {"tools": [draw(tool_entry(i)) for i in ids]}


@st.composite
def source_entry(draw: Any, source_id: str, earlier_id: str | None) -> dict:
    kind = draw(st.sampled_from(["real", "synthetic"]))
    spdx, _ = draw(st.sampled_from(sorted((s, k) for (s, k) in cs.SOURCE_ALLOWED if k == kind)))
    cls = draw(st.sampled_from(sorted(cs.SOURCE_ALLOWED[(spdx, kind)])))
    account = earlier_id is not None and draw(st.booleans())
    entry: dict[str, Any] = {
        "id": source_id,
        "kind": kind,
        "title": draw(TEXT),
        "landing_url": f"https://example.org/data/{source_id}",
        "access": "account" if account else draw(st.sampled_from(["direct", "api", "manual"])),
        "files": [
            {
                "url": f"https://example.org/data/{source_id}/file-{k}.bin",
                "sha256": draw(st.one_of(st.none(), SHA)),
                "bytes": draw(st.one_of(st.none(), st.integers(1, 68_719_476_736))),
                "kind": draw(st.sampled_from(["raster", "point-cloud", "vector", "image-set", "table", "document"])),
            }
            for k in range(draw(st.integers(0, 3)))
        ],
        "spdx": spdx,
        "licence_url": f"https://example.org/data/{source_id}/licence",
        "licence_class": cls,
        "redistribution": draw(st.sampled_from(["redistributable", "derived-only", "no-redistribution"])),
        "citation": draw(TEXT),
        "card": f"data/cards/{source_id}.md",
        "account": {"needed": account},
    }
    if cls in ("attribution", "share-alike"):
        entry["attribution"] = draw(TEXT)
    if account:
        entry["account"]["env_var"] = "EXAMPLE_ACCOUNT_KEY"
        entry["fallback"] = {"sources": [earlier_id], "text": draw(TEXT)}
    if draw(st.booleans()):
        entry["optional"] = draw(st.booleans())
    return entry


@st.composite
def sources_registries(draw: Any) -> dict:
    ids = draw(st.lists(SLUG, min_size=0, max_size=3, unique=True))
    out = []
    for i, sid in enumerate(ids):
        out.append(draw(source_entry(sid, ids[0] if i else None)))
    return {"sources": out}


# ----------------------------------------------------------------------------------------------------------------
# capability reports
# ----------------------------------------------------------------------------------------------------------------
@st.composite
def capabilities(draw: Any) -> dict:
    names = draw(st.lists(st.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True), max_size=4, unique=True))
    probes = {}
    for n in names:
        p: dict[str, Any] = {
            "status": draw(st.sampled_from(["pass", "fail", "skip"])),
            "versions": draw(
                st.dictionaries(
                    st.from_regex(r"[a-z][a-z0-9._-]{0,10}", fullmatch=True), TEXT.map(lambda s: s[:30]), max_size=3
                )
            ),
        }
        mode = draw(st.sampled_from(["none", "numbers", "local-only"]))
        if mode == "numbers":
            p["metrics"] = draw(
                st.dictionaries(
                    st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,12}", fullmatch=True),
                    st.integers(-1000, 1000).map(lambda x: x / 8),
                    min_size=1,
                    max_size=3,
                )
            )
            if draw(st.booleans()):
                p["telemetry"] = draw(
                    st.dictionaries(
                        st.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True),
                        st.integers(0, 1000).map(lambda x: x / 4),
                        min_size=1,
                        max_size=3,
                    )
                )
        elif mode == "local-only":
            p["metrics"] = cs.LOCAL_ONLY
        if draw(st.booleans()):
            p["notes"] = draw(st.lists(TEXT, max_size=3))
        if p["status"] == "fail" and draw(st.booleans()):
            p["error"] = draw(TEXT)
        probes[n] = p
    month, day = draw(st.integers(1, 12)), draw(st.integers(1, 28))
    return {
        "generated": f"2026-{month:02d}-{day:02d}",
        "gpu": draw(TEXT)[:100],
        "driver": f"{draw(st.integers(400, 700))}.{draw(st.integers(0, 99))}",
        "probes": probes,
    }


# ----------------------------------------------------------------------------------------------------------------
# manifests
# ----------------------------------------------------------------------------------------------------------------
STATIC_KINDS = ["image", "figure", "table", "text", "model-card", "usd"]
GATED_KINDS = ["point-cloud", "mesh", "tiles", "splat", "onnx", "trace", "shard", "field", "telemetry"]
ENCODER = {
    "codec": "av1",
    "profile": "main",
    "pix_fmt": "yuv420p",
    "width": 1280,
    "height": 720,
    "fps": 30,
    "frames": 300,
    "duration_s": 10.0,
    "bitrate_kbps": 1500.5,
    "vmaf": {"mean": 94.0, "p5": 90.5, "model": "vmaf_v0.6.1"},
    "source_frames_sha256": "1" * 64,
    "encoder": {"ffmpeg_version": "n7.1", "build_sha256": "2" * 64, "nvenc_api": "13.0", "args": ["-c:v", "av1_nvenc"]},
    "encode_fps": 200.0,
}


@st.composite
def artefacts(draw: Any, rid: str, git_sha: str, count: int) -> list[dict]:
    ids = _unique(draw, st.from_regex(r"[a-z0-9][a-z0-9_-]{0,20}", fullmatch=True), count)
    out = []
    for i, aid in enumerate(ids):
        kind = draw(st.sampled_from([*STATIC_KINDS, *GATED_KINDS, "video"]))
        host = draw(st.sampled_from(["git", "release"]))
        name = f"{i}-{draw(WORD)}.{draw(st.sampled_from(['json', 'bin', 'png']))}"
        cls = draw(st.sampled_from(cs.LICENCE_ORDER))
        a: dict[str, Any] = {
            "id": aid,
            "run_id": rid,
            "git_sha": git_sha,
            "path": name if host == "release" else f"assets/runs/r/{name}",
            "bytes": draw(st.integers(0, 10_485_759 if host == "git" else 2**53 - 1)),
            "sha256": draw(SHA),
            "kind": kind,
            "producer": {"tool": draw(TOOL_ID), "stage": {"id": draw(st.sampled_from(sorted(cs.STAGE_ENVS)))}},
            "inputs": [
                {"id": draw(SLUG), "sha256": draw(SHA), "kind": "source"} for _ in range(draw(st.integers(0, 2)))
            ],
            "licence_class": cls,
            "spdx": draw(st.sampled_from(cs.SPDX_ALLOWLIST)),
            "asset_host": host,
            "budget_class": draw(
                st.sampled_from(
                    [
                        "videos",
                        "tiles-glb",
                        "shards-clouds",
                        "splats",
                        "onnx",
                        "runtimes",
                        "own-code",
                        "studio-showcase",
                    ]
                )
            ),
        }
        if host == "release":
            a["release_tag"] = (
                f"assets-v{draw(st.integers(0, 9))}.{draw(st.integers(0, 99)):02d}.{draw(st.integers(0, 999)):03d}"
            )
        if cls not in cs.NO_ATTRIBUTION_CLASSES:
            a["attribution"] = draw(TEXT)
        if kind in STATIC_KINDS:
            a["lane"] = "static"
        else:
            a["lane"] = draw(st.sampled_from(["live", "replay"]))
            a["lane_measurements"] = {
                "web_drivable": draw(st.booleans()),
                "max_asset_bytes": draw(st.integers(0, 10**9)),
                "interaction_ms": draw(st.one_of(st.none(), st.integers(0, 100000).map(lambda x: x / 100))),
                "run_ms_t2": draw(st.one_of(st.none(), st.integers(0, 10**6).map(lambda x: x / 100))),
                "trace_bytes": draw(st.one_of(st.none(), st.integers(0, 10**9))),
                "measured": {"tier": "T2", "date": "2026-10-07", "browser": "Chromium 141"},
            }
        if kind == "video":
            a["encoder"] = copy.deepcopy(ENCODER)
        out.append(a)
    return out


@st.composite
def stage_record(draw: Any, published: bool, index: int) -> dict:
    status = draw(
        st.sampled_from(
            ["succeeded", "failed", "skipped", "cancelled", "blocked", "held", "interrupted", "env-disabled", "not_run"]
        )
    )
    ok = status in ("succeeded", "skipped", "not_run")
    perf = draw(st.sampled_from(["public", "local-only"]))
    sid = draw(st.sampled_from(sorted(cs.STAGE_ENVS)))
    s: dict[str, Any] = {
        "key": {"id": sid},
        "tool": draw(TOOL_ID),
        "env": {
            "name": draw(st.sampled_from(cs.RECIPE_ENVS)),
            "python": draw(st.sampled_from(["3.12.15", "3.14.4", None])),
            "lock_sha256": draw(SHA),
            "versions": {},
        },
        "cache_key": draw(SHA),
        "cache": draw(st.sampled_from(["hit", "miss"])),
        "status": status,
        "exit_code": 0 if ok else draw(st.integers(-5, 255)),
        "error_class": None if ok else draw(st.sampled_from(["oom", "timeout", "nonzero-exit", "guard", "unknown"])),
        "attempts": [{"n": 1, "error_class": None}],
        "params": draw(params()),
        "seed": draw(SEED),
        "determinism": {"class": "none", "rerun_check": "not-applicable"},
        "performance": perf,
        "telemetry": None,
        "thermal_flag": draw(st.booleans()),
        "inputs": [],
        "outputs": []
        if status == "not_run"
        else [{"name": f"{index}/out.bin", "sha256": draw(SHA), "bytes": draw(st.integers(0, 10**6))}],
    }
    if status == "not_run":
        s["reason"] = draw(TEXT)
    if status == "skipped" and draw(st.booleans()):
        s["reason"] = draw(TEXT)
    if status == "failed" and draw(st.booleans()):
        s["log_tail"] = draw(TEXT)
    if published and perf == "local-only":
        s["telemetry"] = cs.LOCAL_ONLY
    else:
        if draw(st.booleans()):
            s["wall_s"] = draw(st.integers(0, 10**5).map(lambda x: x / 10))
        if draw(st.booleans()):
            s["attempts"][0]["duration_s"] = draw(st.integers(0, 10**5).map(lambda x: x / 10))
    if draw(st.booleans()):
        total = draw(st.integers(1, 10000))
        s["shards"] = {"total": total, "done": draw(st.integers(0, total))}
    return s


@st.composite
def run_manifests(draw: Any) -> dict:
    published = draw(st.booleans())
    rid = run_id(draw)
    sha = draw(GIT_SHA)
    gpu: dict[str, Any] | None = None
    if draw(st.booleans()):
        gpu = {
            "backend": "nvml" if published else draw(st.sampled_from(["nvml", "fake"])),
            "index": draw(st.integers(0, 15)),
            "name": draw(TEXT),
            "driver": "582.78",
            "vram_total_bytes": draw(st.integers(0, 2**40)),
            "power_limit_enforced_w": draw(st.one_of(st.none(), st.integers(0, 4000).map(lambda x: x / 8))),
        }
    doc: dict[str, Any] = {
        "kind": "run",
        "schema_version": "1.0",
        "run_id": rid,
        "recipe": {"id": draw(SLUG), "path": f"cases/{draw(WORD)}.yaml", "sha256": draw(SHA)},
        "git_sha": sha,
        "git_dirty": False if published else draw(st.booleans()),
        "runner_version": f"{draw(st.integers(0, 9))}.{draw(st.integers(0, 99))}.{draw(st.integers(0, 99))}",
        "created": "2026-10-07T12:00:00Z",
        "profile": draw(SLUG),
        "seed": draw(SEED),
        "published": published,
        "launcher": "uv" if published else draw(st.sampled_from(["uv", "test"])),
        "gpu": gpu,
        "stages": [draw(stage_record(published, i)) for i in range(draw(st.integers(1, 3)))],
        "artefacts": draw(artefacts(rid, sha, draw(st.integers(0, 3)))),
    }
    if draw(st.booleans()):
        doc["notes"] = draw(st.lists(TEXT, max_size=3))
    return doc


@st.composite
def web_indexes(draw: Any) -> dict:
    sha = draw(GIT_SHA)
    runs = []
    for _ in range(draw(st.integers(0, 3))):
        rid = run_id(draw)
        runs.append({"run_id": rid, "manifest": f"{rid}/manifest.json", "sha256": draw(SHA)})
    rid = run_id(draw)
    # artefact ids and paths are unique inside one document (FR-001-54, FR-001-56)
    return {
        "kind": "web-index",
        "schema_version": "1.0",
        "generated": "2026-10-07",
        "git_sha": sha,
        "runs": runs,
        "artefacts": draw(artefacts(rid, sha, draw(st.integers(0, 4)))),
    }


# ----------------------------------------------------------------------------------------------------------------
# YAML renderings (P-001-07): the same document in several syntaxes, rendered by PyYAML (reference producer)
# ----------------------------------------------------------------------------------------------------------------
def reorder_keys(value: Any, reverse: bool = True) -> Any:
    if isinstance(value, dict):
        items = [(k, reorder_keys(v, reverse)) for k, v in value.items()]
        return dict(reversed(items) if reverse else items)
    if isinstance(value, list):
        return [reorder_keys(v, reverse) for v in value]
    return value


class _QuotedDumper(yaml.SafeDumper):
    """Double-quotes every string scalar (keys included) and leaves numbers, booleans and null plain."""


_QuotedDumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style='"'))


def render_yaml_variants(doc: dict) -> dict[str, str]:
    """name -> YAML text of ``doc`` (block, flow, all-quoted, reversed key order, comments added)."""
    block = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=10_000)
    plain_scalar_line = re.compile(r"^\s*(- )?[A-Za-z0-9_]+: [A-Za-z0-9_. -]+$")
    commented = "# leading comment\n" + "".join(
        f"{line}  # trailing comment\n" if plain_scalar_line.match(line) else f"{line}\n" for line in block.splitlines()
    )
    return {
        "block": block,
        "flow": yaml.safe_dump(doc, sort_keys=False, default_flow_style=True, allow_unicode=True, width=10_000_000),
        "quoted": yaml.dump(doc, Dumper=_QuotedDumper, sort_keys=False, allow_unicode=True, width=10_000),
        "reversed": yaml.safe_dump(reorder_keys(doc), sort_keys=False, allow_unicode=True, width=10_000),
        "commented": commented,
    }


# ----------------------------------------------------------------------------------------------------------------
# mutation helpers: break exactly one rule; (name, fn, pointer, keyword) of the first error
# ----------------------------------------------------------------------------------------------------------------
def _m(fn: Any) -> Any:
    def wrapped(doc: dict) -> dict:
        d = copy.deepcopy(doc)
        fn(d)
        return d

    return wrapped


MUTATIONS: dict[str, list[tuple[str, Any, str, str]]] = {
    "recipe": [
        ("seed-negative", _m(lambda d: d.update(seed=-1)), "/seed", "minimum"),
        ("seed-bool", _m(lambda d: d.update(seed=True)), "/seed", "type"),
        ("timeout-zero", _m(lambda d: d["stages"][0].update(timeout_s=0)), "/stages/0/timeout_s", "minimum"),
        ("unknown-stage-field", _m(lambda d: d["stages"][0].update(path="x")), "/stages/0", "additionalProperties"),
        ("unknown-top-field", _m(lambda d: d.update(profile="laptop")), "", "additionalProperties"),
        (
            "bad-input-digest",
            _m(lambda d: d["stages"][0].update(inputs=[{"id": "x1", "sha256": "A" * 64}])),
            "/stages/0/inputs/0/sha256",
            "pattern",
        ),
        ("entry-injection", _m(lambda d: d["stages"][0].update(entry="os; rm -rf x")), "/stages/0/entry", "pattern"),
        (
            "output-dotdot",
            _m(lambda d: d["stages"][0]["outputs"][0].update(path="a/../b")),
            "/stages/0/outputs/0/path",
            "pattern",
        ),
    ],
    "job_request": [
        ("unknown-field", _m(lambda d: d.update(entry="pkg.mod")), "", "additionalProperties"),
        ("bad-recipe-id", _m(lambda d: d.update(recipe="../x")), "/recipe", "pattern"),
        ("bad-profile", _m(lambda d: d.update(profile="Laptop")), "/profile", "pattern"),
        (
            "65-stages",
            _m(lambda d: d.update(stages=[{"id": "s00_download", "variant": f"v{i}"} for i in range(65)])),
            "/stages",
            "maxItems",
        ),
    ],
    "tools": [
        ("unknown-field", _m(lambda d: d["tools"][0].update(extra=1)), "/tools/0", "additionalProperties"),
        ("literal-version", _m(lambda d: d["tools"][0].update(version="1.2.3")), "/tools/0/version", "oneOf"),
        ("unknown-ring", _m(lambda d: d["tools"][0].update(ring="Pilot")), "/tools/0/ring", "enum"),
        ("wrong-type-osi", _m(lambda d: d["tools"][0].update(osi="yes")), "/tools/0/osi", "type"),
    ],
    "sources": [
        (
            "http-url",
            _m(lambda d: d["sources"][0].update(landing_url="http://example.org/x")),
            "/sources/0/landing_url",
            "pattern",
        ),
        ("unknown-field", _m(lambda d: d["sources"][0].update(license="MIT")), "/sources/0", "additionalProperties"),
        ("unknown-access", _m(lambda d: d["sources"][0].update(access="ftp")), "/sources/0/access", "enum"),
        (
            "card-traversal",
            _m(lambda d: d["sources"][0].update(card="data/cards/../x.md")),
            "/sources/0/card",
            "pattern",
        ),
    ],
    "capabilities": [
        ("unknown-field", _m(lambda d: d.update(host="box")), "", "additionalProperties"),
        ("bad-driver", _m(lambda d: d.update(driver="v582")), "/driver", "pattern"),
        ("bad-date", _m(lambda d: d.update(generated="2026-13-01")), "/generated", "pattern"),
        ("long-gpu", _m(lambda d: d.update(gpu="G" * 129)), "/gpu", "maxLength"),
    ],
    "run": [
        ("unknown-field", _m(lambda d: d.update(hostname="box")), "", "additionalProperties"),
        ("bad-run-id", _m(lambda d: d.update(run_id="Run-1")), "/run_id", "pattern"),
        ("seed-negative", _m(lambda d: d.update(seed=-1)), "/seed", "minimum"),
        ("empty-stages", _m(lambda d: d.update(stages=[])), "/stages", "minItems"),
        ("published-dirty", _m(lambda d: d.update(published=True, git_dirty=True)), "/git_dirty", "const"),
    ],
    "web_index": [
        ("unknown-field", _m(lambda d: d.update(hostname="box")), "", "additionalProperties"),
        ("bad-generated", _m(lambda d: d.update(generated="2026-10-07T00:00:00Z")), "/generated", "pattern"),
        ("bad-git-sha", _m(lambda d: d.update(git_sha="abc")), "/git_sha", "pattern"),
    ],
}
