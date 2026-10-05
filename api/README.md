# api/

**Status: planned (milestone M3).** The loopback **studio console**: a FastAPI app bound to `127.0.0.1` (port from the
environment) with `/health`, recipes, the job queue, runs, artefacts and server-sent telemetry events. `POST /jobs` is
validated against `contracts/recipe.schema.json`, so hostile input gets a 4xx. Its dependencies are already locked in
the root project's `api` extra (`uv sync --extra api`).

The public site never depends on it and never contacts it on its own; an opt-in "connect to my local studio" control
may. See `docs/studio/console.md`.
