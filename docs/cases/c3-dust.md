# C3 — Haul-road and blast dust, water trucks

> How much PM10 does pit traffic raise, how much of it reaches a receptor under real wind statistics, and how much
> water does it take to control — with the same dust field feeding the trucks' lidar. · Part of: [Cases](README.md) ·
> Related: [Dust theory](../theory/dust.md) · [M16 Dust dispersion](../methods/m16-dust-dispersion.md) ·
> [AP-42 card](../data-contract/dataset-cards/ap42.md) · [B1](b1-traffic-proximity.md)

## What and why

**The question.** An environmental officer preparing a permit, or a mine superintendent scheduling water trucks,
asks: given the traffic on each haul road, its silt content and vehicle weights, how many kilograms of PM10 are
emitted per vehicle-kilometre; what concentration reaches a receptor (an office, the pit rim, a community boundary)
under the site's wind regime; and how much water does a watering schedule use for a given control target? The
autonomy team asks the coupled question: how much does that dust degrade the trucks' lidar ([B1](b1-traffic-proximity.md))?

**Why it matters.**

- The US EPA's AP-42 §13.2.2 *Unpaved Roads* (final section, November 2006) is the regulatory emission-factor method
  for haul-road dust; §13.2.4 covers aggregate handling and storage piles [1].
- Dust-control practice for mining and processing is documented in a NIOSH handbook [2].
- Dust is also a sensing hazard: lidar ranging degrades once atmospheric transmittance drops below 71–74 % [3].

## Site and data

| Input | Kind | Source and licence | Card |
|---|---|---|---|
| Wind speed, direction and stability statistics | **real** | ERA5 single levels, CC BY (needs an optional CDS account) [4]; fallback: NOAA GHCNh hourly station data for Salt Lake City (US Government data, terms verified before use) | [era5-ghcnh](../data-contract/dataset-cards/era5-ghcnh.md) |
| Emission-factor equation and constants | real (regulatory method) | AP-42 §13.2.2, public domain [1][5] | [ap42](../data-contract/dataset-cards/ap42.md) |
| Terrain | **real** | USGS 3DEP Bingham Canyon | [bingham-3dep](../data-contract/dataset-cards/bingham-3dep.md) |
| Traffic per road segment (vehicle-km, weights) | **synthetic** | A1 DES ([M2](../methods/m02-haulage-des.md)) | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |
| Plume and particle concentration fields | **synthetic** | own models; CC-BY-4.0 | [synthetic-data](../data-contract/dataset-cards/synthetic-data.md) |

There is no gridded real concentration dataset for this site. Dust fields are labelled **"calibrated synthetic — not
validated against real data"**, and the plume is labelled **screening, not AERMOD** (AERMOD is EPA's preferred
regulatory model [6]).

## Methods and baseline

| Rung | Method | Role in C3 |
|---|---|---|
| Classical | [M16 AP-42 emission factor](../methods/m16-dust-dispersion.md) | $E = k\,(s/12)^{a}\,(W/3)^{b}$ lb per vehicle-mile, with silt content $s$ (%) and mean vehicle weight $W$ (short tons), extrapolated by $(365-P)/365$ for $P$ wet days [5] |
| Classical | [M16 Gaussian plume](../methods/m16-dust-dispersion.md) | Ground-reflected plume per Pasquill stability class, integrated along each road as a line source [7] |
| SOTA | [M16 Lagrangian dust](../methods/m16-dust-dispersion.md) | GPU particles over the pit terrain (Warp), for in-pit recirculation the flat-terrain plume cannot show |
| Classical | [M2 Haulage DES](../methods/m02-haulage-des.md) | Vehicle-kilometres per segment and hour from the A1 schedule |

**Baseline.** The Lagrangian particles are compared with the Gaussian plume where the plume's assumptions hold
(flat terrain, steady wind), and checked for mass balance and monotone decay with distance.

## KPIs

| KPI | Unit | How it is computed |
|---|---|---|
| Emission intensity | kg PM10 per vehicle-km (kg/VKT) | AP-42 factor in lb/VMT × 0.4536 kg/lb ÷ 1.609 km/mile |
| Receptor concentration | µg/m³ (hourly, and averaged over the wind record) | Plume (or particle) concentration at receptor points, weighted by the frequency of each wind and stability class |
| Water use | m³ per shift | Watering passes from the schedule × road area watered × application depth (inputs) |

