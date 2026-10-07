# Console

> A local web console for the studio: a FastAPI app bound to 127.0.0.1 that lists recipes, queues validated jobs and
> streams live telemetry, never deployed and never contacted by the public site unless the visitor asks. · Part of:
> [Studio](README.md) · Related: [Runner](runner.md) · [Access gate](../web/access-gate.md) ·
> [Deployment](../architecture/deployment.md) · [DEC-0003](../architecture/decisions/DEC-0003-loopback-console.md)

## What and why

The runner has a command line that always works, over SSH too. The console adds what a terminal cannot show: renders,
videos, point clouds and live GPU timelines next to the job that produced them, using the same viewers as the public
site. It is the studio's own window, not a backend of the website.

Why a loopback FastAPI console ([DEC-0003](../architecture/decisions/DEC-0003-loopback-console.md)):

| Alternative | Why not |
|---|---|
| A Kit extension panel | runs only inside the Kit process: it cannot supervise the Python 3.14 lanes and dies when Kit crashes |
| A Textual terminal UI | cannot show images, videos or point clouds [1] |
| Rerun as the console | an artefact viewer, not a job console; its web viewer is about 51.6 MB unpacked and couples to the exact SDK version [2][3] |

**Status: planned.** The `api/` folder is a placeholder today; FastAPI 0.142.2 and uvicorn 0.54.0 are already locked as
the root project's `api` extra.

## Design

| Element | Rule |
|---|---|
| Bind address | **127.0.0.1 only**; never `0.0.0.0` |
| Port | read from the environment, never hard-coded ([Configuration](../reference/configuration.md)) |
| Health | `GET /health` |
| Read endpoints | recipes, queue, runs, manifests, artefact streaming |
| Live stream | Server-Sent Events of `events.jsonl` and 1 Hz telemetry |
| Write endpoint | `POST /jobs`, validated against `contracts/recipe.schema.json` |
| UI | a separate web entry that reuses the site shell (theme, i18n, charts, artefact viewers), **excluded from the Pages build** |

**Server-Sent Events** are native in FastAPI since 0.135.0 through `EventSourceResponse`, with keep-alive pings every
15 s and `Cache-Control: no-cache` [4]. That is enough for job events and 1 Hz telemetry without WebSockets.

**Hostile input returns 4xx.** `POST /jobs` accepts only a body that validates against the recipe schema and refers to
a known recipe and stage; anything else — malformed JSON, unknown fields, wrong types, oversized bodies, path tricks in
ids — is rejected with a 4xx status, never a 500 and never a hang. Property-based API tests (Schemathesis, generated
from the OpenAPI schema) enforce it, and a contract test checks every endpoint against the shared schemas.

## The public-site boundary

- **The console is never part of the Pages site.** It is a separate build target; a CI check fails if any console
  chunk appears in the deployed artefact.
- **The public site never probes localhost on its own.** Chrome's Local Network Access applies to "Any request from the
  public network to a local network or loopback destination", including `127.0.0.0/8` and `::1`, and asks the user for
  permission [5]. A site that silently fetched `http://localhost:<port>/health` would prompt every visitor.
- **An opt-in "connect to my local studio" button** may make that request after an explicit click; declining changes
  nothing. The console itself is served from localhost (same origin), so it never triggers the prompt.
- **Kit's WebRTC "studio link"** (a live RTX viewport streamed to a browser) stays a separate, optional localhost tool.
  The console may link to it; the public build never embeds it ([Composer / Explorer](../frameworks/kit-usd-composer-explorer.md)).

## Using it remotely

On a Linux GPU host the console stays bound to loopback; it is reached through SSH port forwarding, the same way as the
command line ([Scaling to Linux](scaling-to-linux.md)).

```bash
# illustrative: the console's module name and entry point are fixed when it is built
uv run --extra api python -m <console-module>
```

The [CLI reference](../reference/cli.md) records the final form.

## Assumptions and limits

- The console adds no capability the runner lacks: every action it offers is a runner command.
- It is a single-user local tool with no authentication; loopback binding is its security boundary.
- Media shown in the console is read from the store; nothing is copied into the web build.

## In PitStudio

- Status: **planned**; built test-first with the runner (contract tests and Schemathesis) in the build phase.
- What it reads: run manifests, events and telemetry described on [Runner](runner.md) and [Manifest](../data-contract/manifest.md).

## References

1. Python Package Index. *textual* 8.2.8. https://pypi.org/pypi/textual/json
2. npm. *@rerun-io/web-viewer* (unpacked size). https://registry.npmjs.org/@rerun-io/web-viewer/latest
3. Rerun. *Embed a web viewer* (exact version coupling). https://rerun.io/docs/howto/integrations/embed-web
4. FastAPI. *Server-Sent Events*. https://fastapi.tiangolo.com/tutorial/server-sent-events/
5. Google Chrome for Developers. *Local Network Access*. https://developer.chrome.com/blog/local-network-access
