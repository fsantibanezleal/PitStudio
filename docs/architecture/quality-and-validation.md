# Quality and validation

> How PitStudio proves that its code, data, models and site are right: specifications before code, failing tests
> first, metamorphic relations and physics benchmarks, a pre-registered decision rule for every "better" claim, parity
> layers, data validation and a quality gate at the end of every milestone. · Part of: [architecture](README.md) ·
> Related: [sim-to-real](../theory/sim-to-real.md) · [export, parity and acceleration](../models/export-parity-acceleration.md) ·
> [DEC-0016](decisions/DEC-0016-pre-registered-decision-rule.md) · [lanes](lanes.md)

## What and why

PitStudio publishes numbers about safety, energy and cost. A wrong number that looks precise is worse than no number,
so validation is designed in from the start rather than added at the end. Four principles from the project
constitution (`specs/constitution.md`) drive everything on this page:

1. **Spec before code.** No behaviour exists without an approved requirement ID in EARS form
   (`FR`, `NFR`, `SC`, `P` or `DC`-`NNN`-`xx`).
2. **Acceptance tests first.** Every requirement-bearing task starts with committed, failing, locked tests that reference
   its IDs (the `[red]` commit); the implementation (`[green]`) never modifies a locked test.
3. **Independent oracles.** Expected values come from analytical solutions, reference implementations, published values
   or hand calculation, never from running the code under test.
4. **Explicit tolerances.** Seeds, deterministic algorithms where available, pinned data checksums, and justified
   numerical tolerances per data type.

Thresholds live in `specs/000-foundation/thresholds.yaml` and only ratchet upwards; lowering one needs a specification
change and the maintainer's explicit approval.

## What is tested, test-first

Locked failing tests are written first for:

- every `minephys` model, using worked examples from the primary sources;
- the contracts (manifest, recipe, tool registry) and scene invariants;
- the physics benchmarks below;
- the discrete-event haulage simulation, against an exact event trace;
- the runner: cache keys, locks, guards, resume, out-of-memory fallback and job-object cleanup, using a fake GPU backend;
- the console's HTTP contract (Schemathesis generates hostile requests; every one must get a 4xx, never a 500 or a hang);
- the parity layers, the budgets, the showcase rules and the web app's hostile-input suite.

Tests live under `tests/` by kind: `unit/`, `property/`, `metamorphic/`, `contract/`, `parity/`, `pipeline/` and `gpu/`.
Tests that need CUDA carry the `gpu` marker and never run in CI.

## Metamorphic relations

A metamorphic relation checks how the output must change when the input changes in a known way. It catches errors
that a single reference value cannot, and it needs no oracle for the absolute value. Every numerical core has at least
three. The examples below show the kind of relation; the specifications fix the actual set.

| Core | Relation (illustrative) | Why it must hold |
|---|---|---|
| Match factor | Multiplying $N_T$ and $N_L$ by the same $k$ leaves $MF$ unchanged; so does multiplying $t_L$ and $T_c^{\ast}$ by the same $k$ | $MF = N_T t_L / (N_L T_c^{\ast})$ is homogeneous of degree zero in each pair |
| Bond energy | $W = 0$ when $P_{80} = F_{80}$; $W$ increases as $P_{80}$ decreases at fixed $F_{80}$ | Definition of the energy–size relation |
| Limit equilibrium | Raising the cohesion $c'$ never lowers the factor of safety; translating the whole slope geometry leaves it unchanged | Strength enters only the numerator; the method is translation-invariant |
| Haulage DES | Scaling every duration by $k$ scales every event time by $k$ and divides throughput by $k$ | Time units are arbitrary in a discrete-event model |
| Gaussian plume | Concentration is proportional to the source strength $Q$ | The plume equation is linear in $Q$ |
| Beer–Lambert dust attenuation | Transmittance through two consecutive path segments equals the product of their transmittances | $T = e^{-\int \sigma\,ds}$ |

## Physics benchmarks

