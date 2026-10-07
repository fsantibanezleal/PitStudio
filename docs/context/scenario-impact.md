# Scenario impact

> The sourced cost, energy, safety and environmental anchors behind PitStudio's twelve cases, the scoring that
> selected them, and the widely quoted numbers that are deliberately left out. · Part of: [context](README.md) ·
> Related: [mining value chain](mining-value-chain.md) · [open-pit operations](open-pit-operations.md) ·
> [case catalogue](../cases/README.md) · [coverage matrix](../cases/coverage-matrix.md)

## What and why

A simulation studio can spend its GPU hours anywhere. PitStudio spends them where three things meet: a **large,
published impact** on cost, energy or safety; a phenomenon that **can genuinely be simulated** with the stack on one
16 GB GPU; and **something real to validate against**, either public data or an analytical ground truth. This page
records the evidence for the first condition and the scoring that combined all three. Every number below is quoted
for the scope its source states. None is a PitStudio result.

## Impact anchors

### Cost and energy

| Anchor | Value | Scope | Source |
|---|---|---|---|
| Haulage share of open-pit operating cost | up to 60 % | truck–shovel systems | [1] |
| Milling share of operating cost | 59.1 % (6.18 USD/t) | one open-pit copper operation, 2025 costing study | [2] |
| Crushing share of operating cost | 11 % (1.15 USD/t) | same operation | [2] |
| Grinding share of mining energy | 40 % | US mining energy bandwidth, as cited | [3] [4] |
| Diesel materials-handling share of mining energy | 17 % | same | [3] [4] |
| Trolley assist: diesel saved | 830,000 L per year | one Swedish copper mine, 2018 | [5] |
| Trolley assist: CO₂e saved | 79 kg per truck cycle on the trolley section, with more than twice the ramp speed | a Canadian pilot | [5] |
| Trolley assist: route emissions | 80 % lower transport GHG along trolley routes | one operator's report | [5] |
| Payload-variance control | up to 35 % less haul-truck fuel (payload variance tested from 0 to 30 %) | an Australian open-cut coal mine | [6] |
| Crusher-jamming boulders | seven-minute delays costing up to USD 650,000 per year | one operation, cited in a vendor blog | [7] |
| Mine-to-mill meta-models | more than 3 million simulated scenarios; random-forest accuracy above 90 %; finer fragmentation lowers total comminution cost despite higher explosive cost | 2026 study | [8] |

### Safety

| Anchor | Value | Scope | Source |
|---|---|---|---|
| Powered-haulage fatalities | 13 of 33 (39 %) | US mining, 2025 | [9] |
| Powered-haulage non-fatal injuries | 426 of 4,792 (9 %) | US mining, 2025 | [9] |
| Seat-belt use | could save three to four miners' lives each year | MSHA estimate | [9] |
| Powered haulage and machinery | 10 of 40 fatalities were powered haulage; machinery and powered haulage together 65 % | US mining, 2023 | [10] |
| ICMM member fatalities | 42 in 2024 (36 in 2023, 33 in 2022); 9 mobile equipment and transportation, 5 fall of ground | ICMM members | [11] |
| Mobile equipment share | 26 % of all fatalities; 67 % linked to ineffective critical-control execution | ICMM members, 2021–2024 | [12] |
| Flyrock and blast-area security | more than two-thirds of blasting-related injuries | US surface coal, metal and non-metal mines, 1978–2002 | [13] |
| Surface mobile equipment rule | final rule published 20 December 2023 | MSHA | [14] |

### Ground and environment

| Anchor | Value | Scope | Source |
|---|---|---|---|
| 2013 open-pit slide | 165 million tons moved; radar every 6–8 min; 2 in/day before failure; no injuries among ~500 workers; refined-copper output expected −50 % | a large US copper mine | [15] |
| 2019 tailings failure (Brumadinho) | nearly 10 million m³ released; more than 270 lives lost; upstream-raised dams overrepresented in failure statistics | summary of a 2022 statistical study | [16] [17] |
| 2007 tailings failure (Miraí) | 3.8 Mm³ from a 34 m dam; peak breach outflow 422 m³/s; flood arrival 2.5–4 h; about 1,033 people exposed; no deaths | reproduced with HEC-RAS and HEC-LifeSim | [18] |
| Tailings standard | GISTM launched 5 August 2020: 15 principles, 77 auditable requirements; conformance by 5 August 2023 for "extreme / very high" consequence facilities and by 5 August 2025 for the rest | ICMM | [19] |
| Tailings inventory | 1,805 tailings storage facilities at 692 mine sites (licence of the portal not stated) | Global Tailings Portal | [20] |
| Haul-road dust method | AP-42 §13.2.2 *Unpaved Roads*, current section November 2006 | US EPA | [21] |

## How the twelve cases were chosen

Each candidate scenario was scored from 1 (low) to 5 (high) on five axes. The scores are the maintainer's research
judgement from the evidence above, not measurements:

- **Impact:** size of the published cost, energy or safety effect.
- **Simulability:** how faithfully the governing physics or logic can be computed.
- **Validation:** availability of real data or an analytical ground truth.
- **Web:** how well it explains interactively in a browser.
- **GPU:** how much it genuinely uses the 16 GB RTX GPU (rendering, particles, vectorised learning, synthetic data).

