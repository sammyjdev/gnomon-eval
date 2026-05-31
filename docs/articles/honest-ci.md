<!--
LinkedIn article draft (English). Source artifact for the post about GNOMON's
case-level bootstrap aggregation (ADR-008). All numbers are reproducible from
the repo: src/gnomon/metrics/confidence.py and src/gnomon/runner/runner.py.
-->

# Your RAG Eval's Confidence Interval Is Lying — and the Bug Is Pseudoreplication

In my last post I built a RAG in Java 21 for a D&D rules system. The natural next question is whether it's actually good, so I wrote an evaluation harness for it. The first real thing the harness taught me is that the standard way people attach a confidence interval to LLM-as-judge metrics is statistically wrong — specifically, it's a textbook case of pseudoreplication. Here's the full autopsy.

## The ritual

The dominant pattern for RAG quality is LLM-as-judge. A model scores each case on *faithfulness* (is the answer entailed by the retrieved context?) and *context precision* (are the retrieved chunks relevant to the question?). Judge outputs are noisy, so the accepted fix is to run the judge `N` times per case and report a mean with a confidence interval. The CI is the part everyone points to as the "rigorous" bit.

I was about to implement exactly that. Then I instrumented it.

## Pseudoreplication

I ran the judge against a local Ollama model at `temperature=0` (for reproducibility) and measured the run-to-run variance per case.

It was exactly zero. At `temperature=0` the judge is a deterministic function of `(prompt, seed)`. The `N` "repeated" runs are `N` byte-identical copies.

My aggregation was pooling every `(case × run)` score into one flat vector and computing a Student-t interval over `n = cases × runs`. With 2 cases and 8 runs, that's `n = 16`. But there are not 16 independent observations here — there are 2. The runs are *repeated measures of the same experimental unit*, and treating them as independent replicates is pseudoreplication (Hurlbert, 1984). The unit of replication is the case, not the judge call.

Make it concrete with a model. Let `y_ij = μ + a_i + e_ij`, where `a_i` is the case effect (variance `σ²_a`, between-case) and `e_ij` is judge noise (variance `σ²_e`, within-case). The estimator you actually care about is the grand mean, and in a balanced design with `k` cases and `n` runs each:

```
Var(μ̂) = σ²_a / k  +  σ²_e / (k·n)
```

The between-case variance shrinks at rate `k`. Only the judge-noise term shrinks at rate `k·n`. The naive pooled SE — `s / sqrt(k·n)` — implicitly divides *both* terms by `k·n`, so it understates the dominant `σ²_a / k` term by a factor of `n`. In standard-error units that's `sqrt(n)`. With `n = 8`, the interval is roughly `sqrt(8) ≈ 2.8×` too narrow before you even account for the second error.

The second error is the degrees of freedom. Pooling reports `df = k·n − 1 = 15`, so the Student-t critical value is `2.13`. The honest `df = k − 1 = 1` gives `12.71`. You get a tighter interval *and* a smaller multiplier, both for free, both wrong.

## The numbers

On the two cases that scored `1.0` and `0.0`:

| Method | n | df | t* | SE | Interval |
|---|---|---|---|---|---|
| Pooled (pseudoreplicated) | 16 | 15 | 2.13 | 0.129 | **[0.225, 0.775]** |
| Honest t over cases | 2 | 1 | 12.71 | 0.500 | [−5.85, 6.85] → clamp [0,1] |
| Bootstrap over cases | 2 | — | — | — | **[0.000, 1.000]** |

The pooled interval looks confident. It is a confidence interval for a quantity nobody asked about, computed under an independence assumption that is false by construction.

## Which uncertainty do you actually want?

There are two distinct questions hiding in `Var(μ̂) = σ²_a/k + σ²_e/(k·n)`:

- **`σ²_e` (within-case):** how much does the judge wobble re-scoring the same case? This is *instrument reliability*.
- **`σ²_a / k` (between-case):** how much does the metric vary across the population of questions your users will ask, given that your dataset is a finite sample of `k` of them? This is *sampling uncertainty about the population mean*.