GPU physics is validated against laboratory laws and benchmark experiments, not against itself:

| Benchmark | Law or data | Used for | Tolerance |
|---|---|---|---|
| Silo discharge | Beverloo law: mass flow $W = C\,\rho_b\sqrt{g}\,(D - k d)^{5/2}$, with discharge coefficient $C$ (–), bulk density $\rho_b$ (kg/m³), orifice diameter $D$ (m), grain diameter $d$ (m) and shape constant $k$ (–) [1]; a recent DEM validation with Hertz–Mindlin contacts reports $C = 0.56$ and the 5/2 exponent, with $C$ fitted on the particle density (3,000 kg/m³), not $\rho_b$ [2] | Warp DEM, Newton MPM | discharge ±5 % |
| Angle of repose | Calibration targets from the literature [3] | DEM calibration (M09) | ±1.5° |
| Granular column collapse | Run-out scaling with the aspect ratio [4] [5] [6] | DEM, MPM, GNS surrogate | run-out ±5 % |
| Dam break | Martin and Moyce's liquid-column collapse [7]; the SPHERIC 3-D dam-break data [8] [9] | GPU shallow water (M15) | specified per test |
| Stokes settling | Analytical terminal velocity | Dust particles (M16) | specified per test |
| Mass conservation | Total mass before and after | Every particle and field solver | drift < 0.5 % |

## The pre-registered decision rule

Every "better than" claim in the web app or these pages follows one rule, fixed before any result exists
([DEC-0016](decisions/DEC-0016-pre-registered-decision-rule.md)):

> A result is called better only if the paired 95 % confidence interval of the difference excludes 0. Otherwise the
> UI says "no significant difference".

For $n$ paired evaluations (the same seeds, events or images for both methods), let $d_i = m_i^\text{new} -
m_i^\text{base}$ be the difference in the task metric, oriented so that positive means better. With the paired-$t$
interval, for example,

$$
\bar d \pm t_{0.975,\,n-1}\,\frac{s_d}{\sqrt n}
$$

where $\bar d$ is the mean and $s_d$ the standard deviation of the $d_i$ (units of the metric), and $t_{0.975,n-1}$ the
Student quantile (–). The claim "better" requires the whole interval to lie above 0. The interval method for each
comparison is fixed in its specification.

Special cases, all fixed in advance:

- **Dispatch policies** (PPO and attention versus SPTF and LP): at least 30 paired seeds; decision on t/h.
- **Cosmos Reason 2 versus its Qwen3-VL base** on binary questions: "better" only if McNemar's test gives $p < 0.05$;
  never a headline KPI.
- **The single real slope-failure series** ($n = 1$): time-of-failure error at the 50 % and 80 % record cut-offs is
  reported descriptively, with "single real event — no significance test" on screen.

The rule is unit-tested in the build phase and checked on the real artefacts in the data-and-models and web reviews.

## Model acceptance criteria

**Not yet run** — produced in the data-and-models phase. These criteria were fixed before any training; they are
calibrated in `thresholds.yaml` during specification.

