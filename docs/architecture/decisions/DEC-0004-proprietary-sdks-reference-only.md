# DEC-0004: Proprietary SDKs are referenced, never redistributed

> The public repository contains only PitStudio's own code, USD and generated outputs; NVIDIA binaries, caches, assets,
> template-derived code, engines and gated weights never enter git, releases, Pages or packages; every artefact carries
> a licence class, and a notice states the trademarks and non-affiliation. · Part of: [decisions](README.md) · Related:
> [owner acts and licences](../../studio/owner-acts-and-licences.md) · [sources and licences](../../data-contract/sources-and-licences.md) ·
> [DEC-0005](DEC-0005-performance-data-licence-rule.md)

**Status:** Accepted, 2026-10-04

## Context

PitStudio is Apache-2.0, but its studio drives proprietary NVIDIA runtimes (Kit, Isaac Sim, Replicator, ovrtx), may
evaluate gated model weights (Cosmos) and depends on non-OSI or share-alike inputs. The relevant terms:

- The NVIDIA Software License Agreement (2026-05-07) forbids using the software "in any manner that would cause
  components to become subject to an OSS License", forbids copying or distribution beyond the grant, and forbids implying
  NVIDIA sponsorship or endorsement [1]. Omniverse became free for production use and redistribution "under the same
  terms" in May 2026 (announced 2026-07-01) [2]; that does not relicense its binaries.
- The Isaac Sim licence FAQ allows selling outputs such as videos, reports and datasets, and one's own Python code and
  `.usd` assets; redistributing Isaac Sim or Kit binaries, or NVIDIA-provided assets, is not allowed [3]. The Isaac Sim
  Additional Software and Materials License covers the NVIDIA-provided assets [4]. Whether the wording explicitly covers
  free public renders is not stated, so PitStudio publishes only renders of its own scenes.
- kit-app-template output (USD Composer, USD Explorer) is NVIDIA-licensed derivative code that carries a notice [5].
- Cosmos weights under the NVIDIA Open Model License require a licence copy, a notice and "Built on NVIDIA Cosmos" on
  redistribution [6].
- OpenUSD (`usd-core`) is under the Tomorrow Open Source Technology License 1.0, Apache-2.0 with a modified trademark
  clause; it is not SPDX-listed and not OSI-approved [7].
- MineLib is CC BY-SA 3.0 per its publisher and the Maus mining polygons are CC BY-SA 4.0; share-alike terms propagate.
- NVIDIA's brand guidance asks for no NVIDIA marks in product or domain names and no implied endorsement [8].

## Decision

1. **Allowed in git, releases, Pages and PyPI:** PitStudio's source (Apache-2.0); its USD layers and scene recipes
   (CC-BY-4.0 or Apache-2.0); its generated outputs (renders, synthetic datasets, trajectories, trained weights) when
   every input asset is its own or licence-cleared (CC0, MIT-0, CC-BY with attribution) and the training data permits
   it; documentation (CC-BY-4.0).
2. **Never in git, releases, Pages or PyPI:** NVIDIA binaries, wheels, containers, Kit kernels, extension and shader
   caches; NVIDIA, Isaac or SimReady 3D assets not under CC0, MIT-0 or CC-BY; kit-app-template-derived files (USD
   Composer and Explorer are generated outside the repository, and only PitStudio's own extension, `.kit` file and
   scripts are committed); gated model weights, including PitStudio's own quantised GGUF conversions; TensorRT engines
   and timing caches; Nsight report files; images derived from NVIDIA containers; third-party executables run as tools
   (FFmpeg, COLMAP, llama.cpp, Brush), which are referenced by version and SHA-256.
3. **Dependency declaration.** Proprietary packages appear only in isolated studio projects resolved from their official
   index at install time. A lock file listing their hashes is metadata, not redistribution.
