# Deployment

> Where each part of PitStudio runs: a static site on GitHub Pages, large assets kept as GitHub Release assets and
> copied into the site at build time, a local studio that is never deployed and never runs in CI, and a documented
> path to a Linux GPU host. · Part of: [architecture](README.md) · Related: [C4 containers](c4-containers.md) ·
> [lanes](lanes.md) · [budgets](../web/budgets.md) · [release and cite](../guides/release-and-cite.md)

## What and why

PitStudio's two halves have opposite deployment needs. The web app must be public, free to host, fast on a first
visit and reproducible from the repository. The studio needs an RTX GPU, proprietary runtimes and owner-accepted
licences, so it cannot be hosted publicly or run in CI at all. The deployment design keeps them apart and connects
them only through committed or released files with checksums.

![Deployment: workstation, GitHub and browser](../assets/diagrams/deployment-pages.svg)

*The workstation bakes runs with `studio publish`; small files go to git and large ones to draft release assets;
`pages.yml` builds, tests and deploys the static site, copying release assets by tag after checking their SHA-256.*

## Deployment nodes

| Node | What runs there | Controlled by | Never |
|---|---|---|---|
| Maintainer's workstation | Studio and pipeline environments, the runner, the store (`PITSTUDIO_STORE`), the loopback console, NVIDIA runtimes | The maintainer | Exposed to a network; its paths or host name written into a manifest |
| GitHub repository | Code, docs, specs, contracts, baked web files < 10 MB (≤ 100 MB in total) | Pull requests to `main` | Binaries, engines, caches, NVIDIA assets, gated weights, raw third-party data |
| GitHub release assets | Large baked files (videos, splats, models > 10 MB, archives of small-file classes beyond the git cap) under `assets-vX.YY.ZZZ` tags | The maintainer, through draft releases | Fetched by the visitor's browser |
| GitHub Actions | CI on ubuntu runners (CPU only); `pages.yml` build and deploy | Workflow files with actions pinned to commit SHAs | Any studio stage, any GPU job, any studio credential |
| GitHub Pages | The static site at `https://fsantibanezleal.github.io/PitStudio/` | `pages.yml` | A backend; console code |
| Visitor's browser | Prerendered pages, live engines on T1/T2/T0, replays | The visitor | Automatic contact with a local studio |

## GitHub Pages: the static site

**How the site is built today.** `.github/workflows/pages.yml` runs on every push to `main` and on manual dispatch. Its
build job checks out the repository, installs pnpm (version from `packageManager`) and Node (version from `web/.nvmrc`,
Node 24), gets the base path from `actions/configure-pages`, runs `pnpm install --frozen-lockfile`, `pnpm run check`
(Biome, route typegen, TypeScript, Vitest) and `pnpm run build` with `BASE_PATH=/PitStudio/`, then runs the Playwright
end-to-end suite against the production build and uploads `web/build/client` as the Pages artifact. A deploy job
publishes it with `actions/deploy-pages`, and a smoke job runs the live tests against the deployed URL in Chromium,
Firefox and WebKit. Every action is pinned to a full commit SHA.

**What the build produces.** React Router runs in framework mode with `ssr: false` and prerenders every static route to
HTML, so deep links return 200 on Pages. `web/scripts/postbuild.mjs` moves the prerendered tree to the artifact root,
turns the SPA fallback into `404.html`, and fails the build if the start page loads more than 200 KB of gzip
JavaScript. The demo access gate receives its phrase from a repository secret; only the SHA-256 digest reaches the
bundle, and the gate states on screen that it is not a security boundary.

The production build, served the way Pages serves it, runs today (`scripts/run_web.sh` / `scripts/run_web.ps1` wrap
the same steps). In Git Bash on Windows, `MSYS2_ENV_CONV_EXCL=BASE_PATH` stops the shell from rewriting `/PitStudio/` into a
Windows path; elsewhere it is harmless:

```bash run
cd web
pnpm install --frozen-lockfile
MSYS2_ENV_CONV_EXCL=BASE_PATH BASE_PATH=/PitStudio/ pnpm build
MSYS2_ENV_CONV_EXCL=BASE_PATH BASE_PATH=/PitStudio/ pnpm serve
```

**Hosting limits.** Pages sites are limited to 1 GB, deploys to 10 minutes, bandwidth to a soft 100 GB per month and
builds to 10 per hour [1]. PitStudio caps its whole site at 500 MB, well inside the 1 GB limit.

## Large assets: release assets copied at build

Git is a poor home for large binary files: GitHub warns above 50 MiB and blocks files above 100 MiB [2], every
re-baked asset would grow the history forever, and Git LFS cannot be used with GitHub Pages sites [3]. PitStudio
therefore splits baked assets by size ([DEC-0007](decisions/DEC-0007-large-assets-as-release-assets.md)):

- **In git:** files < 10 MB, at most 100 MB of baked assets in total. `tools/check_repo.py` already fails CI on any
  tracked file above 10 MB.
- **As release assets:** everything larger (videos, splats, models above 10 MB). Small-file classes that would exceed the
  in-git total (for example, terrain tiles or replay shards) ship as release-asset archives that the build unpacks. A
  release asset may be up to 2 GiB, a release may hold up to 1,000 assets, and GitHub sets no limit on the total size of
  a release or its bandwidth [4].
- **Same-origin only.** `pages.yml` downloads the release assets by tag, checks every SHA-256 against the manifest and
  copies them into the Pages artifact. The browser never fetches a release asset; every request the site makes goes to
  its own origin.