| Model | Pre-registered acceptance criterion |
|---|---|
| D-FINE-N / D-FINE-S detectors | synthetic held-out mAP50 ≥ 0.70 (N), ≥ 0.80 (S); relative drop ≤ 10 percentage points at corruption severity ≤ 2; "structured randomisation is better" only by the decision rule |
| RF-DETR-Seg-N | synthetic held-out mask AP50 ≥ 0.70; fp16 change ≤ 1 percentage point |
| Fragmentation U-Net | synthetic held-out $x_{50}$ relative error ≤ 15 %; real test split TSTR ≥ 0.90 × TRTR (IoU); "beats watershed + Swebrec" only by the decision rule on $x_{50}$ error |
| GNS granular surrogate | repose ±1.5° and run-out ±5 % on held-out geometries |
| FNO fields | relative L2 error ≤ 5 % on held-out terrains |
| PPO and attention dispatch | ≥ 30 paired seeds; "beats SPTF / LP" only by the decision rule on t/h |
| IL-1 haul-truck policy | ≥ 95 % route success without collision over 100 seeded episodes; RMS lateral error ≤ 0.5 m; minimum time-to-collision ≥ 3 s in ≥ 99 % of episodes; "beats pure pursuit + PID" only by the decision rule; sim-to-sim gap against the TypeScript twin reported |
| IL-2 excavator policy | fill factor ≥ 0.8 in ≥ 80 % of FEE episodes; stalls ≤ 5 %; FEE → MPM fill gap reported with a 95 % CI; "beats scripted dig" only by the decision rule on fill × cycle time |
| Slope forecasters (TCN, PatchTST, Chronos-Bolt) | on many seeded synthetic events: time-of-failure error ≤ 10 % of lead time at the observed signal-to-noise ratio, and "better than inverse velocity" only by the decision rule; on the one real series: descriptive only |
| Mine-to-mill meta-model | R² ≥ 0.95 against the analytical chain on held-out sweeps |
| DEM calibration | the 95 % CI of the recovered parameter covers the synthetic truth in ≥ 90 % of trials |
| Cosmos Reason 2 (inference only) | Q8_0 versus BF16 agreement ≥ 95 % on binary questions; balanced accuracy per question type with CI |
| TensorRT engines | parity per engine on every TensorRT version and execution provider: fp32 rtol 1e-3 / atol 1e-5; reduced precision change ≤ 1 percentage point; failing variants reported as rejected |

## Data validation

- **Classifier two-sample tests (C2ST)** with two classifier families and a real-versus-real baseline, wherever real data
  of the same type exist: fragment images and terrain statistics. Thresholds: AUC ≤ 0.60 for tabular or 1-D data; for
  images, an AUC gap of at most 0.10 over the real-versus-real baseline; train-versus-test AUC ≤ 0.60.
- **Embedding C2ST** on DINOv2 features for fragment images; duplicate scans; an injected-shift check that must be
  detected (AUC ≥ 0.80).
- **TSTR ≥ 0.90 × TRTR only where a real labelled training set exists:** fragmentation. The real fragment set is split by
  source group (240 originals; 231 groups after conservatively merging 9 visually similar pairs), never by file, because its 960 images
  include three flipped or rotated copies of each original.
- **Honesty rule:** a data type with no real reference is labelled "calibrated synthetic — not validated against real
  data" and receives no C2ST or TSTR claim.

## Parity layers