4. **Licence classes** recorded for every baked asset, with its inputs' classes and render provenance (engine, version,
   driver, asset list): `redistributable`, `derived-only`, `share-alike` (kept in separate manifest entries),
   `reference-only` (proprietary: named, never copied) and `no-redistribution`. Whether performance data may be
   published is decided separately ([DEC-0005](DEC-0005-performance-data-licence-rule.md)).
5. **Licence allow-list.** TOST-1.0 is allowed as a dependency licence. Proprietary licences are allowed only for
   packages in the studio projects, never in the root runtime or the web bundle.
6. **Trademarks.** No third-party marks in repository, product, package or domain names; nominative use in prose
   ("NVIDIA Isaac Sim", "OpenUSD"); no vendor logos. The NOTICE, the README and the site footer state: "NVIDIA,
   Omniverse, Isaac Sim, Cosmos and RTX are trademarks of NVIDIA Corporation. This project is independent and not
   affiliated with or endorsed by NVIDIA."
7. **Attribution duties.** Cosmos outputs carry "Built on NVIDIA Cosmos" and the licence notice, are display-only by
   default, and are not used to train other models unless the downstream model card carries the same notice.
8. **Guards.** The repository check (`tools/check_repo.py`, which today fails on secrets, machine paths, files over
   10 MB and template residue) is extended in the build phase to fail on committed NVIDIA cache or binary patterns,
   TensorRT engines (`*.plan`, `*.engine`), Nsight reports, GGUF files, files with NVIDIA proprietary headers,
   `omniverse://` or NVIDIA asset URLs inside committed USD, a missing licence class, and share-alike assets without
   CC BY-SA labelling.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Vendor SDK pieces or caches for one-click setup | Faster first run | Violates the redistribution terms [1] | Licence |
| Commit kit-app-template output as Apache-2.0 | Faster review GUI | It is NVIDIA-licensed derivative code with its own notice [5] | Licence |
| Use the Isaac Sim GUI only and skip Composer/Explorer | No template code at all | Loses Explorer's review tools | Kept as the fallback if the template licence prompt is declined |
| No proprietary runtimes at all | Simplest licensing | Fails the requirement to apply the Omniverse-class stack and use the GPU fully | The open stack stays the reproducible core; proprietary tools add outputs |
| Treat share-alike data like CC-BY | Simpler bookkeeping | Licence violation | Share-alike layers stay separate |

## Consequences

**Positive.** Licence-clean public surfaces; the proprietary studio is still demonstrable and reproducible for anyone
who installs it; every artefact's rights are explicit.

**Negative, accepted.** Extra manifest fields and guard checks; renders cannot use NVIDIA sample assets (people come
from MakeHuman, [DEC-0015](DEC-0015-people-assets-makehuman.md)); share-alike layers need separate handling. The NOTICE
file must be updated with the trademark statement (open item).

**Watch.** Changes to NVIDIA's terms during their 2026 consolidation; the Isaac Sim asset licence; TOST-1.0 status; the
Cosmos licence moving from the Open Model License to OpenMDW for newer models; MineLib's licence wording.

## References

1. NVIDIA Software License Agreement (2026-05-07).
   https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
2. NVIDIA Developer Forums (2026-07-01). NVIDIA Omniverse licensing change.
   https://forums.developer.nvidia.com/t/nvidia-omniverse-licensing-change/375138
3. Isaac Sim licence FAQ. https://docs.isaacsim.omniverse.nvidia.com/latest/common/license-faq.html
4. Isaac Sim Additional Software and Materials License.
   https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/
5. kit-app-template repository. https://github.com/NVIDIA-Omniverse/kit-app-template
6. NVIDIA Open Model License. https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
7. OpenUSD licence (TOST-1.0). https://raw.githubusercontent.com/PixarAnimationStudios/OpenUSD/release/LICENSE.txt
8. NVIDIA. Logo and brand usage. https://www.nvidia.com/en-us/about-nvidia/legal-info/logo-brand-usage/