- **Alternative for > 2 GiB.** A Hugging Face Hub repository under the maintainer's account, used only if a single
  asset exceeds the release-asset limit.

**Asset release flow** (compatible with immutable releases): create an `assets-vX.YY.ZZZ` release as a draft, upload,
verify every SHA-256 against the manifest, then publish it with `--latest=false`. Every re-bake gets a new tag. The
product release `vX.YY.ZZZ`, cut by `tools/release.py`, stays "Latest". The commands below are illustrative; the
upload list comes from `studio publish`, which arrives in the build phase.

```bash
gh release create assets-v0.01.000 --draft --title "assets-v0.01.000" --notes "Baked web assets"
gh release upload assets-v0.01.000 <files from the release upload list>
# verify every SHA-256 against the manifest, then:
gh release edit assets-v0.01.000 --draft=false --latest=false
```

**History policy.** Heavy assets are re-baked only at releases. CI checks every file size, the in-git total and the
repository size.

**Status.** The copy step in `pages.yml` is planned: it is added together with the first asset release, in the build
phase. Today's `pages.yml` deploys the web shell without release assets.

## Budgets

The site total is an exact sum, enforced in CI ([budgets](../web/budgets.md)):

| Item | Budget |
|---|---|
| Initial JavaScript | ≤ 200 KB gzip |
| First view | ≤ 2 MB |
| Videos | ≤ 150 MB (six AV1 + H.264 pairs, ≤ 25 MB each) |
| Tiles and glb | ≤ 95 MB |
| Replay shards and point clouds | ≤ 60 MB |
| Splats | ≤ 25 MB (one scene) |
| ONNX models | ≤ 80 MB (each live model ≤ 25 MB; precompute-only models are not shipped) |
| Runtimes (ORT-web, Pyodide, wheels, Rapier), self-hosted and loaded on user action | ≤ 55 MB |
| Own JavaScript, WASM and fonts | ≤ 10 MB |
| Studio showcase | ≤ 25 MB |
| **Site total** | **= 500 MB** |

## The local studio: never deployed, never in CI

The studio runs only on the maintainer's workstation. Its reference configuration is an RTX 5000 Ada Generation Laptop
GPU (16 GB) on driver 582.78 with Windows 11; manifests record the GPU model, driver and power limit, never a host name,
user name or path.

- **Environments** are created with `uv sync` per project and entered only through `uv run --project <env> --frozen`
  ([studio environments](../studio/environments.md)).
- **The console** binds to 127.0.0.1 only. The optional Kit WebRTC "studio link" is a separate localhost tool. Both are
  excluded from the Pages artifact by build target, and CI checks that no console chunk appears in the build output.
- **The public site** never contacts the studio on its own; an opt-in "connect to my local studio" button may.
- **Owner acts** (NVIDIA terms, the kit-app-template licence prompt, gated model terms, elevated Nsight captures, a
  newer driver only if a compatibility check fails) are listed with their fallbacks in
  [owner acts and licences](../studio/owner-acts-and-licences.md).

**What CI runs and never runs.** CI runs the open, CPU-capable subset: lint, type checks, the core tests without the
`gpu` marker, traceability, test-first replay, the repository and documentation checks, a pipeline smoke on CPU with
samples, the web build and its end-to-end tests. In the build phase it gains scene authoring, USD validation, Warp CPU
kernels, the runner's unit tests against a fake GPU backend and the console's contract tests. CI never installs an
NVIDIA runtime, never runs a GPU stage and never needs a studio credential.

## Scaling target: a Linux GPU host

Nothing in the studio is laptop-specific except a machine profile (`studio/recipes/_profiles/laptop-rtx5000ada.yaml`
versus `linux-gpu.yaml`). On a Linux GPU host:

- the open lanes run from `studio/containers/Dockerfile.open`, built with uv's documented container pattern from the same
  lock files [5]; CI builds this image and runs the CPU test subset inside it;
- the Isaac Sim lane is built `FROM nvcr.io/nvidia/isaac-sim:6.1.0` on that host only and never pushed to a public
  registry [6];
- multi-GPU training is possible there only, because Isaac Lab supports multi-GPU and multi-node training on Linux only
  [7].

Kubernetes, Ray, workflow servers and multi-node training are out of scope. See
[scaling to Linux](../studio/scaling-to-linux.md).

## Assumptions and limits

- GitHub's limits are quoted as documented in October 2026 and can change; CI enforces PitStudio's own, tighter budgets.
- A visitor on a slow connection still downloads large replays; they load only after an explicit action, with progress
  and abort.
- The studio's reference machine is a single laptop; its results describe that machine's power-limited envelope, and
  every benchmark says "our hardware, not a comparative benchmark".

## In PitStudio

- Release procedure and citation: [release and cite](../guides/release-and-cite.md).
- First run on a clone: [quickstart](../guides/quickstart.md).
- Status: the Pages deployment of the web shell is live; the release-asset copy, `studio publish`, the console exclusion
  check and the container build arrive in the build phase.

## References

1. GitHub Docs. GitHub Pages limits. https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
2. GitHub Docs. About large files on GitHub.
   https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
3. GitHub Docs. About Git Large File Storage ("Git LFS cannot be used with GitHub Pages sites").
   https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage
4. GitHub Docs. About releases. https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
5. Astral. Using uv in Docker. https://docs.astral.sh/uv/guides/integration/docker/
6. NVIDIA. Isaac Sim container installation. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html
7. Isaac Lab. Multi-GPU and multi-node training. https://isaac-sim.github.io/IsaacLab/main/source/features/multi_gpu.html
