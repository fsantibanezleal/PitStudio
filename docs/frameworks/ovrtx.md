# ovrtx

> NVIDIA's Kit-less RTX sensor renderer, used for the truck lidar, the proximity radar, the drone survey camera and the
> crusher camera, with PitStudio's own dust model applied on top. · Part of: [Frameworks](README.md) · Related:
> [Isaac Sim + Replicator](isaac-sim-replicator.md) · [M23 RTX sensor simulation](../methods/m23-rtx-sensor-simulation.md) ·
> [RTX sensor physics](../theory/rtx-sensor-physics.md) · [B1 traffic and proximity](../cases/b1-traffic-proximity.md)

## What and why

**ovrtx** is the RTX renderer packaged as a library, with "headless-first" C and Python APIs and no Kit process [1][2].
It renders cameras in three modes (real-time path tracing, path tracing, minimal), and lidar and radar sensors, and it
hands results to NumPy, Warp or PyTorch as DLPack tensors [3]. **ovstage** is the USD runtime stage it attaches to [4].
NVIDIA itself moves Isaac Lab 3.0 onto ovphysx and ovrtx as kit-less backends [2][5].

Why PitStudio uses it next to Isaac Sim:

- **Lightest RTX path on the laptop.** A library call per frame, no GUI, no Kit startup.
- **Looser driver floor.** The ovrtx table accepts Ada workstation GPUs on Windows from R580 581.42, and from 582.41
  with the January 2026 Windows update KB5074109 [6]. The lane works even if Isaac Sim fails its Compatibility
  Checker.
- **Physically based sensors**: lidar with multi-echo returns and per-material non-visual properties, and a 77 GHz-class
  radar with radar cross-section and Doppler [7][8][9].

