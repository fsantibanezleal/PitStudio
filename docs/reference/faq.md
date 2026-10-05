# FAQ

> Short answers to the questions people ask first about PitStudio: what it is and is not, what runs where, what it
> publishes, licences, hardware and how claims are judged. · Part of: [Reference](README.md) · Related:
> [docs home](../README.md) · [showcase rules](../web/showcase-rules.md) · [glossary](glossary.md)

## What and why

These answers point to the page that explains each topic in full. They describe the project as specified; most of it
is built in the build phase, and nothing has been trained or rendered yet.

## About the project

**What is PitStudio?**
An open, reproducible physical-AI simulation studio for open-pit mining: a local GPU studio (OpenUSD scenes, GPU
physics, RTX sensors, synthetic data, robot learning, a vision-language model, training, acceleration, video, GPU
telemetry), a static web app that explains, runs and showcases it through 12 cases, a knowledge base (these docs plus
the `minephys` library), and recipes that also run on a Linux GPU host. See the [docs home](../README.md).

**Is it a digital twin of a real mine?**
No. It is a **simulation-grade twin**: scenes are built from public terrain (USGS 3DEP Bingham Canyon and others) and
models from the literature, and nothing is synchronised with a live operation. There is no telemetry feed.

**Can I use its slope, tailings or blasting results to design something?**
No. They are **educational, not design or regulatory** outputs. Each case page states the validity range of its models
(for example the range of vehicle weights for which the AP-42 road-dust equation was fitted).

**Is it affiliated with NVIDIA?**
No. NVIDIA, Omniverse, Isaac, Cosmos, TensorRT and other names are used nominatively to say which tools were used.
PitStudio is not affiliated with or endorsed by NVIDIA or any mining company.

## What runs where

**Do I need an NVIDIA GPU to use the site?**
No. The site runs in any modern browser. With WebGPU it computes the most (tier T1); without it, engines run in
WebAssembly (T2); if those fail, precomputed results are shown (T0). The active tier is always visible
([compute tiers](../web/compute-tiers.md)).

**Do I need one to run the code?**
Not for the core, the tests, the web app or the analytical models ([quickstart](../guides/quickstart.md)). GPU physics
needs a CUDA GPU; Isaac Sim, Replicator, ovrtx and Kit need an RTX GPU and acceptance of NVIDIA's terms
([set up the studio](../guides/set-up-the-studio.md)).

**Why Windows-native and not WSL2 or Docker?**
The reference machine is a Windows laptop. The Isaac Sim container is Linux-only and RTX rendering is not a working
path in WSL2, so the studio runs natively on Windows; the same recipes run in containers on a Linux GPU host
([scaling to Linux](../studio/scaling-to-linux.md)).

**Why two Python versions?**
NVIDIA's runtimes (Isaac Sim, Kit, ovrtx, Isaac Lab) require Python 3.12; the open stack (Warp, Newton, usd-core,
PyTorch) and the core run on 3.14. Each toolchain gets its own locked environment, and they exchange files only
([environments](../studio/environments.md)).

**Why is the site static, with no server?**
GitHub Pages is free, durable and needs no operations. The trade-off is a byte budget (500 MB) and no secrets, which
is why heavy work is precomputed and the access gate is not security ([budgets](../web/budgets.md),
[access gate](../web/access-gate.md)).

**Does the site talk to my computer?**
Never on its own. The local studio console runs on `127.0.0.1` and is a separate app; the public site probes it only
if you press "connect to my local studio" ([user flow](../web/user-flow.md)).

## What is published

**Why do I see "not yet run"?**
Because nothing has been run for that tool or result yet. PitStudio never shows a placeholder result or a stock image;
a tool with no artefact says "not yet run", and a tool that was tried and dropped says "evaluated, not adopted" with
the reason ([showcase rules](../web/showcase-rules.md)).

**Why are there no Isaac Sim or Replicator speed numbers?**
The NVIDIA Software License Agreement forbids publishing performance data of that software without permission (§8.9),
and TensorRT for RTX has the same restriction (§2.13). Those numbers stay on the machine; the site shows the outputs
and says "measured locally, not published (licence)". Regular TensorRT numbers for PitStudio's own models are published,
because the reviewed TensorRT licence has no such clause.

**Does PitStudio redistribute NVIDIA software or models?**
No. NVIDIA binaries, assets, TensorRT engines, caches, template code and model weights are never committed or published.
You install them from NVIDIA's official sources.

**How do I know a "better" claim is real?**
A result is called better only when the paired 95 % confidence interval of the difference excludes zero; otherwise
the site says "no significant difference". The criteria are fixed before results exist
([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

**How far does synthetic-only training go?**
That is measured where real labelled data exist: fragmentation segmentation is trained on synthetic and on real
images and both are tested on real held-out images. For equipment and people detection there is no licence-clean real
test set, so its sim-to-real gap is reported as "not measured" unless an optional real probe is labelled.

**Where do the numbers in the docs come from?**
Every external number carries a DOI or URL. Values not yet checked against their primary page are flagged UNVERIFIED in
the knowledge tables ([knowledge](../knowledge/README.md)).

## Licences and citation

**Can I reuse the code and data?**
Code is Apache-2.0; docs, figures, PitStudio's own USD and synthetic data are CC-BY-4.0; layers derived from
share-alike sources are CC-BY-SA in separate entries; trained weights follow the most restrictive licence of their
inputs, stated in each model card. `REUSE.toml` maps every path.

**How do I cite it?**
Use "Cite this repository" on GitHub (from `CITATION.cff`) and the version shown in the site footer; cite `minephys`
and the datasets too ([release and cite](../guides/release-and-cite.md)).

## Tools and choices

**Why a small in-house runner instead of Prefect, Dagster or Snakemake?**
The studio spans several isolated Python environments on one GPU and must hold a machine-wide GPU lock with guards and
write PitStudio's own manifest. Server-based orchestrators add a service and do not span the environments without
wrappers, and Snakemake's Windows path is WSL ([DEC-0002](../architecture/decisions/DEC-0002-in-repo-runner.md)).

**Why FFmpeg 8.1 and not 9?**
FFmpeg 9 builds use NVENC SDK 13.1 headers, which require driver ≥ 610; the reference machine's driver is in the R580
branch ([encode videos](../guides/encode-videos.md)).

**Why `minephys` as a separate package?**
It is the knowledge base as code: pure NumPy models with cited parameter tables, used by the studio, the pipeline, Kit
and the browser (through Pyodide), and by other projects
([DEC-0017](../architecture/decisions/DEC-0017-companion-package-minephys.md)).

**Why GitHub Release assets for large files?**
Git should not hold large or frequently re-baked binaries, and Pages artifacts are capped at 1 GB. Release assets are
copied into the site at build, pinned by SHA-256
([DEC-0007](../architecture/decisions/DEC-0007-large-assets-as-release-assets.md)).

**Is the access gate secure?**
No, and it says so on screen. It keeps casual visitors on the landing view; everything on the site is public
([access gate](../web/access-gate.md)).

## Assumptions and limits

- Answers summarise; the linked pages are authoritative.

## In PitStudio

- Foundation spec `specs/000-foundation/spec.md` holds the requirements behind these answers (FR-000-01 to FR-000-16).

## References

1. NVIDIA, "NVIDIA Software License Agreement", §8.9. https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
2. NVIDIA, "TensorRT for RTX Software License Agreement", §2.13. https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
3. NVIDIA, "Isaac Sim 6.0 requirements" — container supported on Linux only. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html
4. Snakemake, "Installation" — Windows via WSL. https://snakemake.readthedocs.io/en/stable/getting_started/installation.html
