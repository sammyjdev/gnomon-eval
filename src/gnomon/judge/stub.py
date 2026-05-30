"""Deterministic stand-in judge for the vertical slice.

A real judge is an LLM whose scores wobble between runs. The StubJudge
reproduces that shape — N runs, each a different score — while being a pure
function of (seed, case, run). That is exactly what lets the reproducibility
suite assert "same seed, same result" and what lets the metrics layer compute
a non-trivial confidence interval.

Phase 2 replaces this with an Ollama-backed judge behind the same contract;
the cache identity tuple (case, response, judge model, seed) lands there.
"""

import hashlib
import random

from gnomon.domain.models import EvalCase, MetricScores, RagResponse
from gnomon.metrics.names import V1_METRICS


class StubJudge:
    """Seeded judge that scores faithfulness with reproducible jitter."""

    model_name = "stub-judge"

    def __init__(self, *, base: float = 0.85, jitter: float = 0.08) -> None:
        self._base = base
        self._jitter = jitter

    def score(self, case: EvalCase, response: RagResponse, *, seed: int, run: int) -> MetricScores:
        scores: dict[str, float] = {}
        for metric in V1_METRICS:
            rng = random.Random(self._derive_seed(metric, case, response, seed, run))
            raw = self._base + rng.uniform(-self._jitter, self._jitter)
            scores[metric] = max(0.0, min(1.0, raw))
        return MetricScores(scores=scores)

    def _derive_seed(
        self, metric: str, case: EvalCase, response: RagResponse, seed: int, run: int
    ) -> int:
        # hashlib, not hash(): the latter is salted per process and would
        # break cross-process reproducibility.
        identity = f"{seed}|{self.model_name}|{metric}|{case.id}|{response.answer}|{run}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return int(digest[:16], 16)
