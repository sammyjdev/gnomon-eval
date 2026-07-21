# GNOMON contract validation for GraphRAG integration (pull-based)

> Validated by reading the code and tests of the `sammyjdev/gnomon-eval` repository. Each item cites the real source (`file:line`).
>
> **As-of:** validated against master as of 2026-06-11 (commit `b32d69c`). Master has moved since then (multi-turn ChatEval etc.); the `file:line` citations may have drifted — re-verify before depending on a specific line. The contract surface (RagTarget/RagResponse/run_eval) is stable.
>
> **Note:** some names assumed in the question don't match the code — the divergences are flagged in each item.

---

## A. Packaging / import

### 1. Distribution name and reference without PyPI
- Distribution name: **`gnomon-eval`**, version `0.1.0` (`pyproject.toml:6-7`). Build backend: `hatchling`.
- **The import package name is different: `gnomon`** (≠ distribution). See `pyproject.toml:25-26`: `[tool.hatch.build.targets.wheel] packages = ["src/gnomon"]`.
- Not on PyPI. Ways to reference it from the consumer's `pyproject`:
  - **canonical git**: `gnomon-eval @ git+https://github.com/sammyjdev/gnomon-eval.git@<ref>` (repo in scope: `sammyjdev/gnomon-eval`; the local `origin` is just a proxy `http://local_proxy@127.0.0.1:.../git/sammyjdev/gnomon-eval`).
  - **editable local path**: `pip install -e .` (used in the README, `README.md:55,63`), or a path dependency `gnomon-eval @ file:///path`.

### 2. Exact import paths
There is no top-level re-export (`src/gnomon/__init__.py` is empty; every subpackage `__init__.py` is empty). Use the full path:

```python
from gnomon.runner.runner import run_eval               # runner.py:23 (used in cli.py:22)
from gnomon.metrics.confidence import aggregate_metric  # confidence.py:31 (used in runner.py:20)
```

### 3. Python and runtime dependencies
- `requires-python = ">=3.11"` (`pyproject.toml:11`) — uses stdlib `tomllib` (`run_config.py:10`).
- **Single runtime dependency: `pydantic>=2.6`** (`pyproject.toml:12-14`). HTTP is stdlib `urllib` (`UrllibTransport` in `gnomon/http.py`, no external lib).
- **LLM judge: GNOMON brings its own client**, it does not expect you to bring yours. Two judges behind the same Protocol: `OllamaJudge` (local Ollama client over stdlib HTTP, `judge/ollama.py:34`) and `StubJudge` (deterministic, `judge/stub.py:20`). **No built-in OpenAI/Anthropic client** — the default judge is local Ollama. The consumer only *configures* provider/model (TOML), it does not inject a client.

---

## B. Target contract (pull-based)

### 4. Target Protocol — confirms `RagTarget`
`domain/interfaces.py:13-19`, `@runtime_checkable Protocol`. Single method:

```python
def query(self, question: str) -> RagResponse   # interfaces.py:17
```

- `question: str` → returns `RagResponse`. **It is synchronous** (not async).

### 5. run_eval only calls `query`
`target.query(case.question)` (`runner.py:31`). It does not access `name`, `setup`, `teardown`, or any other target attribute. (Judges have `model_name`, but that is on the Judge side, not the target.)

---

## C. RagResponse (`domain/models.py:25-33`, `frozen` model)

### 6. Full field list
All **required**, no default:

| field | type | constraint | source |
|---|---|---|---|
| `answer` | `str` | none | models.py:30 |
| `contexts` | `list[str]` | none | models.py:31 |
| `total_tokens` | `int` | `Field(ge=0)` ✓ validated ≥0 | models.py:32 |
| `latency_ms` | `float` | `Field(ge=0.0)` ✓ validated ≥0 | models.py:33 |

### 7. Critical
- **Generated-answer field: YES → `answer: str`** (`models.py:30`).
- **Retrieved-contexts field: YES → `contexts: list[str]`** (`models.py:31`). **The type is plain `list[str]` — NOT objects with `.text`**, there is no `source_documents`.
- **There is NO id field on the response.** `RagResponse` does not link back to the question. The binding is **positional**: the runner pairs `case → response` in the loop (`runner.py:30-31`), and the `id` lives on `EvalCase` (`models.py:19`), not on the response.

---

## D. run_eval input / dataset

### 8. run_eval signature
`runner.py:23-25` — no defaults, everything required:

```python
def run_eval(
    cases: list[EvalCase], target: RagTarget, judge: Judge, config: EvalConfig
) -> EvalReport
```