The AP-42 constants for PM10 ($k$ = 1.5 lb/VMT, $a$ = 0.9, $b$ = 0.45; AP-42 §13.2.2 (11/06), Table 13.2.2-2, p. 13.2.2-5) and the stated applicability range
(silt 1.8–25.2 %, W 2–290 tons; Table 13.2.2-3, p. 13.2.2-5) are verified on the primary PDF [5]. The watering control-efficiency
curve is still **UNVERIFIED — pinned at specification**. Until pinned, the water-use KPI is computed but its
control efficiency is not claimed.

## Studio tools and artefacts

| Tool | Artefacts it produces for C3 |
|---|---|
| [Warp](../frameworks/warp.md) (`st50_physics`) | Lagrangian particle runs; concentration fields (Zarr); replay shards |
| [ovrtx](../frameworks/ovrtx.md) (`st53_sensors`) | Lidar frames inside the dust field (dust-in-lidar), via our Beer–Lambert attenuation |
| [minephys](../frameworks/minephys.md) `environment` | AP-42, Gaussian plume, Beer–Lambert dust attenuation |

## Web delivery

| Sub-tab | Element | Lane | Engine / asset |
|---|---|---|---|
| Scene | Pit with plume overlay and receptors | LIVE | three.js / R3F |
| Simulate | Silt, weight, traffic and wind-class controls → kg/VKT and receptor µg/m³ | LIVE | TS port of `minephys.environment`; Pyodide button |
| Simulate | Small particle twin over the terrain | LIVE | WGSL compute (T1) |
| Studio replay | Warp particle replays; lidar-in-dust frames | REPLAY | shards; frames |
| Charts | Emission vs traffic; concentration roses; water use vs schedule | LIVE / REPLAY | baked wind statistics |
| Context | Question, regulation context, honesty notes | STATIC | — |

## Assumptions and limits

- **Extrapolation.** Large mining haul trucks sit at or beyond the upper end of AP-42's weight range; results for
  them are an extrapolation and are labelled as such.
- **Screening dispersion.** The Gaussian plume ignores terrain channelling and in-pit recirculation; Pasquill–Gifford
  coefficients are UNVERIFIED until pinned. The Lagrangian lane is illustrative, not regulatory.
- **Wind source.** ERA5 is 0.25°, coarse for in-pit flow; the GHCNh fallback is a single station.
- Not a permit model and not a substitute for monitoring.

## Reproduce this

```bash run deferred=P6
uv run studio plan studio/recipes/cases/c3.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/c3.yaml --profile laptop-rtx5000ada
uv run studio publish <run-id>
```

Without a CDS account the recipe uses the GHCNh fallback, and the run manifest records which wind source was used.

## Results

**Not yet run** — produced in the data-and-models phase. What will be reported:

- kg PM10/VKT per road class and traffic scenario from A1; receptor concentrations averaged over the wind record;
  water use per shift for each watering schedule.
- Analytic checks: mass balance, ground reflection and monotone decay with distance; plume vs particles where both
  apply.
- No C2ST or real-data validation claim (no real gridded reference).

## In PitStudio

- Recipe `studio/recipes/cases/c3.yaml`; route `/cases/C3`.
- Shares its dust field with the lidar model of [B1](b1-traffic-proximity.md) and the structured randomisation of
  [B2](b2-synthetic-perception.md).

## References

1. US EPA. *AP-42, Fifth Edition, Volume I, Chapter 13: Miscellaneous Sources* (§13.2.2 and §13.2.4 dated Nov 2006).
   https://www.epa.gov/air-emissions-factors-and-quantification/ap-42-fifth-edition-volume-i-chapter-13-miscellaneous-0
2. NIOSH (2012). *Dust control handbook for industrial minerals mining and processing*. DOI 10.26616/nioshpub2012112
3. Phillips, Guenther, McAree (2017). *When the Dust Settles …*. J. Field Robotics 34(5):985–1009. DOI
   10.1002/rob.21701
4. Copernicus Climate Change Service. *ERA5 hourly data on single levels*. DOI 10.24381/cds.adbb2d47.
   https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
5. US EPA. *AP-42 §13.2.2 Unpaved Roads*. https://www.epa.gov/sites/default/files/2020-10/documents/13.2.2_unpaved_roads.pdf
6. US EPA. *Air Quality Dispersion Modeling — Preferred and Recommended Models*.
   https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models
7. Atmospheric dispersion modeling (Gaussian plume with ground reflection; Pasquill classes A–F).
   https://en.wikipedia.org/wiki/Atmospheric_dispersion_modeling
