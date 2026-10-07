# DEC-0003: A loopback-only studio console

> The studio is operated through a FastAPI console bound to 127.0.0.1 with its own web entry that reuses the site's
> shell; it is excluded from the Pages build, the public site never contacts it unless the visitor opts in, and the CLI
> always works without it. · Part of: [decisions](README.md) · Related: [console](../../studio/console.md) ·
> [C4 containers](../c4-containers.md) · [DEC-0002](DEC-0002-in-repo-runner.md)

**Status:** Accepted, 2026-10-04

## Context

Studio outputs are mostly media: renders, videos, point clouds, telemetry charts. The maintainer needs to queue recipes,
watch runs and inspect artefacts. The console must survive a crash of any one tool (Kit in particular), must never
become a dependency of the public site, and must not expose the workstation to a network.

Three facts shaped the choice. FastAPI has native server-sent events since version 0.135.0, enough to stream job events
and telemetry to a browser without WebSockets [1]. A text console such as Textual cannot show images, videos or point
clouds inline [2]. And browsers now ask the user for permission when a page from the public internet contacts a
loopback or local-network address (Chrome's Local Network Access) [3], so a public site that silently probed
`localhost` would prompt every visitor.

## Decision

- **API.** FastAPI in `api/`, bound to **127.0.0.1 only**, port from an environment variable, with `/health`. Endpoints
  cover recipes, the queue, runs, manifests, artefact streaming and an SSE stream of events and telemetry. `POST /jobs`
  is validated against the recipe schema, so hostile input gets a 4xx; Schemathesis tests the contract.
- **UI.** A separate web entry, `web/console/`, that reuses the site's shell (theme, i18n, the same artefact viewers). It
  is excluded from the Pages artifact by build target, and CI checks that no console chunk appears in the build output.
- **Public-site boundary.** The site never probes localhost on its own. An optional "connect to my local studio" button
  performs the probe only after a click; declining changes nothing.
- **CLI first.** The `studio` CLI always works without the console; on a Linux host the console is reached through SSH
  port forwarding.
- **Studio link.** The optional Kit WebRTC viewer stays a separate localhost tool under `studio/kit/`; the console may
  link to it, never embed it in the public build.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| A Kit extension panel as the console | No extra web code; lives next to the viewport | Runs only inside the Python 3.12 Kit process; dies with Kit; cannot supervise the 3.14 lanes | Not robust; at most an optional status overlay inside Isaac Sim |
| A Textual terminal UI | Works over SSH | No inline images, video or point clouds [2] | Kept as an option only if SSH-only use becomes daily |
| A local timeline viewer (Rerun) as the console | Good multimodal timelines | An artefact viewer, not a job controller; its web viewer is large and version-coupled | Assessed as a viewer, not as the console |
| Console inside the public site | One app | Would put localhost logic and studio code into the public bundle; triggers local-network prompts | Violates the static-site and privacy goals |

## Consequences

**Positive.** Media-rich operation of the studio; no network exposure; the public site stays static and prompt-free;
shared components between console and site.

**Negative, accepted.** A second web entry and a small API to maintain; a CI check for the build boundary.

**Watch.** Browser local-network-access rules as they spread beyond Chrome; FastAPI SSE behaviour under long runs.

## References

1. FastAPI. Server-sent events. https://fastapi.tiangolo.com/tutorial/server-sent-events/
2. Textual on PyPI (8.2.8). https://pypi.org/pypi/textual/json
3. Chrome for Developers. Local Network Access. https://developer.chrome.com/blog/local-network-access