### 9. Example schema — `EvalCase`
`domain/models.py:14-22` (`frozen`), loaded by `load_dataset` (`dataset/loader.py:21`):

| field | type | required |
|---|---|---|
| `id` | `str` (`min_length=1`) | yes |
| `question` | `str` (`min_length=1`) | yes |
| `expected_answer` | `str` (`min_length=1`) | yes |
| `expected_contexts` | `list[str]` (`min_length=1`) | yes |

- **Ground truth (`expected_answer`, `expected_contexts`) is REQUIRED by the dataset schema.** **HOWEVER, a critical divergence to note:** the v1 judge prompt does **not use** these fields. `build_prompt` (`judge/prompts.py:28-36`) only references `case.question`, `response.answer`, `response.contexts`. **So, in the current implementation, `faithfulness` and `context_precision` are reference-free** — the ground truth is required-but-ignored by scoring. You must supply it for the dataset to validate, but it does not enter the score.

### 10. How metrics are selected
**They are not passed to `run_eval`.** The metrics are exactly the keys the judge returns in `MetricScores.scores`; the runner collects them by `metric_name` from the judge's output (`runner.py:44-48`). The canonical set `V1_METRICS = ("faithfulness", "context_precision")` is hardcoded in the judge/prompt (`metrics/names.py:8`). In other words: **you select metrics by choosing/configuring the judge, not through a `run_eval` argument.**

---

## E. v1 metrics

### 11. Exact identifiers
Strings `"faithfulness"` and `"context_precision"` (`metrics/names.py:8`). These are **dict string keys**, not objects.

### 12. What each one consumes
From the prompt, `judge/prompts.py:14-22`:

- `faithfulness`: "how well the ANSWER is grounded in the CONTEXTS" → needs **`response.answer` + `response.contexts`**. **Requires the generated answer.**
- `context_precision`: "how relevant the CONTEXTS are to the QUESTION" → needs **`case.question` + `response.contexts`**. **Does NOT use the answer.**
- **Decision for GLYPH:** `faithfulness` forces a generation step (answer); `context_precision` alone would not need one. Since both are requested in a single call, in practice you will have to supply `answer` anyway. Neither one uses ground truth.

### 13. Do they require an LLM judge? YES
Configured via the TOML `[judge]` block (`config/run_config.py:29-35`; wired in `cli.py:45-53`):

- `provider`: `"ollama"` or `"stub"` (`run_config.py:31`).
- `OllamaJudge` (`judge/ollama.py:34-89`): `model` + `base_url`, `temperature=0.0`, `seed = seed + run` (`ollama.py:72`). **One model call per `score()`** = per `(case, run)`. Billable cost = **`len(cases) * config.judge_runs`** calls, with no per-metric multiplier (all metrics in a single call) — documented in `runner.py:8-12` and implemented in `ollama.py:64-89`. Cached by `(case, response, model, seed, run)` via `JudgeCache` (`ollama.py:53-62`).
- **There is no env var for the provider**; the API key belongs only to the *target* (`api_key_env`, `run_config.py:23`). **The call is per-example → cost scales with dataset × judge_runs.**

---

## F. Output / aggregation

### 14. run_eval returns `EvalReport`
`models.py:88-115`:

- `metrics: list[MetricResult]` + `per_case_cost: list[CaseCost]`.
- `MetricResult` (`models.py:51-67`): `metric, mean, ci_low, ci_high, n (≥2), confidence_level`.
- Helpers: `.metric(name)` (`models.py:101`), `.total_tokens` (`:107`), `.mean_latency_ms` (`:112`).
- `per_case_cost`: cost and latency per case (`CaseCost`: `case_id, total_tokens, latency_ms`).
- `case_scores`: per-case denoised scores, organized by metric.

### 15. Per-case scores

- `gnomon.domain.models.CaseScore`: `case_id: str` and `score: float` in `[0, 1]`; it is the denoised score of one case for one metric, i.e. the mean over the case's judge runs.
- `EvalReport.case_scores: dict[str, list[CaseScore]]`: keyed by metric name, the same names as `MetricResult.metric` and `V1_METRICS`, with one `CaseScore` per case in the same order as `per_case_cost`. It is the exact per-case value that feeds `MetricResult`'s bootstrap CI, so `sum(cs.score for cs in report.case_scores[name]) / len(report.case_scores[name])` reproduces `report.metric(name).mean`.
- The new field defaults to `{}`, and does not change `MetricResult` or any existing `EvalReport(...)` call site. This closes gnomon-eval#46, and glyph ADR-G8 can retire its custom eval loop.

