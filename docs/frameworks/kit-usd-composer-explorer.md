# USD Composer and USD Explorer (Kit)

> NVIDIA's Kit applications for scene review: Composer for layer, variant and look review with path-traced captures,
> Explorer for large-scene review, measurement and markup; generated locally, never committed. · Part of:
> [Frameworks](README.md) · Related: [OpenUSD](openusd.md) · [Composer review guide](../guides/composer-review.md) ·
> [E1 pit shell and pushbacks](../cases/e1-pit-shell-pushbacks.md) · [C2 tailings breach](../cases/c2-tailings-breach.md)

## What and why

Omniverse **Kit** is NVIDIA's application framework; **USD Composer** ("complex scene authoring") and **USD Explorer**
("large-scale collaboration" and review) are apps built from it [1]. Since the Omniverse Launcher was deprecated on
2025-10-01, both are distributed only as templates of **kit-app-template**, from which you generate the app locally [2].

Division of labour in PitStudio: the Python studio **generates, simulates and computes**; Composer and Explorer
**inspect, light, review and capture hero media**. No number on the website depends on a GUI action, and every Kit
output is reproducible by a scripted headless capture with a manifest.

| App | What PitStudio uses | Mining use |
|---|---|---|
| Composer | layer widget, variant editor and presenter, RTX path tracing, Movie Capture, scriptable viewport capture, Asset Validator UI, PhysX authoring tools [3][4] | flip pushback phases and wet/dusty looks on the generated stage; check colliders; path-traced hero clips |
| Explorer | Review and Layout modes, waypoints stored in the USD stage, Measure, Markup exported as CSV/PDF/XLSX [5][6][7] | full-pit review; case cameras as waypoints; measure bench height, berm and ramp width against the design spec |

Rejected alternatives: committing template-generated files (they carry `LicenseRef-NvidiaProprietary` headers and a
`non-redist` kernel) [8][9]; running Composer on the Kit inside Isaac Sim (the Isaac Sim licence places Kit use apart
from Isaac Sim or Isaac Lab outside its purpose) [10]; Live Sessions (they need Nucleus, deprecated on workstations)
[11]; a Kit panel as the studio console (it would die with Kit) — see [Console](../studio/console.md).

## Identity

| Item | Value |
|---|---|
| kit-app-template | 110.3.0 (2026-08-28), targets Kit 110.3.0 [12] |
| Kit SDK | `omniverse-kit` 110.3.0.371399 on PyPI (2026-08-28), Python `==3.12.*` [13]; Isaac Sim 6.1 ships the same Kit 110.3.0 [14] |
| Production branch alternative | Kit 110.1.4 (PB 26h1) on NGC [15] |
| In the repo's locks | none: the apps are generated outside the repo; only our extension and scripts are committed |
| Licence | NVIDIA Software License Agreement + Omniverse / AI Products product terms [8][16] |
| Class | reference-only |
| Ring | Trial (scoped: local generation outside the repo) |
| Environment | `studio/kit/` (Kit's own Python 3.12) |

## How PitStudio uses it

- `studio/kit/` (planned) holds only Apache-2.0 files: our **pit-tools** extension written from the public Kit docs
  (`config/extension.toml`, `omni.ext.IExt`, `omni.ui`), a minimal app `.kit` file of our own, and launch scripts. The
  generated Composer and Explorer apps live in a git-ignored workspace outside the repo [17].
- The extension's panels: open a case's `root.usda` and switch variants; show case KPIs from run manifests; write a job
  request for the runner; run the Asset Validator; capture waypoints.
- Stages: `st58_kit_capture` (headless path-traced captures from our waypoints with `CaptureOptions`: render preset,
  samples per pixel, frame range, resolution [18]) and `st45b_kit_validate`. Captures are PNG/EXR frames; encoding
  happens outside Kit ([NVENC / FFmpeg](nvenc-ffmpeg.md)).
- Telemetry: the template `.kit` files enable anonymous usage data by default; our launch scripts set
  `enableAnonymousData = false` [19].

Artefacts it will produce: path-traced hero clips per case (C2 first), stills per waypoint, validation reports,
Explorer markup CSV logs and waypoint camera sets reused as glTF cameras for the web. Captures show our scenes only,
not NVIDIA application UI.

## Licence and redistribution

The template's licence is the NVIDIA Software License Agreement (v. 2025-01-30) with the Omniverse product terms;
"Derivative Samples" (modified template code) need the NVIDIA notice and terms at least as protective, which cannot be
Apache-2.0 [8][20]. Code we author from scratch that only calls `omni.*` APIs is ours. The first `template new` asks the
user to accept the Omniverse licensing terms; that prompt is the maintainer's act
([Maintainer acts and licences](../studio/owner-acts-and-licences.md)). Kit performance data (frame times, samples per
second) stay local-only ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)).

