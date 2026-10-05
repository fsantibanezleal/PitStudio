# M16 — Haul-road dust: AP-42 emissions, Gaussian plume and Lagrangian particles

> Dust from haul roads is estimated with the US EPA unpaved-road emission factor, spread with a Gaussian plume live in
> the browser, and followed as GPU Lagrangian particles over the pit terrain in the studio. · Part of:
> [Methods](README.md) · Related: [Dust theory](../theory/dust.md) · [M02 DES](m02-haulage-des.md) ·
> [M23 dust in lidar](m23-rtx-sensor-simulation.md) · [Case C3](../cases/c3-dust.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical / SOTA | no | live + precompute | [C3](../cases/c3-dust.md) | `minephys.environment` (Apache-2.0) + TypeScript port; Warp particles in `studio/` | not yet implemented |

## What and why

Unpaved haul roads are a dominant dust source at open pits. The regulatory-grade method to estimate their emissions
is the US EPA AP-42 section 13.2.2 "Unpaved Roads", whose current version dates from November 2006 [1]; NIOSH's
dust-control handbook covers control practice [3]. Emissions alone do not answer the questions of case C3 — how much
reaches a receptor, how much water the trucks should spray — so M16 chains three models:

1. **AP-42 emission factor** per vehicle-kilometre, driven by the truck traffic from the [DES](m02-haulage-des.md);
2. **Gaussian plume** dispersion with ground reflection for live, closed-form concentration maps [2];
3. **Lagrangian particles** in Warp that follow the wind over the real pit terrain and settle by Stokes' law, for
   cases where the terrain matters (in-pit receptors, the pit as a trap).

The dust field also feeds other methods: its optical depth drives dust in synthetic images ([M10](m10-synthetic-data-detector.md))
and in the lidar model ([M23](m23-rtx-sensor-simulation.md)), and its concentration fields train the FNO of
[M15](m15-shallow-water-fno.md).

## The algorithm

### Emission factor (AP-42 §13.2.2, industrial roads)

$$
E = k\left(\frac{s}{12}\right)^{a}\left(\frac{W}{3}\right)^{b} \quad [\text{lb/VMT}], \qquad
E_{\text{ext}} = E\,\frac{365 - P}{365}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $E$ | emission factor per vehicle mile travelled | lb/VMT |
| $s$ | surface silt content | % |
| $W$ | mean vehicle weight | short tons |
| $P$ | days per year with at least 0.01 in of precipitation | days |
| $k$, $a$, $b$ | size-class constants | – |

The constants for PM10 ($k = 1.5$, $a = 0.9$, $b = 0.45$) and PM30 ($k = 4.9$, $a = 0.7$, $b = 0.45$), and the stated
applicability ranges (silt 1.8–25.2 %, $W$ 2–290 tons), were read only from search excerpts of the EPA text and are
**UNVERIFIED — pinned at specification** [1]; the PM2.5 constant is UNVERIFIED (two values in circulation) and is left
out until pinned. Large haul trucks can exceed the upper bound of $W$, an extrapolation that the C3 card states. The
watering control-efficiency curve is UNVERIFIED — pinned at specification. Conversion to SI:
1 lb/VMT $= 0.453592/1.609344 = 0.2818$ kg/VKT.

### Gaussian plume with ground reflection

For a continuous point source of strength $Q$ (g/s) at effective height $H$ (m), wind speed $u$ (m/s) along $x$:

$$
C(x,y,z) = \frac{Q}{2\pi u\,\sigma_y\sigma_z}\,
\exp\!\left(-\frac{y^2}{2\sigma_y^2}\right)
\left[\exp\!\left(-\frac{(z-H)^2}{2\sigma_z^2}\right) + \exp\!\left(-\frac{(z+H)^2}{2\sigma_z^2}\right)\right]
$$

$C$ is the concentration (g/m³) and $\sigma_y(x)$, $\sigma_z(x)$ (m) the lateral and vertical dispersion widths, which
grow with downwind distance according to the atmospheric stability class, from A (extremely unstable) to F (moderately
stable) [2]. The Pasquill–Gifford or Briggs coefficients for $\sigma(x)$ are UNVERIFIED — pinned at specification. A
haul road is a **line source**: the point kernel is integrated along the road (or replaced by the closed-form
crosswind line-source solution). Modern regulatory models (AERMOD) use Monin–Obukhov similarity instead [2]; PitStudio
stays with the screening-grade plume and says so.

### Lagrangian particles (Warp)

Each computational particle carries a mass of dust and moves with the wind, a random turbulent displacement and its
settling velocity†:

$$
d\mathbf X = \big(\mathbf U(\mathbf X) - v_s\,\hat{\mathbf z}\big)\,dt + \sqrt{2K}\, d\mathbf W
$$

with $\mathbf U$ the wind field over the terrain (m/s), $K$ an eddy diffusivity (m²/s) and $d\mathbf W$ a Wiener
increment. The settling velocity of a small sphere follows Stokes' law [4]:

$$
v_s = \frac{2}{9}\,\frac{(\rho_p - \rho_f)}{\mu}\, g R^2
$$

with particle and air densities $\rho_p$, $\rho_f$ (kg/m³), air dynamic viscosity $\mu$ (Pa·s) and particle radius $R$
(m), valid for particle Reynolds numbers below about 1 [4]. For a 10 µm particle ($R = 5$ µm) of density 2,650 kg/m³
in air of viscosity $1.8 \times 10^{-5}$ Pa·s (illustrative inputs), $v_s \approx 8.0$ mm/s: about 21 minutes to fall
10 m. Particles touching the ground deposit; concentrations are binned on a grid.

**Consistency check.** For uniform wind and constant $K$, the particle cloud's lateral spread obeys
$\sigma_y^2 = 2Kx/u$, so the Lagrangian model and the plume must agree on flat terrain — a built-in cross-test.

### Worked example (illustrative, using the unverified constants)

Silt 8 %, mean vehicle weight 200 short tons, PM10:
$E = 1.5 \times (8/12)^{0.9} \times (200/3)^{0.45} = 1.5 \times 0.694 \times 6.618 = 6.89$ lb/VMT, i.e. 1.94 kg/VKT. With 100 wet days, $E_{\text{ext}} = 1.94 \times 265/365 = 1.41$
kg/VKT. A 3 km road carrying 400 truck passes a day is 1,200 VKT/day, or about 1.7 t of PM10 per day before any
watering. These numbers illustrate the chain; the constants must be pinned before any result is published.

## Baseline and comparison

- **Plume vs particles** on flat terrain (consistency check above); on the real pit, the difference is reported as the
  effect of terrain.
- **Control scenarios** (watering interval, speed limits, road surface) are contrasted side by side on PM10 kg/VKT,
  receptor concentration and water use. No stochastic "better" claim.
- **Real data:** no gridded real dust measurements exist for the case pits, so dust fields are labelled "calibrated
  synthetic — not validated against real data", with no classifier two-sample test claim.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)):

- worked examples from primary sources once the AP-42 constants are pinned;
- analytic checks: Stokes settling, exact mass conservation of the particle model, plume–particle agreement on flat
  terrain within tolerances in `specs/000-foundation/thresholds.yaml`;
- metamorphic relations: concentration is linear in emission; ground-level centreline concentration falls with wind
  speed; more wet days never increase $E_{\text{ext}}$; emissions are non-decreasing in silt and vehicle weight;
- TypeScript port parity (exact class) for the closed-form parts.

**Results: Not yet run** — produced in the data-and-models phase. Reported: C3 emission and receptor tables per
scenario, concentration maps, water use.

## Lane and web delivery

**Live + precompute.** AP-42 and the plume are closed form and run live in a web worker (analytical-model gate: under
50 KB of JavaScript, 1–50 ms per evaluation; estimates). Warp particle runs over the terrain are precomputed in the
studio and baked as concentration tiles; a small WGSL particle demo is among the browser engines. Winds come from ERA5
statistics (CC BY, optional account) or, without it, NOAA hourly station data for Salt Lake City (terms verified before
use). Fallback: baked grids.

## Assumptions and limits

- AP-42 is a regression on field tests within its stated ranges; outside them (very heavy trucks) it extrapolates.
- The Gaussian plume assumes steady, horizontally homogeneous wind and flat terrain; pit walls violate both, which is
  why the particle model exists.
- No resuspension, no chemistry, no CFD. Results are screening-grade.
- **Educational, not an air-permitting or regulatory model.**

## In PitStudio

- **Cases:** [C3](../cases/c3-dust.md) (PM10 kg/VKT, receptor concentration, water use); dust inputs for B2 and B1 via
  [M10](m10-synthetic-data-detector.md) and [M23](m23-rtx-sensor-simulation.md).
- **Code (planned):** `minephys.environment` (AP-42, Gaussian plume, Beer–Lambert dust attenuation for lidar);
  particles in `studio/` (`pitstudio_studio.physics`, `st50_physics`); TypeScript port in `web/`. Data cards:
  [AP-42](../data-contract/dataset-cards/ap42.md), [ERA5 / GHCNh](../data-contract/dataset-cards/era5-ghcnh.md).
- **Status:** not yet implemented — built test-first in the build phase.

† Standard random-walk particle form; checked against the analytic diffusion solution at specification.

## References

1. US EPA — AP-42 §13.2.2 Unpaved Roads (November 2006 version; equation and constants read from search excerpts).
   https://www.epa.gov/sites/default/files/2020-10/documents/13.2.2_unpaved_roads.pdf
2. *Atmospheric dispersion modeling* — Gaussian plume with reflections, Pasquill classes A–F, AERMOD.
   https://en.wikipedia.org/wiki/Atmospheric_dispersion_modeling
3. NIOSH (2012). Dust control handbook for industrial minerals mining and processing.
   https://doi.org/10.26616/nioshpub2012112
4. *Stokes' law* — settling velocity of a small sphere; validity Re < 1. https://en.wikipedia.org/wiki/Stokes%27_law