### 16. `aggregate_metric`
`metrics/confidence.py:31-33`:

```python
def aggregate_metric(
    metric: str, case_scores: list[float], *, confidence_level: float = 0.95, seed: int
) -> MetricResult
```

- Returns a `MetricResult` = mean over cases + **seeded percentile-bootstrap CI** (2000 resamples, `confidence.py:28,44-54`). Requires n≥2 (`MIN_CASES`, `confidence.py:22,36`).
- `run_eval` exposes these same scores in `EvalReport.case_scores`, without changing the aggregation.*

---

## G. Minimal end-to-end example

Real, from `tests/integration/test_runner_end_to_end.py:27-59` (the smallest complete flow: define cases + target, run `run_eval`, read the aggregated report):

```python
from gnomon.config.config import EvalConfig
from gnomon.domain.models import EvalCase
from gnomon.judge.stub import StubJudge
from gnomon.runner.runner import run_eval
from gnomon.targets.mock import MockTarget

CASE = EvalCase(
    id="case-1",
    question="Who narrates the world?",
    expected_answer="The game master narrates the world.",
    expected_contexts=["The game master narrates the world to the players."],
)
CASE2 = EvalCase(
    id="case-2",
    question="Who adjudicates the rules?",
    expected_answer="The game master adjudicates the rules.",
    expected_contexts=["The game master adjudicates the rules at the table."],
)

target = MockTarget(
    answer="The game master narrates the world.",
    contexts=["The game master narrates the world to the players."],
    total_tokens=137, latency_ms=512.0,
)

cfg = EvalConfig(reproducible=True, seed=42, judge_runs=8)
report = run_eval([CASE, CASE2], target, StubJudge(), cfg)

faithfulness = report.metric("faithfulness")   # MetricResult
assert faithfulness.n == 2                      # n = number of CASES, not runs (ADR-008)
assert 0.0 <= faithfulness.ci_low <= faithfulness.mean <= faithfulness.ci_high <= 1.0
```

Aggregation happens **inside** `run_eval` (`runner.py:50-56`, which calls `aggregate_metric`). For your pull-based flow, the equivalent, swapping `MockTarget`/`StubJudge` for your GraphRAG adapters, is trivial — the only point of friction is item 15 (`case_scores`).

**`judge_runs=1` with a deterministic judge (roadmap B1):** `EvalConfig` accepts `deterministic_judge: bool = False` (`config.py:36`). With `deterministic_judge=True`, the `judge_runs` floor relaxes from 2 to 1 (`config.py:40-53`) — with `temperature=0` the repeated runs are copies, so the `>=2` floor from VAL-04 is a wasted model call. The `>=2` floor still stands for judges not declared deterministic (ADR-002/008 semantics intact); `aggregate_metric` (item above) is unchanged — the CI remains over cases, not over runs.

---

## H. Stable v1 judge surface

### 17. Public artifacts for downstream consumers

- `gnomon.judge.prompts.V1_PROMPT_INSTRUCTIONS: str` (`judge/prompts.py:28-32`) is the static instructional header, with the metric descriptions and the untrusted-input warning, stable across calls.
- `gnomon.judge.prompts.V1_PROMPT_JSON_SHAPE: str` (`judge/prompts.py:33`) is the exact descriptor of the JSON shape the judge must return.
- `gnomon.judge.prompts.build_prompt(case, response)` (`judge/prompts.py:36-44`) assembles the full per-case prompt from the two constants and the case's `question`, `answer`, and `contexts`.
- `gnomon.judge.ollama.parse_v1_judge_response(content)` (`judge/ollama.py:34-46`) is the public parse function and raises `JudgeProtocolError` for any shape violation, and can also be imported directly from `gnomon.judge.ollama`.

This is the stable v1 surface introduced by gnomon-eval#47 so that downstream consumers, including glyph ADR-G8, can pin against it instead of duplicating the prompt text or the parsing. A semantic change here is a visible API change in gnomon's own test suite.

---

## Summary of the 3 points that most affect P3.0

1. **Per-case quality scores do not come out of `run_eval`** — you need to call `judge.score` per case (or patch the runner) for your own percentile bootstrap. `aggregate_metric` already does a seeded percentile bootstrap and is reusable.
2. **v1 metrics are reference-free in practice** — the judge ignores `expected_answer`/`expected_contexts` (even though the schema requires them). `faithfulness` needs the generated `answer`; `context_precision` does not.
3. **Built-in judge = local Ollama**, 1 call per `(case, run)`, cost = `len(cases) * judge_runs`. No external client to configure beyond `model`/`base_url` in the TOML.
