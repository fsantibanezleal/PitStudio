# DEC-0016: A pre-registered decision rule for every "better" claim

> A learned or new method is called better than its baseline only if the paired 95 % confidence interval of the
> difference excludes zero in its favour; otherwise PitStudio says "no significant difference". The rule, the metric and
> the pairing are fixed before any result exists. · Part of: [decisions](README.md) · Related:
> [quality and validation](../quality-and-validation.md#the-pre-registered-decision-rule) · [sim-to-real](../../theory/sim-to-real.md) ·
> [models](../../models/README.md)

**Status:** Accepted, 2026-10-04

## Context

PitStudio compares classical, state-of-the-art and beyond-state-of-the-art methods on the same cases: PPO and attention
dispatch against SPTF and LP, a fragmentation U-Net against watershed plus Swebrec, learned forecasters against inverse
velocity, Isaac Lab policies against pure pursuit or scripted digging, Cosmos Reason 2 against its base model, structured
against unstructured domain randomisation. Three things make such comparisons easy to get wrong:

- **Noise.** Stochastic simulations and training runs vary from seed to seed, so a single run or a mean without its
  uncertainty can show a difference that is not there.
- **Non-transferable gains.** Published dispatch RL results were each measured on a different simulator with different
  baselines [1] [2] [3], so their improvements cannot be quoted as evidence for PitStudio's setting.
- **Choosing after looking.** Picking the metric, the test or the seeds after seeing results inflates false positives.

## Decision

1. **The rule.** For $n$ paired evaluations (same seeds, events or images for both methods), with differences
   $d_i = m_i^\text{new} - m_i^\text{base}$ oriented so that positive means better, the claim "better" is made only if the
   95 % confidence interval of the mean difference lies entirely above 0. Otherwise the UI and the docs say "no
   significant difference". The interval method for each comparison is fixed in its specification.
2. **Fixed in advance.** For every comparison, the metric, the pairing unit, the number of pairs and the acceptance
   criterion are written in the plan and the specification before training; see the acceptance table in
   [quality and validation](../quality-and-validation.md#model-acceptance-criteria). Examples: dispatch on t/h with at
   least 30 paired seeds; the U-Net on $x_{50}$ error; IL-2 on fill × cycle time.
3. **Binary agreement tasks.** Cosmos Reason 2 against Qwen3-VL-2B uses McNemar's test on paired answers; "better" only if
   $p < 0.05$.
4. **One real event is not a sample.** The single real slope-failure series is reported descriptively, with "single real
   event — no significance test".
5. **Several axes, never one number.** Results are reported on all their axes together (for example accuracy, latency,
   size and robustness), with no composite score.
6. **Enforcement.** The rule is implemented once, unit-tested in the build phase, and checked on the real artefacts in
   the data-and-models and web reviews.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Compare point estimates (means, best runs) | Simple, common | Ignores seed noise; a lucky seed reads as an improvement | Not honest enough for published claims |
| Unpaired comparison of two sets of runs | No need to align seeds | Loses the variance reduction of pairing; needs far more runs for the same power | The simulator makes pairing free |
| Choose the test and metric after seeing results | Flexible | Inflates false positives | Contradicts pre-registration |
| A single composite leaderboard score | Easy to communicate | Hides trade-offs between accuracy, speed and robustness | Results stay multi-axis |

## Consequences

**Positive.** Every "better" in PitStudio is reproducible and defensible; "no significant difference" is a normal,
visible outcome rather than a hidden one.

**Negative, accepted.** More runs per comparison (paired seeds) and therefore more GPU time; some comparisons will end
inconclusive.

**Watch.** Comparisons where the paired design is impossible; the specification must state the alternative design.

## References

1. Meng et al. (2024). OpenMines. IEEE IV 2024. https://arxiv.org/abs/2404.00622
2. Banerjee, Nguyen, Fookes (2025). Mining-Gym. https://arxiv.org/abs/2503.19195
3. Zhang C. et al. (2020). Dynamic dispatching for large-scale heterogeneous fleet via multi-agent deep reinforcement
   learning. https://arxiv.org/abs/2008.10713
