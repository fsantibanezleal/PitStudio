# M01 — Match factor and finite-source queueing (MVA)

> Closed-form fleet balance and queueing models that size a truck–shovel fleet in milliseconds and act as the
> analytical cross-check of the haulage simulation. · Part of: [Methods](README.md) · Related:
> [Haulage theory](../theory/haulage.md) · [M02 Haulage DES](m02-haulage-des.md) ·
> [Case A1](../cases/a1-truck-shovel-dispatch.md) · [minephys](../frameworks/minephys.md)

| Tier | Learned | Lane | Cases | Implementation (licence) | Status |
|---|---|---|---|---|---|
| Classical | no | live | [A1](../cases/a1-truck-shovel-dispatch.md) | `minephys.haulage` (Apache-2.0) + TypeScript port | not yet implemented |

## What and why

A truck–shovel system is a closed loop: a fixed number of trucks circulates between loading units, dumps and haul
roads. Two questions come before any simulation: *is the fleet balanced*, and *how much throughput does randomness
cost*. M01 answers both analytically.

- The **match factor** compares the rate at which trucks arrive at the loaders with the rate at which the loaders can
  serve them [1]. It is the industry's first fleet-sizing number.
- **Finite-source (machine-repair) queueing** treats the trucks as the finite population and the shovel as the
  server. It captures what the match factor ignores: random cycle times make trucks bunch, so a balanced fleet still
  queues and still leaves the shovel idle [2].
- **Mean Value Analysis (MVA)** extends this to a closed network of several stations (shovels, crusher, dumps, road
  segments) [5].

PitStudio uses M01 for three things: an instant fleet-sizing panel on the web, a sanity check that every
[M02](m02-haulage-des.md) simulation must pass under matching assumptions, and a teaching device for the gap between
deterministic balance and stochastic reality. The derivations are on the [haulage theory page](../theory/haulage.md).

## The algorithm

### Match factor

$$
MF = \frac{N_T \, t_L}{N_L \, T_c^{\ast}}
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $N_T$ | number of trucks | – |
| $N_L$ | number of loading units | – |
| $t_L$ | time to load one truck (spot + all passes) | min |
| $T_c^{\ast}$ | truck cycle time excluding waiting (load + haul + dump + return) | min |

$MF < 1$ means the loaders wait (under-trucked), $MF > 1$ means the trucks queue (over-trucked), and $MF = 1$ is the
deterministic balance point. This form assumes homogeneous trucks and loaders; Burt and Caccetta give the
heterogeneous extension [1], which PitStudio implements from the primary text at specification.

### Finite-source queue: one shovel, $N$ trucks (M/M/1//N)

Each truck spends an exponentially distributed time with mean $1/\lambda$ away from the shovel (haul, dump, return)
and an exponentially distributed loading time with mean $1/\mu$. Carmichael models shovel–truck operations exactly
as such a finite-source cyclic queue [2]. The standard machine-repairman result is†:

$$
\pi_0 = \left[\sum_{n=0}^{N} \frac{N!}{(N-n)!}\left(\frac{\lambda}{\mu}\right)^{n}\right]^{-1},
\qquad U = 1 - \pi_0,
\qquad X = \mu \,(1 - \pi_0)
$$

| Symbol | Meaning | Unit |
|---|---|---|
| $\lambda$ | rate at which one truck returns to the shovel (1 / mean time away) | 1/h |
| $\mu$ | loading rate of the shovel (1 / mean loading time) | 1/h |
| $\pi_0$ | probability that the shovel is idle (no truck present) | – |
| $U$ | shovel utilisation | – |
| $X$ | system throughput | trucks/h |

By Little's law the mean cycle time is $N/X$, so the mean time a truck spends queueing and loading is
$N/X - 1/\lambda$.

### Open M/M/c (bank of loaders fed by Poisson arrivals)

For comparison with the closed model, the open M/M/c queue with $\rho = \lambda/(c\mu) < 1$ and $a = \lambda/\mu$
uses the Erlang-C probability of waiting [4]:

