# M23 — RTX sensor simulation: truck lidar in dust and rain, survey and crusher cameras, proximity radar and slope radar

> Ray-traced lidar, radar and cameras render PitStudio's own pit scenes; dust is added by an open, calibrated
> Beer–Lambert model that also runs live in the browser, and the slope-monitoring radar — which no RTX model provides —
> is an analytical line-of-sight model. · Part of: [Methods](README.md) · Related:
> [RTX sensor physics theory](../theory/rtx-sensor-physics.md) · [ovrtx](../frameworks/ovrtx.md) ·
> [Isaac Sim and Replicator](../frameworks/isaac-sim-replicator.md) · [DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| SOTA | no | precompute; live dust slider (own model) | [B1](../cases/b1-traffic-proximity.md), [B2](../cases/b2-synthetic-perception.md), [C1](../cases/c1-slope-time-of-failure.md), [E2](../cases/e2-survey-reconciliation.md) | ovrtx 0.5.0.377615 + ovstage 0.2.0.377349 (NVIDIA proprietary, reference-only) in `studio/rtx/`; Isaac Sim lidar rain; own dust and slope-radar models in `minephys` (Apache-2.0) | not yet implemented |

NVIDIA, Omniverse, ovrtx and Isaac Sim are named nominatively. PitStudio is not affiliated with or endorsed by NVIDIA,
never redistributes NVIDIA binaries, assets or caches, and publishes **no performance data** of ovrtx, Kit, Isaac Sim
or Replicator: the NVIDIA Software License Agreement §8.9 forbids disclosing benchmarking or performance data without
written permission [14] ([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)). Our renders of
our own scenes are published under CC-BY-4.0.

## What and why

Perception in a pit fails where it matters most: in dust, rain and at night. Physically based sensor simulation lets
PitStudio generate sensor data with exact ground truth for those conditions — the core of the physical-AI loop. NVIDIA's
kit-less RTX sensor library **ovrtx** renders cameras, lidar and radar headless, without a Kit application [1]; Isaac
Sim adds a Mie-scattering rain model for lidar [5]. Neither models **dust** [5], and RTX radar has no phase output, so it
cannot be a slope-monitoring (interferometric) radar [4].

M23 uses each tool for what it does and fills the gaps with open models:

| Scenario | Sensor and engine | Open add-on | Case |
|---|---|---|---|
| **S1** truck collision-avoidance lidar | ovrtx rotary or solid-state lidar (multi-echo, range noise, material returns) [2]; rain arm in Isaac Sim [5] | Beer–Lambert dust model calibrated to a mining dust study [10] | B1, B2 |
| **S2** drone survey camera | ovrtx path-traced camera with ground-truth depth [3] | exposure/noise applied on linear HDR output | E2 ([M19](m19-gaussian-splat-survey.md)) |
| **S3** fixed crusher camera (boulders) | ovrtx RGB + semantic segmentation [3]; Isaac Sim Replicator for instance masks and boxes | depth-based haze model [11] | B2 ([M10](m10-synthetic-data-detector.md)) |
| **S4a** 77 GHz proximity radar | ovrtx radar with RCS and Doppler [4] | — (dust assumed negligible at mm-wave, UNVERIFIED) | B1 |
| **S4b** slope-monitoring radar | **none** (no RTX model) | analytical ground-based InSAR line-of-sight model [12][13] | C1 ([M14](m14-slope-forecasting.md)) |

## The algorithm

### Scenes and materials

Scenes come from PitStudio's USD pipeline (Bingham terrain, procedural equipment, MakeHuman people). Lidar and radar
returns depend on **non-visual material labels** independent of visual shading; the available bases include steel,
rubber, stone, gravel, dirt, mud, water and a retroreflective attribute [6]. Mapping: truck body steel + paint, tyres
rubber, berms and benches stone/gravel, haul road gravel/dirt, wet road mud/water, personnel vest fabric +
retroreflective. Vendor lidar USD profiles shipped with Isaac Sim are NVIDIA assets and are not used; generic lidars
are authored from published datasheet parameters.

### Dust attenuation (lidar and cameras)

Light crossing a dusty path of extinction coefficient $\beta(s)$ (1/m) is attenuated by Beer–Lambert transmittance;
over a uniform path of length $d$ (m) the transmittance is $t = e^{-\beta d}$ [11]. For a lidar return from range $R$
(m) the light crosses the path twice:

$$
T_1(R) = \exp\!\left(-\int_0^R \beta(s)\,ds\right), \qquad T_2(R) = T_1(R)^2
$$

Each clean RTX return is kept, attenuated or dropped according to its transmittance, and "dust returns" are injected
early along the beam where $\beta$ is high. The detection rule is **calibrated to Phillips, Guenther and McAree**:
dust starts to affect lidar measurements when the atmospheric transmittance falls below 71–74 %, and lidar still ranges
retroreflective targets at transmittance as low as 2 % [10]. The functional form of the rule and the mapping of the
paper's transmittance definition to $T_1$/$T_2$ are fixed in the spec. $\beta$ comes from the dust field of
[M16](m16-dust-dispersion.md).

For cameras the same physics gives the standard scattering model [11]:

$$
I = J\,t + A\,(1 - t), \qquad t = e^{-\beta d}
$$

with $I$ the observed radiance, $J$ the scene radiance (the clean linear HDR render), $A$ the airlight and $d$ the
ground-truth distance from the renderer (m).

**Worked example (illustrative extinction values).** With $\beta = 0.01$ m⁻¹, a target at 30 m sees
$T_1 = e^{-0.3} = 0.74$ — at the onset band of [10]. With $\beta = 0.05$ m⁻¹, $T_1(40\ \text{m}) = e^{-2} = 0.14$, and
the 2 % retroreflective floor is reached at $R = \ln(50)/0.05 = 78$ m.

```text
dust_lidar(clean_cloud, beta_field, rule):
    for each beam with returns:
        T1 = exp(-integrate(beta_field, origin, hit))         # along the ray
        keep / attenuate / drop the return by rule(T1, material.retroreflective)
        maybe insert early dust return where beta is high
    assert point_count(frame) > 0                              # guard: ovrtx#3 zero-point fans
    return dusty_cloud
```

### Proximity radar

ovrtx's radar uses a wave-propagation detection-matrix approximation with configurable wavelength (the example's 3.9 mm
is about 77 GHz), chirps, resolutions, Gaussian noise and multipath depth, and outputs per-detection coordinates, radar
cross-section in dBsm and signed Doppler radial velocity [4]. Doppler requires Motion BVH, which raises VRAM use and
render time, so radar batches run separately from camera batches [7].

