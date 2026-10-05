# DEC-0015: People in synthetic scenes come from MakeHuman CC0 exports

> The people class in PitStudio's synthetic data is built from characters exported by the official, unmodified
> MakeHuman 1.3.0 under its CC0 export option, using only its bundled system assets; procedural mannequins are the
> fallback, and NVIDIA's character assets are never used. · Part of: [decisions](README.md) · Related:
> [MakeHuman people dataset card](../../data-contract/dataset-cards/makehuman-people.md) ·
> [B2 synthetic perception](../../cases/b2-synthetic-perception.md) · [DEC-0004](DEC-0004-proprietary-sdks-reference-only.md)

**Status:** Accepted, 2026-10-04

## Context

People near haul trucks are the safety question behind cases B1 and B2 and behind several of the Cosmos Reason 2
hazard questions (for example, whether a person is inside a truck's blind zone). The synthetic-data generator therefore
needs human models that can be rendered, labelled and published as part of a CC-BY dataset.

- NVIDIA and Isaac Sim character assets fall under the Isaac Sim Additional Software and Materials License and may not
  be redistributed [1]; renders that contain them would carry that restriction into the published dataset.
- The plan's real-data search found no licence-clean, labelled images of people in open pits.
- MakeHuman, an open-source character creator, offers a CC0 option for exported models under conditions in section C of
  its licence: exports made with the file-export function of an OFFICIAL and UNMODIFIED version of MakeHuman, by the
  copyright holders of the bundled assets [2] (licence page re-read 2026-10-04 when the tool was downloaded).
- MakeHuman 1.3.0 (released 2024-05-15) is a stale release, distributed as an official Windows zip of about 325 MB.

## Decision

- **Tool.** The official MakeHuman 1.3.0 Windows zip, unmodified, installed per user with its SHA-256 pinned at download.
- **Assets.** Characters are generated from MakeHuman's bundled system assets only and exported through its file-export
  function under the CC0 option. No third-party add-on assets.
- **Use.** Exported characters enter PitStudio's USD scenes as `person` instances with UsdSemantics labels. Only
  PitStudio's renders (CC-BY) are published; the exported meshes stay inputs of the bake.
- **Fallback.** If the export conditions turn out not to fit, procedural mannequins replace them, and the B2 card says so.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| NVIDIA / Isaac Sim character assets | High quality, ready in Isaac Sim | Not redistributable; would restrict the published dataset [1] | Licence |
| No people class | Simplest | Weakens B1 and B2 and removes the person-related hazard questions | Loses the core safety question |
| Procedural mannequins only | Fully ours, no licence question | Less realistic shapes; a weaker detector of real people | Kept as the fallback |

## Consequences

**Positive.** A people class whose renders can be published under CC-BY; provenance fixed by the pinned binary.

**Negative, accepted.** A stale, OpenGL-based desktop tool in the toolchain; the export smoke test opens a window and
cannot run headless in CI; realism is limited, which the detector's "not measured" sim-to-real status already reflects.

**Watch.** MakeHuman releases and licence wording.

**Status.** The zip is downloaded, pinned and extracted; the export smoke test waits for the reference machine.

## References

1. Isaac Sim Additional Software and Materials License.
   https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/
2. MakeHuman community: licence, §C "MakeHuman output GPL exception", accessed 2026-10-04.
   http://www.makehumancommunity.org/content/license.html