## Assumptions and limits

- First launch: "5 to 8 minutes as shaders compile" [1]. Disk size of a built app is unpublished; the NGC air-gap
  bundle of the Feature Branch is 4 GB compressed [21].
- Composer's app file loads only `omni.physx.stageupdate`; the PhysX authoring bundle must be enabled in our app layer.
- Whether viewport capture works with `--no-window` on Kit 110.3 is **UNVERIFIED**; the smoke settles it, with a
  minimised window as fallback.
- Feature-branch churn: the template moves every one to two months [12]; the generated workspace is pinned to a commit.
- Never run together with Isaac Sim or training on the 16 GB GPU.

## In PitStudio

- Guide: [Composer review](../guides/composer-review.md). Cases: C2 hero clip, E1 pushback review and measure.
- Status: **not yet run** — produced in the data-and-models phase. Nothing in `studio/kit/` exists yet; the template prompt has not been answered.

## References

1. NVIDIA. *kit-app-template README*. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/README.md
2. NVIDIA. *Omniverse legacy tools*. https://developer.nvidia.com/omniverse/legacy-tools
3. NVIDIA. *USD Composer template README*. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/templates/apps/usd_composer/README.md
4. NVIDIA. *omni.usd_composer.kit*. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/templates/apps/usd_composer/omni.usd_composer.kit
5. NVIDIA. *USD Explorer modes*. https://docs.omniverse.nvidia.com/explorer/latest/features/modes.html
6. NVIDIA. *Waypoint extension*. https://docs.omniverse.nvidia.com/extensions/latest/ext_waypoints.html
7. NVIDIA. *Markup extension*. https://docs.omniverse.nvidia.com/extensions/latest/ext_markup.html
8. NVIDIA. *kit-app-template LICENSE* (SLA v. 2025-01-30). https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/LICENSE
9. NVIDIA. *kit-sdk packman dependency* (`non-redist`). https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/tools/deps/kit-sdk.packman.xml
10. NVIDIA. *Isaac Sim Additional Software and Materials License*.
    https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/
11. NVIDIA. *Connect SDK live sessions*. https://docs.omniverse.nvidia.com/kit/docs/connect-sdk/latest/api/group__livesessions.html
12. NVIDIA. *kit-app-template CHANGELOG*. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/CHANGELOG.md
13. Python Package Index. *omniverse-kit*. https://pypi.org/pypi/omniverse-kit/json
14. NVIDIA. *Isaac Sim release notes*. https://docs.isaacsim.omniverse.nvidia.com/latest/overview/release_notes.html
15. NVIDIA NGC. *Kit SDK Air Gap Windows (PB 26h1)*. https://catalog.ngc.nvidia.com/orgs/nvidia/omniverse/resources/kit-sdk-airgap-windows-pb26h1/-
16. NVIDIA. *Product Specific Terms for NVIDIA AI Products*.
    https://www.nvidia.com/en-us/agreements/enterprise-software/product-specific-terms-for-ai-products/
17. NVIDIA. *Kit manual: extensions in depth*. https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/extensions_advanced.html
18. NVIDIA. *omni.kit.capture.viewport CaptureOptions*.
    https://docs.omniverse.nvidia.com/kit/docs/omni.kit.capture.viewport/latest/omni.kit.capture.viewport/omni.kit.capture.viewport.CaptureOptions.html
19. NVIDIA. *kit-app-template data collection and use*.
    https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/readme-assets/additional-docs/data_collection_and_use.md
20. NVIDIA. *kit-app-template PRODUCT_TERMS_OMNIVERSE*. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/PRODUCT_TERMS_OMNIVERSE
21. NVIDIA NGC. *Kit SDK Air Gap Windows (FB)*. https://catalog.ngc.nvidia.com/orgs/nvidia/omniverse/resources/kit-sdk-airgap-windows/-
