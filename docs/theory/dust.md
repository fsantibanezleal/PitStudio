# Dust

> Haul-road dust from source to receptor: the US EPA AP-42 unpaved-road emission factor with all its coefficients and
> validity ranges, watering control efficiency, Gaussian plume dispersion, Lagrangian particles and what dust does to
> sensors. · Part of: [Theory](README.md) · Related: [RTX sensor physics](rtx-sensor-physics.md),
> [M16 dust dispersion](../methods/m16-dust-dispersion.md), [Case C3](../cases/c3-dust.md),
> [AP-42 dataset card](../data-contract/dataset-cards/ap42.md)

## What and why

Haul trucks pulverise the road surface; their wheels and turbulent wakes lift the fines into the air [1]. The dust
affects workers' health, visibility, neighbours and, increasingly, the sensors of autonomous equipment. The regulatory
method for estimating it is the US EPA's AP-42, whose unpaved-roads section (§13.2.2) is current in its November 2006
version [1][2][3]. Dust control in practice (watering, suppressants, traffic rules) is documented in the NIOSH
handbook for industrial minerals [5].

The chain on this page is the one case C3 computes: traffic (from the haulage simulation) → emission factor →
control → dispersion → receptor concentration, and, in parallel, dust optical depth → lidar and camera degradation.

![Haul-road dust: AP-42 emission, Gaussian plume and receptor](../assets/diagrams/dust-plume.svg)

*A haul-road segment emits into a wind-driven plume that widens downwind; the side view shows vertical spread and the
ground-reflection image source.*

## 1. Emission: AP-42 §13.2.2, industrial unpaved roads

For vehicles on unpaved surfaces at industrial sites (equation 1a of the section) [1]:

$$
E = k\left(\frac{s}{12}\right)^{a}\left(\frac{W}{3}\right)^{b}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $E$ | size-specific emission factor | lb per vehicle mile travelled (lb/VMT) |
| $s$ | surface-material silt content: fraction passing a 200-mesh (75 µm) screen, ASTM C-136 | % |
| $W$ | **mean** weight of all vehicles on the road | short tons |
| $k$, $a$, $b$ | empirical constants (table below) | lb/VMT, –, – |

Conversion: 1 lb/VMT = 281.9 g per vehicle kilometre travelled (g/VKT) [1].

**Constants** (Table 13.2.2-2, industrial roads) [1]:

| Size class | $k$ (lb/VMT) | $a$ (–) | $b$ (–) | Quality rating |
|---|---|---|---|---|
| PM2.5 | 0.15 | 0.9 | 0.45 | B |
| PM10 | 1.5 | 0.9 | 0.45 | B |
| PM30 (taken as total suspended particulate) | 4.9 | 0.7 | 0.45 | B |

The PM2.5 multiplier comes from a January 2006 revision of the table [1]; it is scaled from the PM10 result because
fewer PM2.5 tests exist.

**Validity ranges** (Table 13.2.2-3, the source conditions used to develop equation 1a) [1]:

| Parameter | Range |
|---|---|
| Surface silt content | 1.8–25.2 % |
| Mean vehicle weight | 1.8–260 Mg (2–290 short tons) |
| Mean vehicle speed | 8–69 km/h (5–43 mph) |
| Mean number of wheels | 4–17 |
| Surface moisture content | 0.03–13 % |

The B rating holds only inside these ranges, and drops by two letters when a default silt value from the section's
table replaces a measured one [1]. Defaults are "strongly discouraged" when local data can be gathered; for mining
haul roads the section's table lists, for example, means of 8.3 % (stone quarrying, haul road to and from the pit),
5.8 % (taconite) and 8.4 % (western surface coal), with individual samples from 2.8 % to 18 %, and 18–29 % on a
freshly graded haul road [1].

$W$ is a **fleet average**, not a per-vehicle value: the section's own example is a road where 98 % of the traffic is
2-ton cars and 2 % is 20-ton trucks, so the mean weight is 2.4 tons and only one factor is computed [1]. Large
mining haul trucks push this mean to or past the 290-ton edge (for example, 400 t loaded and 180 t empty on a two-way
road average 290 t, which is 320 short tons): a documented extrapolation that PitStudio flags rather than hides.