Rejected options: ovrtx on Python 3.14 (classifiers and NVIDIA's own example stop at 3.13) [10][11]; one shared 3.12
environment with Isaac Sim (pin conflicts and two RTX runtimes in one process); vendor lidar USD assets (not
redistributable); copying ovrtx example code (it would create NVIDIA-licensed derivative samples) [12].

## Identity

| Item | Value |
|---|---|
| ovrtx | 0.5.0.377615 (published 2026-09-09) [10][13] |
| ovstage | 0.2.0.377349 (2026-09-08) [14] |
| Lock | `studio/rtx/uv.lock`, wheels from the explicit `pypi.nvidia.com` index (PyPI hosts only a 23 KB sdist) [15][16] |
| Licence | NVIDIA Software License Agreement + NVIDIA AI Products terms; `LicenseRef-NvidiaProprietary` [1][10] |
| Class | reference-only |
| Ring | Trial (scoped to `studio/rtx/`) |
| Environment | `studio/rtx/` (Python 3.12, uv-managed) |
| Status upstream | pre-release, alpha; breaking changes in every minor release so far [17] |

## How PitStudio uses it

![Sensor lane: USD stage → ovrtx → own dust model → point-count guard → shards](../assets/diagrams/sensor-lane-ovrtx.svg)

*The sensor lane: clean RTX outputs, then PitStudio's own dust model and a point-count guard, then web shards.*

Stage `st53_sensors` renders four scenarios from our USD stage, kinematic poses and a sensor recipe:

| Scenario | Sensor | Case | Main metric |
|---|---|---|---|
| S1 | Rotary and solid-state truck lidar, in dust (own model) and rain (Isaac Sim arm) | B1, C3 | Detection probability vs range × transmittance; points on target; false dust returns |
| S2 | Drone survey camera, pinhole, nadir + oblique | E2 | Volume error after COLMAP + splats ([COLMAP / Brush / splats](colmap-brush-splats.md)) |
| S3 | Fixed crusher camera with semantic ids | B2, D1 | Detector mAP50 on synthetic held-out data; cross-renderer gap |
| S4a | 77 GHz-class proximity radar (RCS, Doppler; Motion BVH on) | B1 | Lidar vs radar detection range under dust |

**Dust is not modelled by ovrtx or Isaac Sim** [18]. PitStudio applies its own closed-form attenuation to the clean
point cloud. Each return at range $R$ (m) keeps a fraction of its power set by the two-way transmittance

$$
T(R) = \exp\!\left(-\int_0^R \beta(s)\,\mathrm{d}s\right), \qquad P_r(R) \propto \frac{\rho\,T(R)^2}{R^2},
$$

where $\beta$ (m⁻¹) is the dust extinction coefficient along the beam, taken from the C3 dust field, $\rho$ (–) the
target reflectance and $P_r$ the received power. Returns whose power falls below the detection threshold drop out, and
early "dust returns" appear where the dust is dense. The thresholds are anchored to the field study of Phillips et al.
(2017): dust starts to affect measurements once atmospheric transmittance falls below 71–74 %, and retroreflective
targets are still ranged at transmittance as low as 2 % [19]. Cameras use the depth-based haze model
$I = J\,t + A\,(1-t)$ with $t = e^{-\beta d}$ (Narasimhan & Nayar 2002) [20]. The model lives in `minephys.environment`
and runs **live** in the browser as a dust slider over baked clouds.

## Licence and redistribution

Proprietary and reference-only ([DEC-0004](../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md)).
Our renders of our own procedural or CC0 scenes are published under CC-BY-4.0. The NVIDIA SLA §8.9 forbids disclosing
"results of benchmarking … or performance data relating to the Software" without written permission [21], so ovrtx
throughput, frame times and VRAM stay in the local run log
([DEC-0005](../architecture/decisions/DEC-0005-performance-data-licence-rule.md)). Our adapter is written from the API
documentation, never from the examples.

## Assumptions and limits

- **ovrtx#3 (open, 2026-09-29):** `OmniLidar` silently returns 0 points for a wide or near-pole elevation fan, with no
  diagnostic, on Windows with exactly our pinned pair [22]. The S1 recipe limits the fan to a tested range and the
  stage asserts more than 0 points in every frame; it fails fast otherwise.
- Rain: the lidar's Mie rain model is set through a Kit setting that ovrtx does not expose [18]; rain runs in Isaac Sim
  (`st57_rain_lidar`). Radar weather is not modelled; treating dust as negligible at millimetre wave is a stated,
  unsourced assumption.
- No instance segmentation, 2D/3D boxes, motion blur or lens distortion are documented for ovrtx cameras [3]. Boxes
  come from Replicator, or from connected components of the semantic mask.
- First `step()` blocks 1–2 minutes for shader compilation; 40 warm-up frames are recommended after a scene change
  [23][24]. Windows packages use Vulkan only since 0.5.0 [17].
- Render determinism is not documented. Images are compared by tolerance (PSNR/SSIM) and clouds by Chamfer distance
  and point counts, never bit for bit.
- Never imported in the same process as Kit or Isaac Sim.

## In PitStudio

- Probe: the bench registry lists `ovrtx` (local-only); its script is not written yet and will be written against the
  API docs ([Capabilities probe](../studio/capabilities-probe.md)).
- Status: **not yet run** — produced in the data-and-models phase. Reported then: S1–S4a outputs and their metrics; ovrtx
  performance stays in the local run log.

## References

1. NVIDIA. *ovrtx README* (licence, pre-release). https://github.com/NVIDIA-Omniverse/ovrtx/blob/main/README.md
2. NVIDIA (2026-04-08). *Integrate physical AI capabilities into existing apps with NVIDIA Omniverse libraries*.
   https://developer.nvidia.com/blog/integrate-physical-ai-capabilities-into-existing-apps-with-nvidia-omniverse-libraries/
3. NVIDIA. *ovrtx camera outputs*. https://nvidia-omniverse.github.io/ovrtx/sensors/cameras/outputs.html
4. NVIDIA. *ovstage README*. https://github.com/NVIDIA-Omniverse/ovstage
5. Isaac Lab. *v3.0.0-EA release*. https://github.com/isaac-sim/IsaacLab/releases/tag/v3.0.0-EA
6. NVIDIA. *ovrtx driver requirements*. https://nvidia-omniverse.github.io/ovrtx/driver_requirements.html
7. NVIDIA. *ovrtx lidar*. https://nvidia-omniverse.github.io/ovrtx/sensors/lidar.html
8. NVIDIA. *ovrtx radar*. https://nvidia-omniverse.github.io/ovrtx/sensors/radar.html
9. NVIDIA. *ovrtx non-visual materials*. https://nvidia-omniverse.github.io/ovrtx/sensors/nonvisual_materials.html
10. Python Package Index. *ovrtx* 0.5.0.377615. https://pypi.org/pypi/ovrtx/json
11. NVIDIA. *ovrtx lidar example pins*.
    https://raw.githubusercontent.com/NVIDIA-Omniverse/ovrtx/main/examples/python/lidar/pyproject.toml
12. NVIDIA (2026-04-15). *Product Specific Terms for NVIDIA AI Products*.
    https://www.nvidia.com/en-us/agreements/enterprise-software/product-specific-terms-for-omniverse/
13. NVIDIA. *ovrtx releases (API)*. https://api.github.com/repos/NVIDIA-Omniverse/ovrtx/releases?per_page=2
14. Python Package Index. *ovstage* 0.2.0.377349. https://pypi.org/pypi/ovstage/json
15. NVIDIA. *pypi.nvidia.com ovrtx index*. https://pypi.nvidia.com/ovrtx/
16. Astral. *uv indexes* (explicit index pinning). https://docs.astral.sh/uv/concepts/indexes/
17. NVIDIA. *ovrtx CHANGELOG*. https://github.com/NVIDIA-Omniverse/ovrtx/blob/main/CHANGELOG.md
18. NVIDIA. *Omniverse Lidar extension* (Mie rain model; fog, haze, snow planned).
    https://docs.omniverse.nvidia.com/kit/docs/omni.sensors.nv.lidar/latest/lidar_extension.html
19. Phillips, T. G., Guenther, N., McAree, P. R. (2017). *When the dust settles …* (lidar in fine airborne
    particulates). Journal of Field Robotics 34(5):985–1009. DOI 10.1002/rob.21701
20. Narasimhan, S. G., Nayar, S. K. (2002). *Vision and the atmosphere*. IJCV 48(3):233–254. DOI 10.1023/A:1016328200723
21. NVIDIA. *NVIDIA Software License Agreement* (2026-05-07).
    https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
22. NVIDIA. *ovrtx issue #3* (OmniLidar returns 0 points for wide elevation fans). https://github.com/NVIDIA-Omniverse/ovrtx/issues/3
23. NVIDIA. *ovrtx Python getting started*. https://nvidia-omniverse.github.io/ovrtx/python_api/getting_started.html
24. NVIDIA. *ovrtx sensor configuration*. https://nvidia-omniverse.github.io/ovrtx/sensors/configuration.html