### Slope-monitoring radar (analytical)

Ground-based interferometric radars measure displacement along the line of sight from the phase difference between
scans [12]. Given the displacement field $\mathbf u(\mathbf x, t)$ (m) of the C1 slope (a Voight creep field, see
[M14](m14-slope-forecasting.md)) and the unit line-of-sight vector $\hat{\mathbf e}$ from the radar to each pixel:

$$
d_{\text{LOS}} = \mathbf u \cdot \hat{\mathbf e}, \qquad \phi = \frac{4\pi}{\lambda}\, d_{\text{LOS}} \pmod{2\pi}
$$

with $\lambda$ the radar wavelength (m) and the factor $4\pi$ reflecting the two-way path. Atmospheric and phase noise
are added with statistics matched to the de Wit real series; the output is a line-of-sight displacement time series per
pixel, which feeds the forecasters of [M14](m14-slope-forecasting.md). Open-pit monitoring practice is reviewed in [13].

### Platform facts

- **Versions:** ovrtx 0.5.0.377615 and ovstage 0.2.0.377349 (locked in `studio/rtx/uv.lock`), pre-release and Alpha,
  with breaking changes in every minor release so far [1]; Python 3.12; installed from NVIDIA's explicit package index.
  Since 0.5.0 the public packages use Vulkan exclusively on Windows [1].
- **Driver:** the minimum validated driver for Ada workstation GPUs on Windows is R580 581.42, and 582.41 or newer after
  the January 2026 Windows security update [8]; the reference machine's 582.78 satisfies both.
- **Clean-room adapter:** PitStudio's adapter is written from the API documentation, never from copied examples, and sits
  behind a thin `SensorBackend` interface with `ovrtx` and `isaac` implementations.
- **Known bug:** OmniLidar can silently return zero points for wide elevation fans on Windows with the exact pinned
  versions [9]; every lidar stage asserts a non-zero point count per frame and limits the fan to a tested range.
- **Determinism:** bit-exact render determinism is not documented, so scene, recipe and seed are hashed while pixels
  and points are checked by tolerance (PSNR/SSIM for images; Chamfer distance and point counts for clouds).

## Baseline and comparison

- **Lidar vs radar under dust** (S1 vs S4a): detection range and points on target per transmittance level.
- **Clean vs dusty vs rainy lidar** (S1): probability of detection vs range × transmittance (0.02–1.0), false dust
  returns, and the TTC margin at detection for truck speeds of 30, 40 and 50 km/h (with [M20](m20-traffic-ttc.md)).
- **Slope radar:** the LOS model's forecast lead time through [M14](m14-slope-forecasting.md), against the noise-free
  displacement field.