| Layer | Tolerance (from `thresholds.yaml`) |
|---|---|
| PyTorch → ONNX on CPU, fp32 | rtol 1e-3, atol 1e-5, max abs 1e-4 |
| Quantised models | task metric change ≤ 1 percentage point; mask IoU ≥ 0.99 against fp32 |
| ONNX in the browser | WASM fp32 max abs ≤ 1e-4; WebGPU fp32 ≤ 1e-3; fp16 ≤ 1e-2; top-1 agreement ≥ 0.995 |
| TypeScript and WGSL twins | by system class: exact trace, snapshot hash, or per-kernel plus observables ([lanes](lanes.md#parity-by-system-class)) |
| TensorRT engines | per engine, as in the acceptance table above |

## Code-quality thresholds

| Measure | Threshold |
|---|---|
| Branch coverage of the core | ≥ 85 % |
| Coverage of changed lines | ≥ 90 % |
| Mutation score, numerical core | ≥ 80 % (fails below 70 %) |
| Mutation score, other code | ≥ 60 % |
| Property-based examples per test | 200 in CI, 2,000 at release |
| Web: initial JavaScript | ≤ 200 KB gzip |
| Web: Lighthouse accessibility | ≥ 0.95 (performance warns below 0.80) |

## Quality gates by milestone

Each milestone ends green, committed and pushed, and an independent review then tries to refute the claim that it is
done, with reproducible evidence.

| Milestone | Gate: what the independent review checks |
|---|---|
| M0 bootstrap | Repository guard, CI, the live site skeleton, security settings, both repositories created and public, capability probe committed |
| M1 docs | Docs derived from the plan with no new behaviour, links resolve, diagrams render in both themes |
| M2 specifications | EARS completeness, hostile input classes covered, thresholds signed off |
| M3–M5 build | Red → green replay of every task, coverage ≥ 85 % of the core, mutation ≥ 80 % of the numerical core, ≥ 200 property examples per test |
| M6 data, training, runs | C2ST and TSTR, physics benchmarks, ONNX and TensorRT parity per engine, Cosmos Q8_0 versus BF16 agreement, VMAF targets, budgets, licence classes and `performance: local-only` markers |
| M7 web | Playwright hostile-input suite, in-browser parity, axe, Lighthouse, both themes and both languages, "not yet run" honesty |
| M8 release | Deployed commit equals validated commit, supply chain, live smoke in three browser engines, `minephys` wheel smoke |

**Definition of done:** the full quality bar is met; the knowledge-base items exist; and every studio tool either has a
published artefact or a documented "evaluated, not adopted because …" page.

## What CI checks today

On every push and pull request, the Python job runs `uv sync --all-groups --locked`, Ruff (lint and format), mypy,
`pytest -m "not gpu"` with branch coverage, `tools/trace.py --check` (requirement traceability), `tools/check_tdd.py
--replay` (red before green), `tools/check_repo.py` (secrets, machine paths, files over 10 MB, template residue),
`tools/check_docs.py` (links, public-repo hygiene, shell-block markers, diagram rules) and a CPU pipeline smoke on
samples. The web job runs Biome, route typegen, TypeScript and Vitest, the production build with its initial-JS budget,
and the Playwright end-to-end suite with axe. These commands run today from the repository root:

```bash run
uv sync --all-groups --locked
uv run pytest -m "not gpu"
uv run python tools/check_docs.py
```

## Assumptions and limits

- A passing gate means the review could not refute the claim with the evidence available; it is not a proof of
  correctness.
- Physics benchmarks validate the solvers on canonical problems; they do not validate a full mining scene, which is why
  scene-level results stay simulation-grade.
- Pre-registered criteria can be wrong. If one turns out to be infeasible, it is changed by a new specification revision
  with the reason recorded, never silently.

## In PitStudio

- Code: `specs/` (constitution, foundation spec, thresholds, traceability), `tools/` (checks), `tests/` (by kind),
  `.github/workflows/ci.yml`.
- Status: CI and the checks are active. Feature specifications, model results and gate outcomes after the bootstrap gate
  are **Not yet run**.

## References

1. Beverloo, W. A., Leniger, H. A., van de Velde, J. (1961). The flow of granular solids through orifices. *Chemical
   Engineering Science.* https://doi.org/10.1016/0009-2509(61)85030-6
2. DEM validation of the Beverloo law (2025). https://arxiv.org/html/2512.03698v1
3. Al-Hashemi, Al-Amoudi (2018). A review on the angle of repose of granular materials. *Powder
   Technology.* https://doi.org/10.1016/j.powtec.2018.02.003
4. Lube, G. et al. (2004). *Journal of Fluid Mechanics* 508:175–199. https://doi.org/10.1017/S0022112004009036
5. Lajeunesse, E. et al. (2004). *Physics of Fluids* 16:2371–2381. https://doi.org/10.1063/1.1736611
6. Deposition morphology of granular column collapses. https://arxiv.org/html/2002.02146v3
7. Martin, J. C., Moyce, W. J. (1952). An experimental study of the collapse of liquid columns on a rigid horizontal
   plane. *Phil. Trans. R. Soc. A.* https://doi.org/10.1098/rsta.1952.0006
8. SPHERIC Test 2: 3-D dam break. https://www.spheric-sph.org/tests/test-02
9. Kleefsman, K. M. T. et al. (2005). *Journal of Computational Physics.* https://doi.org/10.1016/j.jcp.2004.12.007