**Natural mitigation by precipitation** (equation 2), with $P$ the number of days a year with at least 0.254 mm
(0.01 in) of precipitation [1]:

$$
E_{\text{ext}} = E\,\frac{365 - P}{365}
$$

The section warns that this simple assumption has not been verified rigorously and downgrades its rating by one
letter [1].

**Worked example 1** (illustrative: silt 10 %, mean weight 290 short tons, 150 wet days, 200 truck passes a day on a
2 km segment):

| Quantity | PM2.5 | PM10 | PM30 |
|---|---|---|---|
| $E$ (lb/VMT) | 0.996 | 9.96 | 33.7 |
| $E$ (kg/VKT) | 0.281 | 2.81 | 9.51 |

With 150 wet days, PM10 falls to 5.87 lb/VMT (1.65 kg/VKT). Uncontrolled, the segment emits
$400\ \text{VKT/day} \times 2.81$ kg/VKT = 1,123 kg of PM10 a day before precipitation; at 75 % watering control,
281 kg. Above the validity range, every extra 38 % of mean weight multiplies $E$ by about $1.38^{0.45} = 1.16$
(arithmetic), which shows how fast the extrapolation compounds.

## 2. Watering control efficiency

Watering raises the surface moisture and binds the fines; its effect fades as the road dries between water-truck
passes. AP-42 gives a simple bilinear relation between the instantaneous control efficiency $CE$ and the moisture ratio
$M$, the surface moisture of the watered road over that of the uncontrolled road (Figure 13.2.2-2) [1]. Read from the
figure:

$$
CE(M) = \begin{cases}
0 & M \le 1 \\
75\,(M - 1) & 1 < M \le 2 \\
75 + \tfrac{20}{3}\,(M - 2) & 2 < M \le 5
\end{cases} \quad [\%]
$$

that is, 0 % at the uncontrolled moisture, 75 % at twice that moisture and about 95 % at five times it. Between the
uncontrolled moisture and twice its value a small increase gives a large gain; beyond that the gain is slow [1].

The section's guidance shapes how PitStudio uses it:

- characterise a watered road by sampling surface moisture at several times between water-truck passes, during active
  traffic, preferably in hot summer conditions, and average $CE$ over the watering cycle [1];
- for prospective designs, the drying model (evaporation, traffic) is a planning tool and its estimate is downgraded
  two letters [1];
- an equivalent of 1 inch of precipitation is an application of 5.6 gallons of water per square yard [1];
- equation 1a does **not** apply to chemically stabilised roads [1].

## 3. Gaussian plume dispersion

For a continuous point source in a steady, uniform wind over flat ground, with reflection at the ground [4]:

$$
C(x,y,z) = \frac{Q}{2\pi\,u\,\sigma_y\,\sigma_z}\,\exp\!\Big(-\frac{y^2}{2\sigma_y^2}\Big)
\Big[\exp\!\Big(-\frac{(z - H)^2}{2\sigma_z^2}\Big) + \exp\!\Big(-\frac{(z + H)^2}{2\sigma_z^2}\Big)\Big]
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $C$ | concentration | g/m³ |
| $Q$ | emission rate | g/s |
| $u$ | wind speed along $x$ | m/s |
| $x$, $y$, $z$ | downwind, crosswind and vertical coordinates | m |
| $\sigma_y(x)$, $\sigma_z(x)$ | crosswind and vertical dispersion lengths | m |
| $H$ | effective source height | m |

The second exponential is the image source below the ground; the full form adds reflections from an inversion lid.
The dispersion lengths come from the Pasquill–Gifford curves or Briggs formulas for the six stability classes, A
(extremely unstable) to F (moderately stable) [4]; their coefficients are UNVERIFIED — pinned at specification.
Modern regulatory models such as AERMOD use Monin–Obukhov similarity instead [4].