- No "better" claim between sensors without the [decision rule](README.md#how-methods-are-compared).

## Acceptance criterion (pre-registered)

No numeric accuracy threshold is pre-registered for M23 (it produces data, not a trained model). Its pre-registered
checks, from the project's validation rules
([quality and validation](../architecture/quality-and-validation.md)):

- dust model unit tests and metamorphic relations: $T_1(0) = 1$; transmittance is non-increasing in range and in
  $\beta$; two-way equals one-way squared; zero dust returns the clean cloud unchanged;
- slope-radar tests: motion along the line of sight is fully seen, motion perpendicular to it is invisible, phase wraps
  at $\lambda/2$ of displacement;
- the TypeScript and Python dust models agree exactly (the live slider's parity class);
- every sensor stage passes its point-count guard, and every manifest records its licence class and the
  `performance: local-only` marker for NVIDIA runtimes.

**Results: Not yet run** — produced in the data-and-models phase. Reported: S1–S4 datasets and their quality metrics
(never rendering throughput), detection-vs-transmittance curves, and the slope-radar series used by C1.

## Lane and web delivery

**Precompute; live dust slider.** RTX outputs are replayed: point clouds as quantised shards ≤ 10 MB (16-bit xyz, 8-bit
intensity and class), videos ≤ 25 MB per AV1 + H.264 pair, image galleries. The **dust (and rain) transmittance slider
is live**: the clean cloud is baked and the open Beer–Lambert model re-attenuates it in a TypeScript worker with a
Python twin. A sensor-comparison widget shows one frame as RGB, semantic, lidar and radar (Doppler colours). Rendering
performance appears only as a "measured locally, not published" card. Fallback: poster frames.

## Assumptions and limits

- The dust model is a calibrated post-process, not volumetric radiative transfer inside the renderer.
- Radar dust immunity is an assumption, stated, not a measured fact.
- Rain in ovrtx is UNVERIFIED (the setting is documented only for Kit); the rain arm uses Isaac Sim.
- The slope-radar model is analytical: no speckle, decorrelation or atmospheric phase screen beyond the matched noise.
- Simulation-grade twin; sensors are generic, not any vendor's product.

## In PitStudio

- **Cases:** [B1](../cases/b1-traffic-proximity.md) (S1, S4a), [B2](../cases/b2-synthetic-perception.md) (S3),
  [C1](../cases/c1-slope-time-of-failure.md) (S4b), [E2](../cases/e2-survey-reconciliation.md) (S2).
- **Code (planned):** `studio/rtx/` (package `pitstudio_rtx`, stage `st53_sensors`); rain lidar in `studio/isaac/`
  (`st57_rain_lidar`); RTX clips `st52_rtx_render` and encoding `st56_encode`; dust attenuation and slope-radar model in
  `minephys.environment` and `minephys.geotech`; live slider in a `web/` worker.
- **Status:** not yet implemented — built test-first in the build phase. The GPU capability probes are written but not
  yet run on the reference machine.

## References

1. ovrtx changelog — breaking changes per minor release; Vulkan-only on Windows since 0.5.0.
   https://github.com/NVIDIA-Omniverse/ovrtx/blob/main/CHANGELOG.md
2. ovrtx lidar — `OmniLidar`, point-cloud channels, validity flag. https://nvidia-omniverse.github.io/ovrtx/sensors/lidar.html
3. ovrtx camera outputs — HDR/LDR colour, distance, semantic segmentation (no instance or box outputs).
   https://nvidia-omniverse.github.io/ovrtx/sensors/cameras/outputs.html
4. ovrtx radar — RCS in dBsm, signed Doppler radial velocity, no phase output.
   https://nvidia-omniverse.github.io/ovrtx/sensors/radar.html
5. Omniverse Lidar extension — Mie-scattering rain model; fog, haze and snow planned; no dust.
   https://docs.omniverse.nvidia.com/kit/docs/omni.sensors.nv.lidar/latest/lidar_extension.html
6. ovrtx non-visual materials (stone, gravel, dirt, mud, steel, rubber, retroreflective).
   https://nvidia-omniverse.github.io/ovrtx/sensors/nonvisual_materials.html
7. Isaac Sim RTX radar — Motion BVH required for Doppler; RTX sensors and VRAM notes.
   https://docs.isaacsim.omniverse.nvidia.com/latest/sensors/isaacsim_sensors_rtx_radar.html
8. ovrtx driver requirements (Ada workstation Windows R580 581.42; 582.41 with KB5074109).
   https://nvidia-omniverse.github.io/ovrtx/driver_requirements.html
9. ovrtx issue #3 — OmniLidar returns zero points for wide elevation fans. https://github.com/NVIDIA-Omniverse/ovrtx/issues/3
10. Phillips, Guenther & McAree (2017). "When the dust settles…" — lidar in airborne dust (transmittance thresholds
    71–74 %; retroreflective targets ranged down to 2 %). Journal of Field Robotics 34(5):985–1009.
    https://api.crossref.org/works/10.1002/rob.21701
11. Narasimhan, S. G. & Nayar, S. K. (2002). Vision and the atmosphere. IJCV 48(3):233–254.
    https://api.crossref.org/works/10.1023/A:1016328200723
12. Monserrat, O., Crosetto, M. & Luzi, G. (2014). A review of ground-based SAR interferometry for deformation
    measurement. ISPRS Journal 93:40–48. https://api.crossref.org/works/10.1016/j.isprsjprs.2014.04.001
13. Le Roux et al. (2025). Slope stability monitoring methods and technologies for open-pit mining: a systematic review.
    Mining 5(2):32 (CC BY 4.0). https://api.crossref.org/works/10.3390/mining5020032
14. NVIDIA Software License Agreement (2026-05-07) — §8.9 benchmarking and performance-data disclosure.
    https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