A regression gate is making an inference about the population mean. Its uncertainty is dominated by `σ²_a / k`. The "run the judge N times" ritual is an attempt to estimate `σ²_e`, which (a) is the wrong quantity for the gate, and (b) at `temperature=0` is identically zero. So the ritual contributes nothing except a false reduction in the reported interval.

## Determinism vs. the premise

The whole "report a CI because the judge is non-deterministic" argument assumes `σ²_e > 0`. Two ways out, both with teeth:

- **Keep `temperature=0`.** Then `σ²_e = 0`, the judge is reproducible, and `N=1` is statistically sufficient. The N-runs machinery is pure cost.
- **Raise the temperature** to manufacture `σ²_e > 0` so there's something to measure. But then reproducibility needs per-run seed pinning, the numbers drift across model/hardware, and — empirically — on unambiguous cases the variance is still ~0. I measured `stdev = 0.0` across 8 runs even at `temperature=0.8` on a clear-cut case. The variance only appears on genuinely ambiguous items, so the estimate is degenerate exactly where you'd hope it wasn't.

Either way, the honest object is the between-case interval. The lever to tighten it is **more cases**, not more judge runs — and a harness should say that out loud instead of laundering it into decimals.

## The interval method — why not just the honest t?

Because the honest t-interval at small `k` on a bounded metric is also wrong, just differently. Faithfulness lives in `[0,1]`; the t-interval assumes unbounded, roughly-Gaussian support. At `k=2` it returns `[−5.85, 6.85]`, and the usual patch is to clamp to `[0,1]` — which is an artifact, not an inference, and it lies hardest near the boundaries. With 6 of 8 cases passing, a clamped t gives `[0.36, 1.00]`: it claims the true rate could be 100% despite two observed failures.

So GNOMON uses a **percentile bootstrap over the cases**: resample the `k` per-case scores with replacement, recompute the mean, take the empirical 2.5/97.5 percentiles. Resampled means of values in `[0,1]` stay in `[0,1]`, so the interval is bounded by construction — no clamp — and it won't assert `1.0` after seeing a failure. For a *binary* pass/fail judge the principled choice is a binomial-proportion interval (Wilson or Jeffreys); Wilson on 6/8 returns `[0.41, 0.93]`, correctly refusing the `1.0` the clamped t invented. The continuous-score path uses the bootstrap (or a Beta moment-fit).

None of this is novel statistics — variance components, pseudoreplication, and bounded-support intervals are decades old. The point is that bootstrap-over-cases is exactly the `σ²_e → 0` limit of a two-level random-effects estimator, so it isn't a hack; it's the correct hierarchical model collapsed to the regime a deterministic judge actually lives in. (BCa would improve coverage at moderate `k`; at `k=2` it doesn't matter, because two contradictory cases *should* return `[0,1]`.)

## The honesty propagates into the engineering

- **Gate on `ci_low`, not the mean.** A result whose interval still crosses the threshold doesn't pass. Thresholds are validated to `[0,1]` at config load, before any model call (fail-closed).
- **Fail-closed parsing.** A weak judge (`phi3:mini`) returned valid JSON on a hard case with the key silently renamed from `faithfulness` to `faithlessness`. The parser raised `JudgeProtocolError` instead of fuzzy-matching it — the run fails loud rather than fabricating a score. A quiet wrong number is the worst possible output for an eval tool.
- **Exact-match cache.** Judge scores are memoized on the full identity tuple `(case_id, question, answer, contexts, model, seed, run)`. No prefix keys, no normalization — a key that doesn't match exactly is a miss, never a hit returning a score computed for a different context.
- **One model call per `score()`.** The judge returns one JSON object keyed by metric, so cost is `|cases| × runs`, not `× |metrics|`. `options.seed = seed + run` gives a deterministic, reproducible sequence.
- **Dependency direction is a test.** An AST check fails the build if the domain package imports anything below it. Targets and judges depend on the core through Protocols; the core depends on nothing.

## The whole fix, in two functions

The entire correction is two steps: collapse runs within a case, then bootstrap over the cases. First, the runner refuses to pool — each case's `N` runs are averaged into a single per-case score (that's the within-case `σ²_e` denoising), so what comes out is one observation per case:

