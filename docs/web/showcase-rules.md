# Showcase rules

> The honesty rules every artefact on the site obeys — lane badges, "not yet run", outputs-only for proprietary tools,
> our own scenes, local-only performance cards — and the CI checks that enforce them. · Part of: [Web](README.md) ·
> Related: [structure](structure.md) ·
> [DEC-0005 performance-data licence rule](../architecture/decisions/DEC-0005-performance-data-licence-rule.md) ·
> [DEC-0004 proprietary SDKs reference-only](../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md) ·
> [owner acts and licences](../studio/owner-acts-and-licences.md)

## What and why

A showcase of 17 tools invites two failure modes: a brochure for proprietary software, and results that look more
finished than they are. PitStudio prevents both with rules that are **checked in CI**, not left to good intentions.
Each rule names what the visitor sees, why, and the check that fails the build when it is broken. Nothing on the site
is shown as more than it is: a tool that has not run says so; a number that a licence forbids publishing is replaced by
a card that says why.

## The rules

### 1. Every artefact card carries a lane badge and its provenance

| Badge | Meaning |
|---|---|
| **LIVE** | Computed now, in this browser, on the active tier |
| **REPLAY** | Precomputed by the named tool in the named run, replayed here |
| **STATIC** | A figure or table |

Provenance chips name the producing tool, the run id and the commit (FR-000-06). The lane is **measured, not
declared**: an artefact is LIVE only if it is web-drivable, its asset is ≤ 25 MB, an interaction takes ≤ 16 ms or a
run ≤ 1 s on T2, and its trace is ≤ 10 MB; otherwise it is precompute or replay. The measurement is stored in the
manifest and CI fails when a label disagrees with it (FR-000-15). See [compute lanes](../pipelines/compute-lanes.md).

### 2. A tool marked done has at least one artefact

The tool registry `studio/tools.yaml` holds a status per tool. CI fails if an entry with `status: done` has no artefact
in the web manifest whose `producer.tool` equals that tool's id (FR-000-07).

### 3. Nothing published means "not yet run"

A tool with no published artefact shows **"not yet run"**, never a stock image or a vendor screenshot. A tool that was
evaluated and dropped shows **"evaluated, not adopted"** with the reason; that is an honest result, not a gap. The
tools already evaluated and not adopted have their own pages: [cuOpt](../frameworks/not-adopted-cuopt.md),
[PhysicsNeMo](../frameworks/not-adopted-physicsnemo.md) and
[Cosmos Predict / Transfer](../frameworks/not-adopted-cosmos-predict-transfer.md).

### 4. Proprietary tools contribute outputs only

Isaac Sim, Replicator, Kit, ovrtx, ovphysx, TensorRT and the Cosmos weights are **reference-only**: the visitor installs
them from NVIDIA's official sources under NVIDIA's terms. PitStudio publishes what they **produced** — images, videos,
point clouds, metrics, text — and never their binaries, TensorRT engines, shader or extension caches, NVIDIA assets,
NVIDIA-licensed template code or GGUF weight files. Guards in the build check for engines, caches, NVIDIA headers and
GGUF files ([DEC-0004](../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md)).

### 5. Our scenes, not NVIDIA UI

Renders and captures show **PitStudio's own scenes** (procedural pit geometry from public terrain, CC0 textures,
MakeHuman CC0 people exports), never screenshots of NVIDIA application UI. This is a trademark and copyright caution,
a judgement call rather than a requirement found in a licence text.

### 6. Local-only performance cards

Two licences forbid publishing performance data without NVIDIA's permission:

| Software | Licence clause | What the site shows |
|---|---|---|
| Isaac Sim, Kit, Replicator, ovrtx (NVIDIA Software License Agreement) | §8.9 [1] | outputs + "measured locally, not published (licence)" |
| TensorRT for RTX | SLA §2.13 [2] | not used for published evidence; internal only |
| TensorRT (regular), for PitStudio's own models | no benchmark or performance-data clause in the reviewed licence text | full latency, throughput, energy and parity tables |

The regular TensorRT result is **pinned to the licence text**: both TensorRT 11.3.0.99 wheels ship the same
`LICENSE.txt` (47,141 bytes, SHA-256 `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`), and the
capability probe `studio/bench/probe_tensorrt.py` records that hash. If NVIDIA changes the text, TensorRT results drop
to local-only until the new text is reviewed.

