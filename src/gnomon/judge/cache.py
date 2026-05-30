"""In-memory judge score cache keyed by the identity tuple (ADR-002, VAL-07).

Reproducibility needs the same (case.id, case.question, response.answer,
response.contexts, judge model, seed, run) to return the same score. The key
includes `run`: the N variance runs must each keep their own score, otherwise
the interval would collapse. Contexts are included because context_precision
depends on the retrieved contexts — different contexts with the same answer
must never collide. Any lookup whose tuple does not match exactly is a miss —
never a hit that would return a score computed for a different context.
"""

from gnomon.domain.models import EvalCase, MetricScores, RagResponse

_Key = tuple[str, str, str, tuple[str, ...], str, int, int]


class JudgeCache:
    def __init__(self) -> None:
        self._store: dict[_Key, MetricScores] = {}

    def _key(self, case: EvalCase, response: RagResponse, model: str, seed: int, run: int) -> _Key:
        return (case.id, case.question, response.answer, tuple(response.contexts), model, seed, run)

    def get(
        self, case: EvalCase, response: RagResponse, model: str, *, seed: int, run: int
    ) -> MetricScores | None:
        return self._store.get(self._key(case, response, model, seed, run))

    def put(
        self,
        case: EvalCase,
        response: RagResponse,
        model: str,
        *,
        seed: int,
        run: int,
        scores: MetricScores,
    ) -> None:
        self._store[self._key(case, response, model, seed, run)] = scores