| Scenario | Impact | Simul. | Valid. | Web | GPU | Sum | Outcome |
|---|---|---|---|---|---|---|---|
| Truck–shovel cycle, dispatch, fleet sizing | 5 | 5 | 3 | 5 | 4 | 22 | **A1** |
| Drone survey → volumetric reconciliation | 3 | 5 | 5 | 5 | 4 | 22 | **E2** |
| Haul-road physics and trolley/battery energy | 5 | 5 | 3 | 5 | 3 | 21 | **A2** |
| Autonomous–manned interaction and synthetic perception | 5 | 4 | 3 | 4 | 5 | 21 | **B1**, **B2** |
| Drill and blast (fragmentation, PPV, flyrock, muck pile) | 4 | 4 | 3 | 5 | 4 | 20 | **D1** |
| Slope radar → time of failure | 5 | 4 | 3 | 5 | 2 | 19 | **C1** |
| Tailings breach run-out | 5 | 3 | 3 | 4 | 4 | 19 | **C2** |
| Crusher oversize detection | 3 | 5 | 2 | 4 | 5 | 19 | merged into **B2** |
| Loading: bucket fill, payload variance | 4 | 4 | 2 | 4 | 5 | 19 | **A3** |
| Pit shell, pushbacks → life-of-mine haul distance | 4 | 5 | 4 | 4 | 1 | 18 | **E1** |
| Haul-road and blast dust, water trucks | 3 | 4 | 3 | 5 | 3 | 18 | **C3** |
| Chutes and stockpile blending | 3 | 4 | 2 | 4 | 5 | 18 | demoted: weak public validation data |
| Mine-to-mill: fragmentation → SAG throughput, kWh/t | 5 | 3 | 3 | 4 | 2 | 17 | **D2** |
| Pit flooding and dewatering | 2 | 4 | 2 | 4 | 4 | 16 | kept as a variant of C2 (same solver) |
| Emergency response and fire training | 3 | 3 | 1 | 3 | 4 | 14 | rejected: no validation data |
| Flotation soft sensor | 3 | 2 | 3 | 3 | 1 | 12 | rejected: not a physics or rendering use |

Two observations from the table. Categories A and D carry the **cost and energy** story; B and C carry the **safety**
story; E carries the **geometry** story with the strongest validation (a scene of exactly known volume). And the cases
where the 16 GB GPU is load-bearing (A3, B2, C2, D1, E2) sit next to cases that run fully live in the browser (A1, A2,
C1, C3, D2, E1), so the web app can always show something computed in front of the visitor.

## The KPI of each case

| Case | KPI reported | Impact anchor it speaks to |
|---|---|---|
| [A1](../cases/a1-truck-shovel-dispatch.md) | t/h, queue time, match factor, cost/t | haulage share of opex [1] |
| [A2](../cases/a2-haul-road-electrification.md) | L/t·km, kWh/t, CO₂e/t | diesel materials handling [3]; trolley results [5] |
| [A3](../cases/a3-loading-payload-variance.md) | payload CV, passes per truck, fuel/t | payload-variance control [6] |
| [B1](../cases/b1-traffic-proximity.md) | minimum time-to-collision, near-misses per 1,000 h | powered haulage and mobile equipment [9] [12] |
| [B2](../cases/b2-synthetic-perception.md) | synthetic held-out mAP, randomisation ablation, corruption robustness | mobile equipment [12]; crusher boulders [7] |
| [C1](../cases/c1-slope-time-of-failure.md) | FoS, PoF, forecast error, lead time | 2013 slide [15]; fall of ground [11] |
| [C2](../cases/c2-tailings-breach.md) | arrival time, depth, inundated area | tailings failures [16] [18]; GISTM [19] |
| [C3](../cases/c3-dust.md) | PM10 kg/VKT, receptor concentration, water use | AP-42 method [21] |
| [D1](../cases/d1-blast-muck-pile.md) | P80, % oversize, PPV, flyrock radius; measured sim-to-real | flyrock injuries [13] |
| [D2](../cases/d2-mine-to-mill.md) | t/h, kWh/t, cost/t | milling and grinding shares [2] [3]; meta-models [8] |
| [E1](../cases/e1-pit-shell-pushbacks.md) | NPV, strip ratio, haul km per lift | haulage share of opex [1] |
| [E2](../cases/e2-survey-reconciliation.md) | volume error %, real excavated volume 2018 → 2023 | survey validation by construction |

## Numbers deliberately left out

Some figures circulate widely but could not be read in a primary source when this page was written. PitStudio does not
show them in tables or the web app until they are pinned to a readable primary text:

- the share of mine-site energy attributed to comminution in Ballantyne and Powell (2014) [22] (the paper is
  identified; its abstract was not readable);
