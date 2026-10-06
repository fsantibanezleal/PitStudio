# Composer review

> Generate USD Composer / USD Explorer locally from NVIDIA's kit-app-template (outside the repository), load
> PitStudio's own Kit extension, review the composed pit stage, and capture path-traced stills of our scenes headlessly
> from canonical waypoints. · Part of: [Guides](README.md) · Related:
> [Kit, USD Composer and Explorer](../frameworks/kit-usd-composer-explorer.md) · [OpenUSD](../frameworks/openusd.md) ·
> [owner acts and licences](../studio/owner-acts-and-licences.md) · [showcase rules](../web/showcase-rules.md)

## What and why

**Goal:** a human review loop for the stages that the open lane composes (terrain, pit design, assets, fleet, sensors,
weather layers), plus publication-quality path-traced stills of **PitStudio's own scenes** for the case pages and the
Composer tool page. USD Composer ("complex scene authoring") and USD Explorer ("large-scale collaboration") are now
distributed only as kit-app-template templates [1]; the old Launcher and Nucleus Workstation were deprecated on
2025-10-01 [2].

Template-generated files are NVIDIA-licensed derivative samples, stamped with a proprietary licence header, so they are
**generated outside the PitStudio repository and never committed**. What PitStudio commits is its own Apache-2.0 Kit
extension in `studio/kit/` (review panels, waypoint cameras, validation and capture scripts), written without copying
template code.

**Status:** optional. The extension, the capture stage `st58_kit_capture` and the validation stage
`st45b_kit_validate` are written in the build phase. Generating the app requires the maintainer to accept the
kit-app-template licence prompt; if that is declined, Isaac Sim's own GUI is used for review and the Composer tool page
says "not run".

## Prerequisites

- An RTX GPU; the template README recommends an RTX 3070 or better and a Windows driver ≥ 551.78 [1]. Git. Visual
  Studio is needed only for C++ extensions, which PitStudio does not have [1].
- Kit 110.3 embeds CPython 3.12; extension code must be 3.12-compatible and runs inside Kit's interpreter [3].
- A short working folder outside the repository (template build artefacts are long paths), and Windows long paths
  enabled.
- Maintainer act: the first `template new` prompts to accept the Omniverse licensing terms [1].
- Composed stages from the open lane: `st40_compose` → `st45_validate` ([studio stages](../pipelines/studio-stages.md)).

## Steps

1. **Generate the app outside the repository** (maintainer, once). These are kit-app-template's own commands, shown for
   context; they run in the template's folder, never in PitStudio's.

   ```bash
   git clone https://github.com/NVIDIA-Omniverse/kit-app-template.git
   cd kit-app-template
   ./repo.bat template new      # choose USD Composer or USD Explorer; first run shows the licence prompt
   ./repo.bat build
   ./repo.bat launch
   ```

   The first launch can take 5 to 8 minutes while shaders compile [4]. Template caches live in `%LOCALAPPDATA%\ov` and a
   packman folder at the drive root unless `PM_PACKAGES_ROOT` points elsewhere [4].

2. **Turn telemetry off.** The template `.kit` files enable anonymous usage data; the documented opt-out is
   `[settings.telemetry] enableAnonymousData = false` [5]. PitStudio's launch scripts pass the equivalent
   `--/telemetry/enableAnonymousData=false` setting [6].

3. **Load PitStudio's extension and open a case stage.** The extension folder is added with Kit's `--ext-folder` and
   enabled with `--enable` [6].

   ```bash run deferred=P6
   uv run --extra runner studio run studio/recipes/cases/e1.yaml --stage st45b_kit_validate
   ```

4. **Review.** Variants (pushbacks, weather, time of day), layers and validation results are reviewed interactively in
   Composer; USD Explorer adds large-scene review tools. Waypoints are the canonical case cameras stored in USD and
   reused for the web glTF cameras and for capture.

5. **Capture stills headlessly** from the waypoints with the path tracer. Kit's scriptable viewport capture exposes the
   render preset (path trace), samples per pixel, frame range and output format [7].

   ```bash run deferred=P6
   uv run --extra runner studio run studio/recipes/cases/e1.yaml --stage st58_kit_capture
   ```

6. **Encode and publish** the stills and any clip ([encode videos](encode-videos.md)), then `studio publish`.

## Expected output

- EXR/PNG stills per waypoint with a capture manifest (stage hash, waypoint, render preset, samples per pixel), produced
  by `kit-usd-composer-explorer` with licence class reference-only.
- On the web: stills of **our** scenes on the E1 case page and the Composer tool page, with REPLAY badges. No NVIDIA
  application UI appears in any published image, and no capture timing is published (NVIDIA SLA §8.9 [8]).
- Today: **Not yet run** — produced in the data-and-models phase.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `template new` stops at a licence prompt in automation | the prompt is interactive on first use | the maintainer answers it once; no environment variable is documented to pre-accept it |
| A packman folder appears at the drive root, or creating it is refused | packman's default cache location | set `PM_PACKAGES_ROOT` to a short per-user path [4] |
| Headless capture produces empty frames | viewport capture with `--no-window` is unconfirmed on Kit 110.3 | run the capture smoke first; fall back to a hidden window |
| Git shows template files in PitStudio | the app was generated inside the repository | delete them and generate outside; a repository guard for NVIDIA licence headers is added in the build phase |

## Assumptions and limits

- Composer and Explorer are review and capture tools here, not the scene's source of truth: the stage is generated by
  the open lane and validated by hash.
- Stills show only PitStudio's procedural geometry, public terrain and CC0 / CC-BY assets with attribution; NVIDIA
  sample or library assets are never published.

## In PitStudio

- Cases [E1](../cases/e1-pit-shell-pushbacks.md) (pushback review and measurement) and
  [C2](../cases/c2-tailings-breach.md) (path-traced hero clip); stages `st58_kit_capture`, `st45b_kit_validate`.

## References

1. NVIDIA, kit-app-template README — templates, prerequisites (RTX 3070 recommended, driver ≥ 551.78 Windows), VS for C++ only, licence prompt on first `template new`. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/README.md
2. NVIDIA, "Omniverse legacy tools" — Launcher and Nucleus Workstation deprecated 2025-10-01. https://developer.nvidia.com/omniverse/legacy-tools
3. PyPI, `omniverse-kit` 110.3.0.371399 — `requires_python ==3.12.*`. https://pypi.org/pypi/omniverse-kit/json
4. NVIDIA, kit-app-template "Usage and troubleshooting" — 5–8 min first launch, cache locations, `PM_PACKAGES_ROOT`. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/readme-assets/additional-docs/usage_and_troubleshooting.md
5. NVIDIA, kit-app-template "Data collection and use" — `enableAnonymousData = false` opt-out. https://raw.githubusercontent.com/NVIDIA-Omniverse/kit-app-template/main/readme-assets/additional-docs/data_collection_and_use.md
6. NVIDIA, Kit manual "Configuring" — `--enable`, `--ext-folder`, `--/setting=value`. https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/configuring.html
7. NVIDIA, `omni.kit.capture.viewport` `CaptureOptions` — path-trace preset, samples per pixel, frames. https://docs.omniverse.nvidia.com/kit/docs/omni.kit.capture.viewport/latest/omni.kit.capture.viewport/omni.kit.capture.viewport.CaptureOptions.html
8. NVIDIA, "NVIDIA Software License Agreement", §8.9. https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