This rule already runs in code: every probe declares `publish: public | local-only`, and
`studio/bench/run_bench.py` writes the committed `studio/capabilities.json` with metrics replaced by the string
"measured locally, not published (licence)" and telemetry withheld for local-only probes. The full data stays in
`$PITSTUDIO_TMP/bench/`. `tests/contract/test_capabilities_contract.py` checks the split and the path scrubbing.

### 7. Benchmarks state their conditions

A published timing names the GPU model, driver, power state and the fraction of time spent in each throttle state
(software power cap, software thermal slowdown, hardware thermal slowdown), because a power-limited laptop GPU often
runs power-capped and timings are not comparable otherwise [3]. Every benchmark card says "our hardware, not a
comparative benchmark".

### 8. "Better" only by the pre-registered decision rule

A result is called better than another only if the paired 95 % confidence interval of the difference excludes 0;
otherwise the UI says **"no significant difference"** (FR-000-05,
[DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)). Single real events, such as the one
real slope-failure series, are reported descriptively with "single real event — no significance test".

### 9. Synthetic data is labelled as such

A data type with no real reference (equipment and people images without the optional real probe, dust fields, haul
telemetry) is labelled **"calibrated synthetic — not validated against real data"** and gets no C2ST or TSTR claim
(FR-000-09). Equipment and people detection is reported with sim-to-real **"not measured"** unless the optional real
probe is labelled.

### 10. Cosmos outputs are display-only and attributed

Answers and captions from Cosmos Reason 2 are text shown with the attribution "Built on NVIDIA Cosmos", as the NVIDIA
Open Model License requires for Cosmos models [4]. They are never a headline KPI.

### 11. Every external number has a source

Every external number in the UI, the docs and the knowledge tables carries a DOI or URL, and every row not yet checked
against its primary page is flagged **UNVERIFIED** (FR-000-10).

## Card anatomy

An artefact card is rendered from one manifest entry. The entry below is illustrative; the schema is fixed by
`contracts/manifest.schema.json` in the build phase.

```json
{
  "id": "a1-des-trace-baseline",
  "producer": { "tool": "pytorch", "run_id": "<run id>", "commit": "<sha>" },
  "lane": { "label": "replay", "measured": { "asset_mb": 0.0, "run_ms_t2": 0.0, "trace_mb": 0.0 } },
  "licence_class": "open",
  "performance": "public",
  "host": "git",
  "sha256": "<sha256 of the served file>"
}
```

For a reference-only tool the same entry carries `"performance": "local-only"`, and the card shows the outputs with
the local-only note instead of timing chips.

## CI enforcement

| Rule | Check | Status |
|---|---|---|
| 1 lane badge, measured lane | manifest schema + lane-gate check against measurements (FR-000-15) | build phase |
| 2 done ⇒ artefact | registry vs manifest join (`producer.tool`) | build phase |
| 3 "not yet run" | unit + e2e on tool pages with an empty registry | build phase |
| 4 outputs only | file guards for engines, caches, NVIDIA headers, GGUF; `tools/check_repo.py` for secrets, machine paths and files > 10 MB | partly today (`check_repo.py`) |
| 6 local-only | probe `publish` field, `public_view()` split, contract test; manifest `performance: local-only` guard | today for the capability probe; manifest guard in the build phase |
| 7 conditions | manifest telemetry fields required for any published timing | build phase |
| 8 decision rule | unit tests on the comparison helper; e2e on `/results` | build phase |
| 9, 11 synthetic label, sources | manifest and knowledge-table schema fields; docs check | build phase |

## Assumptions and limits

- Licence readings here are the maintainer's interpretation of published terms, not legal advice.
- The "our scenes, not NVIDIA UI" rule is a precaution; it is stricter than any clause found.
- The rules make the site honest about what it shows; they do not make a result correct. Correctness is the job of the
  specs, tests and acceptance criteria.

## In PitStudio

- Foundation requirements FR-000-05 to FR-000-10 and FR-000-15 in `specs/000-foundation/spec.md`; feature spec
  `019-web-studio`.
- Today: rule 6 runs in the capability bench and its contract test; every studio tool is "not yet run"; the GPU probes
  are written but not yet run on the reference machine.

## References

1. NVIDIA, "NVIDIA Software License Agreement", §8.9 (performance-data disclosure). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
2. NVIDIA, "TensorRT for RTX Software License Agreement" (v. 2025-04-21), §2.13. https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
3. NVIDIA, "NVML API Reference: Clocks Event Reasons" (updated 2026-09-09). https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html
4. NVIDIA, "NVIDIA Open Model License Agreement" (last modified 2025-10-24). https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