$$
C(c,a) = \frac{\dfrac{a^{c}}{c!}\dfrac{1}{1-\rho}}{\displaystyle\sum_{k=0}^{c-1}\frac{a^{k}}{k!} + \frac{a^{c}}{c!}\frac{1}{1-\rho}},
\qquad W_q = \frac{C(c,a)}{c\mu - \lambda},
\qquad L_q = \lambda W_q
$$

Here $\lambda$ is the arrival rate at the bank (1/h), $c$ the number of loaders, $W_q$ the mean wait (h) and $L_q$
the mean queue length. The open model over-states waiting for small fleets because it ignores that queued trucks
stop arriving; the closed model does not.

### Mean Value Analysis for a closed multi-station network

For a product-form closed network with stations $k$, visit ratios $v_k$ and service rates $\mu_k$, exact MVA
iterates over the population $n = 1 \dots N$ [5]:

$$
W_k(n) = \frac{1 + L_k(n-1)}{\mu_k}, \qquad
X(n) = \frac{n}{\sum_k v_k W_k(n)}, \qquad
L_k(n) = v_k \, X(n) \, W_k(n)
$$

with $L_k(0) = 0$. Haul-road segments are *delay* stations with $W_k = 1/\mu_k$ (no queue). Symbols: $W_k$ mean
residence time at station $k$ (h), $L_k$ mean number of trucks at $k$, $X$ system throughput (cycles/h).

```text
mva(stations, N):
    L[k] = 0 for every queueing station k
    for n in 1..N:
        for k in stations:
            W[k] = 1/mu[k]                     if k is a delay station
                   (1 + L[k]) / mu[k]          otherwise
        X = n / sum(v[k] * W[k])
        for k in queueing stations: L[k] = v[k] * X * W[k]
    return X, W, L
```

† Standard textbook form; the exact transcription is checked against the primary source by a worked-example test at
specification.

### Worked example (illustrative inputs, not field data)

One shovel, eight trucks, mean loading time 3 min ($\mu = 20$ /h), mean time away 21 min ($\lambda = 20/7$ /h, so
$\lambda/\mu = 1/7$).

- **Match factor:** $T_c^{\ast} = 3 + 21 = 24$ min, so $MF = (8 \times 3)/(1 \times 24) = 1.00$: a perfectly balanced
  fleet on paper, which would deliver 20 loads/h with the shovel always busy.
- **Finite-source queue:** the nine terms of the sum in $\pi_0$ are 1, 1.1429, 1.1429, 0.9796, 0.6997, 0.3998,
  0.1714, 0.0490 and 0.0070, which add to 5.5922, so $\pi_0 = 0.1788$, $U = 0.821$ and $X = 20 \times 0.821 = 16.42$
  loads/h.
- **Reading:** randomness alone costs about 18 % of the deterministic throughput at $MF = 1$. The mean cycle is
  $8/16.42$ h $= 29.2$ min, so each truck queues and loads for about 8.2 min instead of 3 min. With an illustrative
  200 t payload that is 3,285 t/h instead of 4,000 t/h.

This is exactly the effect the DES in [M02](m02-haulage-des.md) reproduces and that dispatch ([M03](m03-lp-dispatch.md),
[M04](m04-ppo-dispatch.md)) tries to reduce.

## Baseline and comparison

M01 is itself a baseline: the analytical reference for the DES. It is compared, not ranked.

- **M01 vs M02 under matching assumptions.** With exponential loading and travel times and a single dispatch rule,
  the DES throughput must fall inside its own 95 % confidence interval around the MVA value (product-form networks
  are exact for MVA [5]). This is an oracle test in the build phase.
- **M01 vs M02 under realistic assumptions.** With deterministic, grade-dependent travel times from
  [M06](m06-haul-road-energy-routing.md) and non-exponential loading, the DES departs from MVA. The departure is
  reported as a result ("how much product-form assumptions misjudge this pit"), never treated as a failure. DES is the
  industry-standard validator precisely because these assumptions break in practice [6].