```python
for case in cases:
    response = target.query(case.question)
    # Denoise within the case: the case's score for a metric is the mean of
    # its N judge runs (ADR-008). Runs are repeated measures of one case,
    # not independent samples, so they are collapsed here, not pooled.
    runs_by_metric: dict[str, list[float]] = defaultdict(list)
    for run in range(config.judge_runs):
        run_scores = judge.score(case, response, seed=config.seed, run=run)
        for metric_name, value in run_scores.scores.items():
            runs_by_metric[metric_name].append(value)
    for metric_name, values in runs_by_metric.items():
        case_scores_by_metric[metric_name].append(sum(values) / len(values))
```

Then the aggregation takes the interval over those per-case scores with a seeded percentile bootstrap. `n` is the number of cases — the real replication unit — and the resampled means never leave `[0,1]`, so there is no clamp:

```python
def aggregate_metric(
    metric: str, case_scores: list[float], *, confidence_level: float = 0.95, seed: int
) -> MetricResult:
    """Mean over cases with a seeded percentile-bootstrap confidence interval."""
    n = len(case_scores)
    if n < MIN_CASES:                      # one case cannot bound a population
        raise ValueError(
            f"need at least {MIN_CASES} cases to bootstrap a confidence interval "
            f"for {metric!r}, got {n}"
        )

    mean = sum(case_scores) / n
    rng = random.Random(seed)              # seeded → reproducible interval (RNF-01)
    boot_means: list[float] = []
    for _ in range(_BOOTSTRAP_RESAMPLES):  # resample cases with replacement
        total = 0.0
        for _ in range(n):
            total += case_scores[rng.randrange(n)]
        boot_means.append(total / n)
    boot_means.sort()

    alpha = 1.0 - confidence_level
    lo_index = int((alpha / 2.0) * _BOOTSTRAP_RESAMPLES)
    hi_index = int((1.0 - alpha / 2.0) * _BOOTSTRAP_RESAMPLES) - 1
    return MetricResult(
        metric=metric,
        mean=mean,
        ci_low=boot_means[lo_index],       # empirical 2.5th percentile
        ci_high=boot_means[hi_index],      # empirical 97.5th percentile
        n=n,                               # n = cases, not cases × runs
        confidence_level=confidence_level,
    )
```

`random.Random(seed)` is the whole reproducibility story: same dataset, same seed, identical interval, no global RNG state to leak. The `n < MIN_CASES` guard is the honest floor — one case can't bound a population, so it refuses rather than returning a zero-width interval that would imply certainty from a single data point.

## What this is not

This is a methodology fix validated on a deliberately tiny setup — a mock target and two judge models — not an empirical study. I haven't measured how often the pseudoreplicated interval flips a real gate decision across many RAGs and judges; that's the experiment that would turn this into a paper rather than a build log. The claim here is narrow and, I think, hard to argue with: if you report a CI by repeating a deterministic judge and pooling the runs, that interval is `~sqrt(N)` too narrow, and the fix is to make the case your unit of replication.

The harness is called GNOMON — the rod on a sundial that casts the shadow. It doesn't compute the time. It stands still and lets you read it without lying to yourself.

Repo (MIT, offline-first): https://github.com/sammyjdev/gnomon-eval

---

## TL;DR — for anyone, no stats required

To check whether an AI system is any good, a common trick is to have a *second* AI grade its answers, grade them a few times, and report an average with a "margin of error" next to it. The margin of error is the part that's supposed to say "trust me, this is rigorous."

I found that when you set the grader to be consistent (so the score is repeatable), those repeated gradings are *identical copies*. Counting them as separate opinions makes the margin of error look about three times smaller than it honestly is. It's like asking one friend the same question eight times and presenting it as a survey of eight people.

The fix is boring and correct: treat each **test question** as one data point — not each repeat — and compute the margin of error with a method (a *bootstrap*) that can't claim more certainty than the handful of questions actually support. When the answer comes back as "we don't have enough test questions to say yet," that's not a failure of the tool. That *is* the honest answer, and the only way to shrink the margin is to add more test questions, not to re-grade the same ones.

An evaluation tool that fakes its own margin of error is worse than having none, because it dresses up a guess as a measurement. GNOMON is my attempt to build one that doesn't.