**A road is a line source.** Integrate the point kernel along the road. For an infinite crosswind road at ground level
($H = 0$, receptor at $z = 0$), integrating $\exp(-y^2/2\sigma_y^2)$ over the road gives $\sqrt{2\pi}\,\sigma_y$ and
(arithmetic)

$$
C(x, 0) = \sqrt{\frac{2}{\pi}}\;\frac{q_\ell}{u\,\sigma_z(x)}, \qquad
q_\ell = \frac{E_{\text{g/VKT}} \times \text{traffic (vehicles/s)}}{1000}
$$

with $q_\ell$ the emission per metre of road (g/(s·m)).

*Worked example 2* (worked example 1 traffic; illustrative $u$ = 3 m/s and $\sigma_z$ = 20 m, not taken from the
stability-class curves): $q_\ell = 2807 \times (200/86{,}400)/1000 = 0.0065$ g/(s·m), so the ground-level
concentration downwind is $0.798 \times 0.0065/(3 \times 20) = 86$ µg/m³ of PM10 before control and precipitation. For
a point source at ground level, the centreline value is $Q/(\pi u \sigma_y \sigma_z)$: 1 g/s with $\sigma_y$ = 36 m,
$\sigma_z$ = 20 m and $u$ = 3 m/s gives 147 µg/m³ (all illustrative).

## 4. Lagrangian particles

Over real pit terrain, where walls and benches channel the wind, the plume formula no longer holds. Lagrangian
particles carry the dust instead: each particle is advected by the wind field, settles, and takes a random-walk step
for turbulent dispersion:

$$
d\mathbf x = \big(\bar{\mathbf u}(\mathbf x, t) - w_s\,\hat{\mathbf z}\big)\,dt + \sqrt{2K}\,d\mathbf W, \qquad
w_s = \frac{\rho_p\,g\,d_p^2}{18\,\mu}
$$

with $\bar{\mathbf u}$ the mean wind (m/s), $K$ an eddy diffusivity (m²/s), $d\mathbf W$ a Wiener increment, and the
settling velocity $w_s$ from Stokes drag on a particle of diameter $d_p$ (m) and density $\rho_p$ (kg/m³) in air of
viscosity $\mu$ (Pa·s). Stokes' law is classical (its primary citation is pinned at specification) and holds only
for small particles at low Reynolds number.

*Illustrative* ($\rho_p$ = 2,650 kg/m³, $\mu$ = 1.8 × 10⁻⁵ Pa·s): 2.5, 10 and 30 µm particles settle at 0.50, 8.0 and
72 mm/s, so they take 66 min, 4.2 min and 28 s to fall 2 m. PM2.5 and PM10 travel far; the coarse fraction falls next
to the road.

Two consistency checks tie the particles to the plume. A random walk with constant $K$ spreads a puff as
$\sigma = \sqrt{2Kx/u}$ (for example 18 m at 500 m with $K$ = 1 m²/s and $u$ = 3 m/s), so on flat ground with uniform
wind the particle cloud must reproduce the Gaussian plume with those $\sigma$. And the particle count is a mass
budget: emitted = airborne + deposited, to round-off.

## 5. Dust and sensors: Beer–Lambert

Dust attenuates light along a path. The transmittance over a path of length $L$ through a medium with extinction
coefficient $\beta_{\text{ext}}$ (1/m) is $T = \exp\!\big(-\int_0^L \beta_{\text{ext}}\,dl\big)$, and a lidar return
crosses the path twice, $T^2 = \exp(-2\beta_{\text{ext}} R)$ for a uniform cloud at range $R$. A field study of lidar
in airborne fines found that dust starts to affect measurements when the atmospheric transmittance falls below 71–74 %
(optical depth $-\ln T$ of 0.30–0.34), and that lidar still ranges retroreflective targets at transmittance as low as
2 % (optical depth 3.9) [6]. For cameras, a depth-based haze model $I = J\,t + A\,(1 - t)$ with $t = e^{-\beta d}$
is the standard approach [7]. PitStudio feeds $\beta_{\text{ext}}$ from the C3 dust field into both; the sensor
models are on [RTX sensor physics](rtx-sensor-physics.md).

