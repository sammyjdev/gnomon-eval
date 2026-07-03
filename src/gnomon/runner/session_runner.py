"""Dual-arm replay runner for scripted sessions."""

from pydantic import BaseModel, ConfigDict

from gnomon.domain.models import MetricResult
from gnomon.domain.session import Arm, Session, TurnCost
from gnomon.metrics.confidence import aggregate_metric

ARMS: tuple[Arm, Arm] = ("axon", "baseline")


class SessionRunReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    turn_costs: list[TurnCost]
    final_faithfulness: dict[str, MetricResult]


def run_sessions(
    sessions: list[Session],
    target,
    judge,
    *,
    judge_runs: int,
    seed: int,
    confidence_level: float = 0.95,
    window_turns: int = 0,
) -> SessionRunReport:
    if judge_runs < 1:
        raise ValueError(f"judge_runs must be >= 1, got {judge_runs}")

    turn_costs: list[TurnCost] = []
    scores: dict[Arm, list[float]] = {"axon": [], "baseline": []}

    for session in sessions:
        for arm in ARMS:
            history: list[dict[str, str]] = []
            final_question = ""
            final_answer = ""
            final_contexts: list[str] = []

            for turn_index, question in enumerate(session.turns):
                result = target.run_turn(history, question, arm=arm)
                turn_costs.append(
                    TurnCost(
                        session_id=session.id,
                        turn=turn_index,
                        arm=arm,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        total_tokens=result.total_tokens,
                        latency_ms=result.latency_ms,
                        usage_source=result.usage_source,
                    )
                )
                final_question = question
                final_answer = result.answer
                if arm == "axon":
                    window = history[-(2 * window_turns) :] if window_turns > 0 else []
                    final_contexts = [*result.contexts, *_serialize_history(window)]
                else:
                    final_contexts = _serialize_history(
                        [*history, {"role": "user", "content": question}]
                    )
                history.extend(
                    [
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": result.answer},
                    ]
                )

            if not final_contexts:
                # Zero admissible evidence means the answer is ungrounded by
                # the metric's own definition: score 0.0 without calling the
                # judge. For the axon arm with a window, final_contexts already
                # includes retrieved contexts plus forwarded history, so this
                # branch fires only when both are empty.
                scores[arm].append(0.0)
                continue

            run_scores = [
                judge.score_faithfulness(
                    final_question, final_answer, final_contexts, seed=seed, run=run
                )
                for run in range(judge_runs)
            ]
            scores[arm].append(sum(run_scores) / len(run_scores))

    return SessionRunReport(
        turn_costs=turn_costs,
        final_faithfulness={
            arm: aggregate_metric(
                f"final_faithfulness_{arm}",
                scores[arm],
                confidence_level=confidence_level,
                seed=seed,
            )
            for arm in ARMS
        },
    )


def _serialize_history(history: list[dict[str, str]]) -> list[str]:
    return [f"{message['role']}: {message['content']}" for message in history]