- an often-quoted SAG throughput gain from mine-to-mill programmes;
- productivity gains quoted for autonomous haulage systems;
- rolling-resistance rules of thumb (speed loss and extra fuel per percent of rolling resistance);
- the AP-42 §13.2.2 constants and the watering control-efficiency curve (pinned at specification for C3);
- aggregate tailings-failure statistics (counts, fatalities, rainfall share) beyond the summary in [16];
- statistics on fires on mobile plant.

Where such a value is needed as a model constant, it carries **UNVERIFIED — pinned at specification** until the
specification phase reads the primary source.

## Assumptions and limits

- **Context, not results.** The anchors explain why a case matters. They are not calibration targets unless a case
  page says so explicitly.
- **Scope-bound.** A cost share from one copper operation, or a fuel saving from one coal mine, does not transfer to
  another site. Pages quote the scope together with the number.
- **Sensitive events.** Slope and tailings disasters are cited factually. Cases are illustrative and never recreate an
  identifiable community at risk.
- **Generic names.** Operations appear as sources of evidence, not as branding; tables use generic descriptions ("a
  Swedish copper mine").

## In PitStudio

- The web app shows the relevant anchor, with its source, in each case's *Context* sub-tab and in the case catalogue.
- KPIs are produced by the methods listed on each case page. **Not yet run** — produced in the data-and-models phase;
  each case page lists its pre-registered acceptance criterion.

## References

1. May, M. A. (2013). *Applications of Queuing Theory for Open-Pit Truck/Shovel Haulage Systems.* Virginia Tech thesis.
   https://vtechworks.lib.vt.edu/items/fecf61c3-860b-4671-91ed-09549ddad265
2. Mboyo et al. (2025). Distribution of operating costs along the value chain of an open-pit copper mine. *Applied
   Sciences.* https://doi.org/10.3390/app15031602
3. *Improve Energy Efficiency in Surface Mines Using Artificial Intelligence.* IntechOpen chapter.
   https://doi.org/10.5772/intechopen.101493
4. U.S. Department of Energy (2007). *Mining Industry Energy Bandwidth Study.* https://doi.org/10.2172/1218653
5. CIM Magazine. All in on trolley assist. https://magazine.cim.org/en/net-zero-challenge/all-in-on-trolley-assist-en/
6. International Mining (2016-12-07). Mining3 project looks at effect of payload variance on haul truck fuel
   consumption. https://im-mining.com/2016/12/07/mining3-project-looks-effect-payload-variance-haul-truck-fuel-consumption/
7. NVIDIA blog (2025-10-29). Into the Omniverse: open world foundation models generate synthetic worlds for physical AI
   development. https://blogs.nvidia.com/blog/scaling-physical-ai-omniverse/
8. Nobahar, Xu, Dowd (2026). Cost-integrated AI meta-models for mine-to-mill optimisation. *Minerals.*
   https://doi.org/10.3390/min16010073
9. MSHA. Powered Haulage Safety. https://www.msha.gov/safety-and-health/safety-and-health-initiatives/powered-haulage-safety
10. Pit & Quarry. Mining fatalities totaled 40 in 2023. https://www.pitandquarry.com/mining-fatalities-totaled-40-in-2023/
11. ICMM (2025). 2024 safety performance. https://www.icmm.com/en-gb/news/2025/2024-safety-performance
12. ICMM (2025). 2020–2024 Safety Performance: Insights.
    https://www.icmm.com/en-gb/research/health-safety/2025/insights-2020-2024-safety-data
13. Bajpayee, Lobb, Verakis (2004). *An Analysis and Prevention of Flyrock Accidents in Surface Blasting
    Operations.* NIOSH. https://stacks.cdc.gov/view/cdc/220760
14. Federal Register (2023-12-20). Safety Program for Surface Mobile Equipment (final rule).
    https://www.federalregister.gov/documents/2023/12/20/2023-27640/safety-program-for-surface-mobile-equipment
15. High Country News. How technology detected a huge mine landslide before it happened.
    https://www.hcn.org/issues/45-8/how-technology-detected-a-huge-mine-landslide-before-it-happened/
16. NGI / ScienceNorway. This determines how dangerous a dam failure can be.
    https://partner.sciencenorway.no/geology-natural-sciences-ngi/this-determines-how-dangerous-a-dam-failure-can-be/2568663
17. Piciullo et al. (2022). A new look at the statistics of tailings dam failures. *Engineering Geology* 303.
    https://doi.org/10.1016/j.enggeo.2022.106657
18. Silva, Eleutério (2023). Tailings dam-breach case study (Miraí, 2007). *Natural Hazards and Earth System Sciences*
    23:3095. https://doi.org/10.5194/nhess-23-3095-2023
19. ICMM. Global Industry Standard on Tailings Management.
    https://www.icmm.com/en-gb/our-principles/tailings/global-industry-standard-on-tailings-management
20. Global Tailings Portal. https://tailing.grida.no/
21. US EPA. AP-42, Fifth Edition, Volume I, Chapter 13.
    https://www.epa.gov/air-emissions-factors-and-quantification/ap-42-fifth-edition-volume-i-chapter-13-miscellaneous-0
22. Ballantyne, Powell (2014). *Minerals Engineering* 65:109–114.
    https://doi.org/10.1016/j.mineng.2014.05.017