- No "better than" claim is made for M01, so the [decision rule](README.md#how-methods-are-compared) does not apply.

## Acceptance criterion (pre-registered)

From the project's validation rules ([quality and validation](../architecture/quality-and-validation.md)): every
`minephys` model is specified test-first with worked examples from primary sources, and every numerical core carries
at least three metamorphic relations. For M01 the relations proposed for the spec
are:

1. $X(N+1) \ge X(N)$ — adding a truck never lowers finite-source throughput;
2. $U \to 1$ as $N \to \infty$ — the shovel saturates;
3. $MF$ scales linearly with $N_T$ and inversely with $N_L$;
4. MVA with one queueing station equals the closed-form M/M/1//N result.

The TypeScript port is in the *exact* parity class: same inputs, same outputs to floating-point tolerance, on fixed
golden vectors. Numerical tolerances are fixed in `specs/000-foundation/thresholds.yaml` at specification.

**Results: Not yet run** — produced in the data-and-models phase. Reported: the A1 fleet-sizing curve
($X$ and $U$ vs $N_T$), and the M01-vs-M02 gap under both assumption sets.

## Lane and web delivery

**Live.** Analytical models pass the lane gate easily: under 50 KB of JavaScript and under 1–50 ms per evaluation
(estimates, measured when the web is built; see [compute lanes](../pipelines/compute-lanes.md)). The fallback is a
baked grid of $(N_T, \lambda, \mu)$ results. A "verify with the reference engine" button runs the same function from
the `minephys` wheel in Pyodide.

## Assumptions and limits

- Exponential service and travel times. Real loading is closer to Erlang or lognormal and haul times are nearly
  deterministic on a fixed profile [6], so M01 is a bound and a sanity check, not a forecast.
- No bunching dynamics beyond what the queue implies; no breakdowns, shift changes or road deterioration.
- No dispatch: trucks are assigned to a fixed shovel. Multi-shovel dispatch effects need [M02](m02-haulage-des.md).
- Homogeneous fleets in the forms above. Heterogeneous fleets use the Burt–Caccetta extension [1].
- Educational and planning-grade: a simulation-grade twin, not a live digital twin of any operation.

## In PitStudio

- **Cases:** [A1 truck–shovel dispatch](../cases/a1-truck-shovel-dispatch.md) (fleet sizing panel, match factor KPI).
- **Code (planned):** `minephys.haulage` (match factor, M/M/c, MVA) in the companion package
  ([minephys](../frameworks/minephys.md)); a TypeScript port in a `web/` worker for the live panel.
- **Status:** not yet implemented — built test-first in the build phase.

## References

1. Burt, C. N. & Caccetta, L. (2007). *Match factor for heterogeneous truck and loader fleets*. International Journal
   of Mining, Reclamation and Environment 21(4):262–270. https://doi.org/10.1080/17480930701388606
2. Carmichael, D. G. (1986). *Shovel–truck queues: a reconciliation of theory and practice*. Construction Management
   and Economics 4(2):161–177. https://doi.org/10.1080/01446198600000013
3. Ta, C. H., Kresta, J. V., Forbes, J. F. & Marquez, H. J. (2005). *A stochastic optimization approach to mine truck
   allocation*. International Journal of Surface Mining, Reclamation and Environment 19(3):162–175.
   https://doi.org/10.1080/13895260500128914
4. *M/M/c queue* (Erlang-C and waiting-time formulas). https://en.wikipedia.org/wiki/M/M/c_queue
5. *Mean value analysis* (closed-network recursion). https://en.wikipedia.org/wiki/Mean_value_analysis
6. Meneses & Sepúlveda (2023). Discrete-event simulation study of truck productivity and fuel consumption under
   haul-road deterioration. Mining 3(1):96–105 (CC BY). https://doi.org/10.3390/mining3010006