## Assumptions and limits

- **AP-42 is a regression.** It is valid inside its tested ranges. Mining haul trucks sit at or beyond the weight
  edge, and that extrapolation is flagged, not hidden. Watering and precipitation adjustments carry downgraded ratings
  by the section's own rules [1].
- **Plume assumptions.** Steady wind, flat terrain, uniform stability and no deposition; pit topography breaks all
  four, which is why the particle model exists.
- **Stokes regime only.** No deposition-velocity or resuspension model beyond settling.
- **No CFD.** Large-eddy simulation of pit dust was rejected for its cost and lack of decision value over AP-42 plus
  dispersion.
- **No real dust field.** There is no open measured dust field to validate against. Dust fields are labelled
  "calibrated synthetic — not validated against real data" and get no C2ST or train-synthetic-test-real claim.
- **Educational, not regulatory.** PitStudio is not a regulatory dispersion model; regulatory work uses AERMOD-class
  tools and site meteorology.

## In PitStudio

| Where | What | Lane |
|---|---|---|
| `minephys.environment` | AP-42 emission factors and validity checks, watering control efficiency, Gaussian plume, Beer–Lambert dust attenuation for lidar | live (TypeScript port + Pyodide button) |
| `studio/src/pitstudio_studio/physics/` (`st50_physics`) | Warp Lagrangian particles over the pit terrain | precompute → replay |
| [M16](../methods/m16-dust-dispersion.md) | AP-42 + Gaussian plume + Lagrangian dust | live + precompute |
| [M15](../methods/m15-shallow-water-fno.md) | FNO-2D surrogate of tailings and dust fields | precompute → live |
| [M23](../methods/m23-rtx-sensor-simulation.md) | truck lidar in dust with the own Beer–Lambert model; live dust slider | precompute + live |
| [Case C3](../cases/c3-dust.md) | PM10 kg/VKT, receptor concentration, water use, with traffic from A1 | — |

Wind comes from ERA5 single levels (optional account) or, as the no-account fallback, NOAA GHCNh hourly station data
([dataset card](../data-contract/dataset-cards/era5-ghcnh.md)).

**Status: Not yet run** — produced in the data-and-models phase. Pre-registered acceptance (from the plan): the FNO-2D
surrogate of the dust and tailings fields reaches a relative L2 error ≤ 5 % on held-out terrains. The analytical
models are tested against the worked examples above and the plume–particle consistency checks.

## References

1. US EPA (2006). AP-42, Fifth Edition, Volume I, §13.2.2 Unpaved Roads (November 2006): equations 1a and 2, Tables
   13.2.2-1 to 13.2.2-3, Figure 13.2.2-2. https://www.epa.gov/sites/default/files/2020-10/documents/13.2.2_unpaved_roads.pdf
2. US EPA. AP-42 §13.2.2 Unpaved Roads, related information (current version November 2006).
   https://19january2021snapshot.epa.gov/air-emissions-factors-and-quantification/ap-42-section-1322-unpaved-roads-related-information-0_.html
3. US EPA. AP-42, Fifth Edition, Volume I, Chapter 13: Miscellaneous Sources (section dates).
   https://www.epa.gov/air-emissions-factors-and-quantification/ap-42-fifth-edition-volume-i-chapter-13-miscellaneous-0
4. Atmospheric dispersion modeling (Gaussian plume with reflections; Pasquill stability classes).
   https://en.wikipedia.org/wiki/Atmospheric_dispersion_modeling
5. NIOSH (2012). *Dust control handbook for industrial minerals mining and processing.*
   https://doi.org/10.26616/nioshpub2012112
6. Phillips, Guenther, McAree (2017). When the dust settles: the four behaviors of LiDAR in the presence of fine
   airborne particulates. *J. Field Robotics* 34(5), 985–1009. https://doi.org/10.1002/rob.21701
7. Narasimhan, Nayar (2002). Vision and the atmosphere. *Int. J. Comput. Vis.* 48(3), 233–254.
   https://doi.org/10.1023/A:1016328200723
