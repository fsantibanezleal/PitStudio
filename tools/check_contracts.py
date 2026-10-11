"""CI check: every committed contract document against its schema, plus the rules a schema cannot state.

Usage:  python tools/check_contracts.py [--root DIR] [--json] [--release-assets DIR]
Exit:   0 clean, 1 findings, 2 usage error. A finding is (file, rule, pointer, message, error_class); no input,
        however broken, produces a traceback.

Documents (data-model 8.1): studio/tools.yaml, data/sources.yaml, studio/recipes/{cases,_bench,_profiles}/*.yaml,
studio/capabilities.json, web/public/assets/manifest.json, web/public/assets/runs/*/{manifest,telemetry}.json and
models/cards/*/manifest.json. Any other file in contracts/, studio/recipes/ or web/public/assets/runs/ is a finding.
The schemas always come from the repository that holds this script; ``--root`` selects the tree that is checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

TOOLS_DIR = Path(__file__).resolve().parent
REPO = TOOLS_DIR.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TOOLS_DIR))

import check_repo  # noqa: E402  (the secret patterns live there; reused, never copied)

from pitstudio.contracts import ContractError, load_json, load_yaml, validate  # noqa: E402
from pitstudio.contracts.lane import lane_failures  # noqa: E402
from pitstudio.contracts.licence import RANK, SHARE_ALIKE_SPDX, derivative_problems  # noqa: E402
from pitstudio.contracts.privacy import iter_strings, leaks, machine_identity  # noqa: E402
from pitstudio.contracts.sources import TOO_PERMISSIVE, too_permissive_entries  # noqa: E402

MAX_MESSAGE = 300
CAPS = {  # data-model 1.4
    "recipe": 262_144,
    "tools": 262_144,
    "sources": 1_048_576,
    "capabilities": 262_144,
    "run": 4_194_304,
    "web-index": 8_388_608,
}
STATIC_KINDS = frozenset({"image", "figure", "table", "text", "model-card", "usd"})
CREDENTIAL_QUERY_NAMES = frozenset({"key", "token", "apikey", "api_key", "access_token", "signature"})
RULE_OF_KEYWORD = {
    "duplicate-id": "FR-001-54",
    "shards": "FR-001-55",
    "shard-count": "FR-001-23",
    "params-size": "FR-001-23",
    "device-name": "FR-001-56",
    "duplicate-path": "FR-001-56",
    "control-char": "FR-001-57",
}
SCHEMA_RULE = "FR-001-50"
LOAD_RULE = "FR-001-51"
UNKNOWN_FILE = "file is not a contract document of its folder"
STUDIO_TOOL_COUNT = 20
PNPM_KEY = re.compile(r"""^\s{2,6}['"]?(@?[^@'"\s:]+(?:/[^@'"\s:]+)?)@""", re.M)


@dataclass(frozen=True, order=True)
class Finding:
    file: str
    pointer: str
    rule: str
    message: str
    error_class: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "rule": self.rule,
            "pointer": self.pointer,
            "message": self.message,
            "error_class": self.error_class,
        }


def clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_MESSAGE else text[: MAX_MESSAGE - 3] + "..."


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def sha256_of(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class Checker:
    def __init__(self, root: Path, release_assets: Path | None) -> None:
        self.root = root.resolve()
        self.release_assets = release_assets
        self.findings: set[Finding] = set()
        self.identity = machine_identity()
        self.tools: dict[str, Any] | None = None
        self.sources: dict[str, dict[str, Any]] | None = None
        self.lock_cache: dict[str, set[str] | str] = {}

    # ------------------------------------------------------------------------------------------------------------
    def add(self, file: str, rule: str, pointer: str, message: str, error_class: str | None = None) -> None:
        self.findings.add(Finding(file, pointer, rule, clip(message), error_class))

    def inside(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.root)
        except OSError:
            return False

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    # ------------------------------------------------------------------------------------------------------------
    def read(self, path: Path, kind: str) -> Any | None:
        """Load one document; every defect is a finding and returns None."""
        rel = self.rel(path)
        if not path.is_file():
            self.add(rel, LOAD_RULE, "", "not a regular file")
            return None
        if not self.inside(path):
            self.add(rel, LOAD_RULE, "", "the file resolves outside the repository")
            return None
        loader = load_yaml if path.suffix in (".yaml", ".yml") else load_json
        try:
            return loader(path, max_bytes=CAPS.get(kind))
        except ContractError as exc:
            self.add(rel, LOAD_RULE, exc.pointer or "", f"{exc.reason}" + (f" (line {exc.line})" if exc.line else ""))
        except Exception as exc:
            self.add(rel, LOAD_RULE, "", f"cannot be read ({type(exc).__name__})")
        return None

    def schema(self, rel: str, document: Any, name: str) -> None:
        for error in validate(document, name):
            self.add(rel, RULE_OF_KEYWORD.get(error.keyword, SCHEMA_RULE), error.pointer, error.message)

    # ------------------------------------------------------------------------------------------------------------
    def run(self) -> list[Finding]:
        self.unknown_files()
        self.check_tools()
        self.check_sources()
        self.check_capabilities()
        self.check_recipes()
        self.check_manifests()
        return sorted(self.findings)

    # ------------------------------------------------------------------------------------------------------------
    # unknown files (FR-001-51)
    # ------------------------------------------------------------------------------------------------------------
    def unknown_files(self) -> None:
        contracts = self.root / "contracts"
        if contracts.is_dir():
            for entry in sorted(contracts.iterdir()):
                if not (entry.name.endswith(".schema.json") or entry.name == "README.md"):
                    self.add(self.rel(entry), LOAD_RULE, "", UNKNOWN_FILE)
        recipes = self.root / "studio/recipes"
        if recipes.is_dir():
            for path in sorted(recipes.rglob("*")):
                if path.is_dir():
                    continue
                parts = path.relative_to(recipes).parts
                if not (len(parts) == 2 and parts[0] in ("cases", "_bench", "_profiles") and path.suffix == ".yaml"):
                    self.add(self.rel(path), LOAD_RULE, "", UNKNOWN_FILE)
        runs = self.root / "web/public/assets/runs"
        if runs.is_dir():
            for entry in sorted(runs.iterdir()):
                if not entry.is_dir():
                    self.add(self.rel(entry), LOAD_RULE, "", UNKNOWN_FILE)
                    continue
                for inner in sorted(entry.iterdir()):
                    if inner.name not in ("manifest.json", "telemetry.json"):
                        self.add(self.rel(inner), LOAD_RULE, "", UNKNOWN_FILE)

    # ------------------------------------------------------------------------------------------------------------
    # tool registry (FR-001-25, -26, -53)
    # ------------------------------------------------------------------------------------------------------------
    def check_tools(self) -> None:
        path = self.root / "studio/tools.yaml"
        if not path.exists() and not path.is_symlink():
            return
        rel = self.rel(path)
        doc = self.read(path, "tools")
        if doc is None:
            return
        self.schema(rel, doc, "tools")
        self.tools = {t["id"]: t for t in as_list(as_dict(doc).get("tools")) if isinstance(t, dict) and "id" in t}
        entries = as_list(as_dict(doc).get("tools"))
        studio = [t for t in entries if isinstance(t, dict) and t.get("category") == "studio-tool"]
        if len(studio) != STUDIO_TOOL_COUNT:
            self.add(
                rel, "FR-001-25", "/tools", f"{len(studio)} studio-tool entries, exactly {STUDIO_TOOL_COUNT} required"
            )
        for index, tool in enumerate(entries):
            if not isinstance(tool, dict):
                continue
            tid, base = str(tool.get("id")), f"/tools/{index}"
            self.check_version(rel, tid, base, tool)
            page = tool.get("docs_page")
            if isinstance(page, str):
                prefix = "not-adopted-" if tool.get("status") == "evaluated-not-adopted" else ""
                expected = f"docs/frameworks/{prefix}{tid}.md"
                if tool.get("category") == "studio-tool" and page != expected:
                    self.add(rel, "FR-001-53", f"{base}/docs_page", f"tool {tid}: docs_page must be {expected}")
                elif not (self.root / page).is_file():
                    self.add(rel, "FR-001-53", f"{base}/docs_page", f"tool {tid}: docs page {page} does not exist")

    def lock_packages(self, lock: str) -> set[str] | str:
        """The package names of a lock file, or the reason it cannot be read."""
        if lock not in self.lock_cache:
            path = self.root / lock
            try:
                if not path.is_file() or not self.inside(path):
                    raise FileNotFoundError
                text = path.read_bytes().decode("utf-8")
                if lock.endswith("pnpm-lock.yaml"):
                    names = set(PNPM_KEY.findall(text))
                else:
                    names = {
                        re.sub(r"[-_.]+", "-", str(p["name"])).lower() for p in tomllib.loads(text).get("package", [])
                    }
                self.lock_cache[lock] = names
            except FileNotFoundError:
                self.lock_cache[lock] = "the lock file does not exist"
            except Exception:
                self.lock_cache[lock] = "the lock file cannot be parsed"
        return self.lock_cache[lock]

    def check_version(self, rel: str, tid: str, base: str, tool: dict[str, Any]) -> None:
        version = tool.get("version")
        if not isinstance(version, dict):
            return
        pointer = f"{base}/version"
        if "from_lock" in version and isinstance(version.get("from_lock"), str):
            lock, package = version["from_lock"], str(version.get("package"))
            known = self.lock_packages(lock)
            if isinstance(known, str):
                self.add(rel, "FR-001-26", pointer, f"tool {tid}: {lock}: {known}")
            else:
                wanted = package if lock.endswith("pnpm-lock.yaml") else re.sub(r"[-_.]+", "-", package).lower()
                if wanted not in known:
                    self.add(rel, "FR-001-26", pointer, f"tool {tid}: package {package} is not in {lock}")
        elif "from_binary" in version and "external" not in as_list(tool.get("envs")):
            self.add(rel, "FR-001-26", pointer, f"tool {tid}: a pinned-binary version needs the external environment")

    # ------------------------------------------------------------------------------------------------------------
    # source registry (FR-001-32, -52, -58)
    # ------------------------------------------------------------------------------------------------------------
    def check_sources(self) -> None:
        path = self.root / "data/sources.yaml"
        if not path.exists() and not path.is_symlink():
            return
        rel = self.rel(path)
        doc = self.read(path, "sources")
        if doc is None:
            return
        self.schema(rel, doc, "sources")
        entries = as_list(as_dict(doc).get("sources"))
        self.sources = {e["id"]: e for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}
        for index, entry in enumerate(entries):
            if isinstance(entry, dict):
                self.check_source(rel, index, entry)
        for index, _entry_id, message in too_permissive_entries(doc):
            self.add(rel, "FR-001-58", f"/sources/{index}", message, TOO_PERMISSIVE)

    def check_source(self, rel: str, index: int, entry: dict[str, Any]) -> None:
        sid, base = str(entry.get("id")), f"/sources/{index}"
        urls = [("landing_url", entry.get("landing_url")), ("licence_url", entry.get("licence_url"))]
        urls += [(f"files/{i}/url", as_dict(f).get("url")) for i, f in enumerate(as_list(entry.get("files")))]
        for name, url in urls:
            if isinstance(url, str):
                try:
                    query = parse_qsl(urlsplit(url).query, keep_blank_values=True)
                except ValueError:
                    continue
                bad = sorted({k for k, _ in query if k.lower() in CREDENTIAL_QUERY_NAMES})
                if bad:
                    self.add(
                        rel, "FR-001-32", f"{base}/{name}", f"source {sid}: credential-like query parameter {bad[0]}"
                    )
        for pointer, text in iter_strings(entry, base):
            if check_repo.CHECKS["secret"].search(text):
                self.add(rel, "FR-001-32", pointer, f"source {sid}: a value matches a secret pattern")
        fallback = as_dict(entry.get("fallback"))
        for position, other in enumerate(as_list(fallback.get("sources"))):
            if not isinstance(other, str):
                continue
            if other == sid:
                self.add(
                    rel,
                    "FR-001-52",
                    f"{base}/fallback/sources/{position}",
                    f"source {sid}: fallback names the entry itself",
                )
            elif self.sources is not None and other not in self.sources:
                self.add(
                    rel,
                    "FR-001-52",
                    f"{base}/fallback/sources/{position}",
                    f"source {sid}: fallback {other} is not a registry id",
                )
        files = [as_dict(f) for f in as_list(entry.get("files"))]
        spdx = {f.get("spdx", entry.get("spdx")) for f in files} or {entry.get("spdx")}
        spdx.discard(None)
        if spdx & SHARE_ALIKE_SPDX and len(spdx) > 1:
            self.add(
                rel,
                "FR-001-52",
                f"{base}/files",
                f"source {sid}: a share-alike id is mixed with another id ({', '.join(sorted(map(str, spdx)))})",
            )

    # ------------------------------------------------------------------------------------------------------------
    # capability report (FR-001-59)
    # ------------------------------------------------------------------------------------------------------------
    def check_capabilities(self) -> None:
        path = self.root / "studio/capabilities.json"
        if not path.exists() and not path.is_symlink():
            return
        rel = self.rel(path)
        doc = self.read(path, "capabilities")
        if doc is None:
            return
        self.schema(rel, doc, "capabilities")
        for name, probe in as_dict(as_dict(doc).get("probes")).items():
            probe = as_dict(probe)
            texts = [(f"/probes/{name}/error", probe.get("error"))]
            texts += [(f"/probes/{name}/notes/{i}", n) for i, n in enumerate(as_list(probe.get("notes")))]
            for pointer, text in texts:
                if isinstance(text, str) and (why := leaks(text, self.identity)):
                    self.add(rel, "FR-001-59", pointer, f"text holds an {why}", "privacy-leak")

    # ------------------------------------------------------------------------------------------------------------
    # recipes (FR-001-29)
    # ------------------------------------------------------------------------------------------------------------
    def check_recipes(self) -> None:
        for folder in ("cases", "_bench"):
            base = self.root / "studio/recipes" / folder
            if not base.is_dir():
                continue
            for path in sorted(base.glob("*.yaml")):
                doc = self.read(path, "recipe")
                if doc is None:
                    continue
                rel = self.rel(path)
                self.schema(rel, doc, "recipe")
                if self.tools is None:
                    continue
                for index, stage in enumerate(as_list(as_dict(doc).get("stages"))):
                    tool = as_dict(stage).get("tool")
                    if isinstance(tool, str) and tool not in self.tools:
                        self.add(rel, "FR-001-29", f"/stages/{index}/tool", f"stage tool {tool} is not a registry id")
        profiles = self.root / "studio/recipes/_profiles"
        if profiles.is_dir():
            for path in sorted(profiles.glob("*.yaml")):
                self.read(path, "recipe")  # strict syntax only: the profile schema belongs to spec 002

    # ------------------------------------------------------------------------------------------------------------
    # manifests (FR-001-13, -15 ... -20, -29, -33)
    # ------------------------------------------------------------------------------------------------------------
    def check_manifests(self) -> None:
        index_path = self.root / "web/public/assets/manifest.json"
        if index_path.exists() or index_path.is_symlink():
            doc = self.read(index_path, "web-index")
            if doc is not None:
                self.manifest(self.rel(index_path), doc, "web-index")
                self.served_files(self.rel(index_path), doc)
        runs = self.root / "web/public/assets/runs"
        if runs.is_dir():
            for entry in sorted(runs.iterdir()):
                if entry.is_dir():
                    for name in ("manifest.json", "telemetry.json"):
                        path = entry / name
                        if path.exists() or path.is_symlink():
                            doc = self.read(path, "run")
                            if doc is not None and name == "manifest.json":
                                self.manifest(self.rel(path), doc, "run")
        cards = self.root / "models/cards"
        if cards.is_dir():
            for path in sorted(cards.glob("*/manifest.json")):
                doc = self.read(path, "run")
                if doc is not None:
                    self.manifest(self.rel(path), doc, "run")

    def manifest(self, rel: str, doc: Any, kind: str) -> None:
        self.schema(rel, doc, "manifest")
        body = as_dict(doc)
        published = kind == "web-index" or body.get("published") is True
        for pointer, text in iter_strings(doc):
            if why := leaks(text, self.identity):
                self.add(rel, "FR-001-15", pointer, f"string holds an {why}", "privacy-leak")
        artefacts = [as_dict(a) for a in as_list(body.get("artefacts"))]
        by_id = {a["id"]: a for a in artefacts if isinstance(a.get("id"), str)}
        stages = [as_dict(s) for s in as_list(body.get("stages"))]
        for index, art in enumerate(artefacts):
            self.check_artefact(rel, index, art, by_id, stages, kind, published)
        if kind == "run":
            self.check_stages(rel, stages, by_id, published)

    def check_artefact(
        self,
        rel: str,
        index: int,
        art: dict[str, Any],
        by_id: dict[str, dict[str, Any]],
        stages: list[dict[str, Any]],
        kind: str,
        published: bool,
    ) -> None:
        aid, base = str(art.get("id")), f"/artefacts/{index}"
        lane, measurements = art.get("lane"), art.get("lane_measurements")
        if lane in ("live", "replay") and isinstance(measurements, dict):
            try:
                failing = lane_failures(measurements)
            except ContractError as exc:
                self.add(rel, "FR-001-13", f"{base}/lane_measurements", f"artefact {aid}: {exc.reason}")
            else:
                if lane == "live" and failing:
                    self.add(rel, "FR-001-13", base, f"artefact {aid}: declared live but fails {', '.join(failing)}")
                elif lane == "replay" and not failing:
                    self.add(rel, "FR-001-13", base, f"artefact {aid}: declared replay but the gate gives live")
        encoder = art.get("encoder")
        if isinstance(encoder, dict):
            try:
                frames, fps, duration = encoder["frames"], encoder["fps"], encoder["duration_s"]
                if abs(duration - frames / fps) > 1 / fps:
                    self.add(
                        rel,
                        "FR-001-17",
                        f"{base}/encoder",
                        f"artefact {aid}: duration_s {duration} is over one frame from frames/fps = {frames / fps:.6g}",
                    )
            except KeyError, TypeError, ZeroDivisionError:
                pass
        producer = as_dict(art.get("producer"))
        tool = producer.get("tool")
        if self.tools is not None and isinstance(tool, str) and tool not in self.tools:
            self.add(
                rel, "FR-001-29", f"{base}/producer/tool", f"artefact {aid}: producer tool {tool} is not a registry id"
            )
        if kind == "run" and published:
            stage_key = as_dict(producer.get("stage"))
            for stage in stages:
                if as_dict(stage.get("key")) == stage_key and stage.get("status") != "succeeded":
                    self.add(
                        rel,
                        "FR-001-16",
                        base,
                        f"artefact {aid}: its stage {stage_key.get('id')} has status {stage.get('status')}",
                    )
        known: list[tuple[str, str, str | None]] = []
        for position, item in enumerate(as_list(art.get("inputs"))):
            item = as_dict(item)
            iid = item.get("id")
            if not isinstance(iid, str):
                continue
            pointer = f"{base}/inputs/{position}"
            if iid in by_id and item.get("kind") != "source":
                other = by_id[iid]
                known.append((iid, str(other.get("licence_class")), other.get("spdx")))
            elif self.sources is not None and iid in self.sources:
                src = self.sources[iid]
                known.append((iid, str(src.get("licence_class")), src.get("spdx")))
                self.check_pinned(rel, pointer, aid, iid, src, published)
            elif (
                item.get("kind") != "knowledge"
                and not (kind == "web-index" and item.get("kind") == "artefact")
                and self.sources is not None
            ):
                self.add(
                    rel,
                    "FR-001-33",
                    f"{pointer}/id",
                    f"artefact {aid}: input {iid} is neither a source nor an artefact of this run",
                )
        if published:
            valid = [k for k in known if k[1] in RANK]
            for rule, message in derivative_problems(aid, str(art.get("licence_class")), str(art.get("spdx")), valid):
                self.add(rel, rule, base, message)

    def check_stages(self, rel: str, stages: list[dict[str, Any]], by_id: dict[str, Any], published: bool) -> None:
        for index, stage in enumerate(stages):
            base = f"/stages/{index}"
            tool = stage.get("tool")
            if self.tools is not None and isinstance(tool, str):
                if tool not in self.tools:
                    self.add(rel, "FR-001-29", f"{base}/tool", f"stage tool {tool} is not a registry id")
                else:
                    env = as_dict(stage.get("env")).get("name")
                    if isinstance(env, str) and env not in as_list(as_dict(self.tools[tool]).get("envs")):
                        self.add(
                            rel,
                            "FR-001-29",
                            f"{base}/env/name",
                            f"stage environment {env} is not among the envs of tool {tool}",
                        )
            for position, item in enumerate(as_list(stage.get("inputs"))):
                item = as_dict(item)
                iid = item.get("id")
                if not isinstance(iid, str) or self.sources is None:
                    continue
                pointer = f"{base}/inputs/{position}"
                if iid in self.sources:
                    self.check_pinned(rel, pointer, f"stage {index}", iid, self.sources[iid], published)
                elif item.get("kind") != "knowledge" and iid not in by_id:
                    self.add(
                        rel,
                        "FR-001-33",
                        f"{pointer}/id",
                        f"stage {index}: input {iid} is neither a source nor an artefact of this run",
                    )

    def check_pinned(self, rel: str, pointer: str, who: str, iid: str, src: dict[str, Any], published: bool) -> None:
        if published and any(as_dict(f).get("sha256") is None for f in as_list(src.get("files"))):
            self.add(rel, "FR-001-33", pointer, f"{who}: source {iid} has a file without a pinned sha256")

    # ------------------------------------------------------------------------------------------------------------
    # served files (FR-001-20)
    # ------------------------------------------------------------------------------------------------------------
    def served_files(self, rel: str, doc: Any) -> None:
        body = as_dict(doc)
        for index, art in enumerate(as_list(body.get("artefacts"))):
            art = as_dict(art)
            host, path, aid = art.get("asset_host"), art.get("path"), str(art.get("id"))
            if not isinstance(path, str):
                continue
            if host == "git":
                self.compare_file(rel, f"/artefacts/{index}", aid, self.root / "web/public" / path, art)
            elif host == "release" and self.release_assets is not None:
                self.compare_file(rel, f"/artefacts/{index}", aid, self.release_assets / path, art)
        for index, run in enumerate(as_list(body.get("runs"))):
            run = as_dict(run)
            manifest = run.get("manifest")
            if isinstance(manifest, str):
                self.compare_file(
                    rel,
                    f"/runs/{index}",
                    str(run.get("run_id")),
                    self.root / "web/public/assets/runs" / manifest,
                    run,
                    size=False,
                )

    def compare_file(
        self, rel: str, pointer: str, name: str, path: Path, entry: dict[str, Any], size: bool = True
    ) -> None:
        if not path.is_file():
            self.add(rel, "FR-001-20", pointer, f"{name}: the served file is missing")
            return
        try:
            digest, length = sha256_of(path)
        except OSError:
            self.add(rel, "FR-001-20", pointer, f"{name}: the served file cannot be read")
            return
        if digest != entry.get("sha256"):
            self.add(rel, "FR-001-20", pointer, f"{name}: sha256 of the served file differs from the index entry")
        if size and length != entry.get("bytes"):
            self.add(
                rel, "FR-001-20", pointer, f"{name}: bytes of the served file ({length}) differ from the index entry"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check every committed contract document against its schema.")
    parser.add_argument("--root", type=Path, default=REPO, help="repository tree to check (default: this repository)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print the findings as a JSON list")
    parser.add_argument("--release-assets", type=Path, help="folder with the downloaded release assets (FR-001-20)")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"usage error: --root {args.root.name} is not a directory", file=sys.stderr)
        return 2
    if args.release_assets is not None and not args.release_assets.is_dir():
        print("usage error: --release-assets is not a directory", file=sys.stderr)
        return 2
    try:
        findings = Checker(args.root, args.release_assets).run()
    except Exception as exc:
        print(f"contract check failed to run: {type(exc).__name__}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps([f.as_dict() for f in findings], indent=2, ensure_ascii=False))
    elif findings:
        for f in findings:
            print(f"{f.file}: {f.pointer or '/'}: {f.rule}: {f.message}")
        print(f"CONTRACT CHECK FAIL ({len(findings)} findings)")
    else:
        print("CONTRACT CHECK OK")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
