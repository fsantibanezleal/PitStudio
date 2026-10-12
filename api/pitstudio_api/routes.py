"""The console's endpoints (plan.md D1, D2): every handler is one read of the store or one runner call."""

# ruff: noqa: E501

from __future__ import annotations

import json
import mimetypes
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi import Path as FPath
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

from pitstudio.contracts._generated.console import Health, Job, JobCreated, JobList, Problem, RecipeList, RunList
from pitstudio.runner import __version__ as runner_version
from pitstudio.runner.recipe import ROOT, Usage, first_errors, kstr, load_profile, repo_root, strict_json
from pitstudio_api import __version__ as console_version
from pitstudio_api import sse, store
from pitstudio_api.problem import line, problem

LIMIT = 65536
ID = {"slug": r"^[a-z0-9][a-z0-9-]{0,63}$", "run": r"^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$", "job": r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$", "art": r"^[a-z0-9][a-z0-9_-]{0,95}$"}  # fmt: skip
RecipeId = Annotated[str, FPath(pattern=ID["slug"], max_length=64)]
RunId = Annotated[str, FPath(pattern=ID["run"], max_length=64)]
JobId = Annotated[str, FPath(pattern=ID["job"], max_length=25)]
ArtId = Annotated[str, FPath(pattern=ID["art"], max_length=96)]
JOB_INVALID = "https://fsantibanezleal.github.io/PitStudio/problems/job-record-invalid"
router = APIRouter()


def errs(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Documented error responses: every one is a `problem` body."""
    return {c: {"model": Problem, "description": f"problem, status {c}"} for c in codes}


def ok(model: type, description: str = "success") -> dict[int | str, dict[str, Any]]:
    return {200: {"model": model, "description": description}}


def doc(description: str) -> dict[int | str, dict[str, Any]]:
    return {200: {"description": description, "content": {"application/json": {"schema": {"type": "object"}}}}}


def unavailable(e: store.StoreUnavailable) -> Response:
    return problem(503, str(e), headers={"Retry-After": "5"})


def invalid_job(job_id: str) -> Response:
    return problem(
        500, f"job record {job_id} is invalid and is not served", title="Job record invalid", kind=JOB_INVALID
    )


@router.get("/health", responses=ok(Health, "the only body readable from the public site") | errs(400))
def health() -> Response:
    contracts = {
        p.name.removesuffix(".schema.json"): json.loads(p.read_text(encoding="utf-8"))["$id"]
        for p in sorted((ROOT / "contracts").glob("*.schema.json"))
    }
    return JSONResponse(
        {"status": "ok", "console_version": console_version, "runner_version": runner_version, "contracts": contracts}
    )


@router.get("/recipes", responses=ok(RecipeList) | errs(400))
def recipes() -> Response:
    repo = repo_root()
    return JSONResponse({"recipes": [store.recipe_summary(repo, p) for p in store.recipe_files(repo)]})


@router.get("/recipes/{recipe_id}", responses=doc("the validated recipe") | errs(404, 422))
def recipe(recipe_id: RecipeId) -> Response:
    repo = repo_root()
    path = store.find_recipe_file(repo, recipe_id)
    if path is None:
        return problem(404, f"no recipe {recipe_id}")
    parsed, errors = store.recipe_view(repo, path)
    return JSONResponse(parsed) if parsed else problem(422, f"recipe {recipe_id} is invalid", errors=errors)


@router.get("/queue", responses=ok(JobList) | errs(500, 503))
def queue_list() -> Response:
    try:
        jobs = [store.check_job(j) for j in store.ask_queue("jobs")]
    except store.StoreUnavailable as e:
        return unavailable(e)
    except ValueError as e:
        return invalid_job(e.args[0])
    return JSONResponse({"jobs": jobs})


def find_job(job_id: str) -> dict | None:
    try:
        rec = store.ask_queue("job", job_id)
    except KeyError:
        return None
    return store.check_job(rec) if rec else None


@router.get("/jobs/{job_id}", responses=ok(Job) | errs(404, 422, 500, 503))
def job(job_id: JobId) -> Response:
    try:
        rec = find_job(job_id)
    except store.StoreUnavailable as e:
        return unavailable(e)
    except ValueError:
        return invalid_job(job_id)
    return JSONResponse(rec) if rec else problem(404, f"no job {job_id}")


@router.post("/jobs", status_code=202, responses={202: {"model": JobCreated, "description": "accepted"}} | errs(400, 403, 413, 415, 422, 503),
             openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/JobRequest"}}}}})  # fmt: skip
async def create_job(request: Request) -> Response:
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return problem(415, "the content type must be application/json")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > LIMIT:
        return problem(413, f"the body is larger than {LIMIT} bytes")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > LIMIT:
            return problem(413, f"the body is larger than {LIMIT} bytes")
    try:
        req = strict_json(body.decode("utf-8"))
    except ValueError, RecursionError:
        return problem(400, "the body is not valid JSON (no NaN, duplicate keys, byte-order mark or invalid UTF-8)")
    if errors := first_errors("recipe", req, "#/$defs/job_request", n=20):
        return problem(
            422,
            "the job request does not match the contract",
            errors=[
                {
                    "pointer": e.split(": ", 1)[0],
                    "keyword": "schema",
                    "message": line(e.split(": ", 1)[1], 300) or "invalid",
                }
                for e in errors
            ],
        )
    repo = repo_root()
    path = store.find_recipe_file(repo, req["recipe"])
    parsed = store.recipe_view(repo, path)[0] if path else None
    if parsed is None:
        return problem(422, f"recipe {line(req['recipe'], 64)} is unknown or invalid")
    if bad := [k for k in (kstr(s) for s in req.get("stages", [])) if k not in {kstr(s) for s in parsed["stages"]}]:
        return problem(422, f"stage {line(bad[0], 64)} is not in recipe {req['recipe']}")
    try:
        load_profile(repo, req["profile"])
    except Usage:
        return problem(422, f"profile {line(req['profile'], 64)} is unknown or invalid")
    try:
        job_id = store.ask_queue("enqueue", req)
    except store.StoreUnavailable as e:
        return unavailable(e)
    return JSONResponse({"job_id": job_id, "location": f"/jobs/{job_id}"}, 202, {"Location": f"/jobs/{job_id}"})


@router.post(
    "/jobs/{job_id}/cancel",
    status_code=202,
    responses={202: {"model": Job, "description": "the job"}} | errs(403, 404, 409, 422, 500, 503),
)
def cancel_job(job_id: JobId) -> Response:
    try:
        rec = find_job(job_id)
        if rec is None:
            return problem(404, f"no job {job_id}")
        if rec["state"] not in ("queued", "running"):
            return problem(409, f"job {job_id} is {rec['state']} and cannot be cancelled")
        store.ask_queue("cancel", job_id)
        return JSONResponse(find_job(job_id), 202)
    except store.StoreUnavailable as e:
        return unavailable(e)
    except ValueError, Usage:
        return problem(409, f"job {job_id} cannot be cancelled")


@router.get("/runs", responses=ok(RunList) | errs(503))
def runs() -> Response:
    try:
        root = store.store_dir()
        ids = store.run_ids(root)
    except (store.StoreUnavailable, OSError) as e:
        return unavailable(
            e if isinstance(e, store.StoreUnavailable) else store.StoreUnavailable("the runs folder is unreadable")
        )
    try:
        states = {j["run_id"]: j["state"] for j in store.ask_queue("jobs") if j["run_id"]}
    except store.StoreUnavailable:
        states = {}
    rows = []
    for rid in ids:
        m, _ = store.read_manifest(root, rid)
        rows.append({"run_id": rid, "recipe": m["recipe"]["id"] if m else None, "created": m["created"] if m else None, "profile": m["profile"] if m else None,
                     "state": states.get(rid), "stages": len(m["stages"]) if m else 0, "published": bool(m and m["published"]), "valid": m is not None})  # fmt: skip
    return JSONResponse({"runs": rows})


@router.get("/runs/{run_id}", responses=doc("the validated run manifest") | errs(404, 409, 422, 503))
def run(run_id: RunId) -> Response:
    try:
        m, why = store.read_manifest(store.store_dir(), run_id)
    except store.StoreUnavailable as e:
        return unavailable(e)
    except FileNotFoundError:
        return problem(404, f"no run {run_id}")
    return JSONResponse(m) if m else problem(409, why)


def byte_range(header: str | None, total: int) -> tuple[int, int] | str | None:
    """(first, last) of a single satisfiable `bytes=` range, "unsatisfiable", or None to serve the whole object (RFC 9110, 14.1)."""
    m = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", header or "")
    if not m or not (m.group(1) or m.group(2)):
        return None
    start, end = m.group(1), m.group(2)
    if not start:  # a suffix range: the last n bytes
        return "unsatisfiable" if int(end) == 0 else (max(0, total - int(end)), total - 1)
    if int(start) >= total:
        return "unsatisfiable"
    if end and int(end) < int(start):
        return None
    return int(start), min(int(end), total - 1) if end else total - 1


class Chunked(StreamingResponse):
    """Sends the chunks in turn without waiting for the peer to speak first, so a client that has already sent its whole request cannot cut the body short."""

    async def __call__(self, scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers})
        async for data in self.body_iterator:
            await send({"type": "http.response.body", "body": data, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})


def chunks(path: Path, first: int, last: int) -> Iterator[bytes]:
    with open(path, "rb") as fh:
        fh.seek(first)
        left = last - first + 1
        while left > 0 and (data := fh.read(min(65536, left))):
            left -= len(data)
            yield data


@router.get("/runs/{run_id}/artefacts/{artefact_id}", responses={200: {"description": "the bytes", "content": {"*/*": {"schema": {"type": "string", "format": "binary"}}}},
            206: {"description": "partial content", "content": {"*/*": {"schema": {"type": "string", "format": "binary"}}}}} | errs(404, 409, 416, 422, 503))  # fmt: skip
def artefact(run_id: RunId, artefact_id: ArtId, request: Request) -> Response:
    try:
        root = store.store_dir()
        m, why = store.read_manifest(root, run_id)
    except store.StoreUnavailable as e:
        return unavailable(e)
    except FileNotFoundError:
        return problem(404, f"no run {run_id}")
    rec = next((a for a in (m or {}).get("artefacts", []) if a["id"] == artefact_id), None)
    path = store.artefact_file(root, rec["sha256"]) if rec else None
    if m is None or path is None:
        return problem(404 if m else 409, f"no artefact {artefact_id} in run {run_id}" if m else why)
    total = os.path.getsize(path)
    rng = byte_range(request.headers.get("range"), total)
    kind = rec.get("media_type") or "application/octet-stream"
    base = {
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600, immutable",
    }
    if rng == "unsatisfiable":
        return problem(
            416, f"the range cannot be satisfied for {total} bytes", headers={"Content-Range": f"bytes */{total}"}
        )
    first, last = rng if rng else (0, total - 1)
    headers = {
        **base,
        "Content-Length": str(last - first + 1),
        **({"Content-Range": f"bytes {first}-{last}/{total}"} if rng else {}),
    }
    return Chunked(chunks(path, first, last), 206 if rng else 200, headers, media_type=kind)


@router.get(
    "/runs/{run_id}/events",
    responses={
        200: {"description": "server-sent events", "content": {"text/event-stream": {"schema": {"type": "string"}}}}
    }
    | errs(404, 422, 429, 503),
)
def events(run_id: RunId, request: Request) -> Response:
    try:
        after = sse.parse_last_event_id(request.headers.get("last-event-id"))
    except ValueError as e:
        return problem(422, str(e))
    try:
        run_dir = store.store_dir() / "runs" / run_id
    except store.StoreUnavailable as e:
        return unavailable(e)
    if not run_dir.is_dir():
        return problem(404, f"no run {run_id}")
    return sse.open_stream(run_dir, after) or problem(
        429, "8 event streams are already open", headers={"Retry-After": "5"}
    )


@router.get("/ui", include_in_schema=False)
def ui_root() -> Response:
    return RedirectResponse("/ui/")


@router.get("/ui/{path:path}", include_in_schema=False)
def ui(path: str) -> Response:
    root = os.path.realpath(repo_root() / "web" / "build" / "console")
    target = os.path.realpath(os.path.join(root, path or "index.html"))
    if not target.startswith(root + os.sep) or not os.path.isfile(target):
        return problem(404, "no such console file (is the UI built? run pnpm build:console)")
    return FileResponse(
        target,
        media_type=mimetypes.guess_type(target)[0] or "application/octet-stream",
        headers={"Cache-Control": "no-cache"},
    )
