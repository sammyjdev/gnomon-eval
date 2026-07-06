"""One-command entrypoint (RNF-04): config in, report + gate exit code out.

Wires the pieces by configuration, never by editing source. Factories map the
declared kind/provider to a concrete RagTarget / Judge, so a new backend is a
config change. Exit code is the gate verdict (0 pass, 1 fail), which is what
makes the same command usable as a CI regression gate (RF-09).
"""

import argparse
import json
import logging
import os
import sys

from gnomon.config.chat_config import ChatRunConfig
from gnomon.config.run_config import JudgeConfig, RunConfig, SessionRunConfig, TargetConfig
from gnomon.dataset.chat_loader import load_chat_cases
from gnomon.dataset.loader import load_dataset
from gnomon.dataset.session_loader import load_sessions
from gnomon.domain.interfaces import Judge, RagTarget
from gnomon.gate.gate import evaluate_gate
from gnomon.judge.cache import JudgeCache
from gnomon.judge.chat_judge import ChatJudge
from gnomon.judge.ollama import OllamaJudge
from gnomon.judge.session_judge import SessionOllamaJudge
from gnomon.judge.stub import StubJudge
from gnomon.reporting.report import to_dict, to_text
from gnomon.reporting.savings import savings_report
from gnomon.reporting.savings import to_text as session_to_text
from gnomon.runner.chat_runner import run_chat_eval
from gnomon.runner.runner import run_eval
from gnomon.runner.session_runner import run_sessions
from gnomon.targets.chat_target import ChatTarget
from gnomon.targets.mock import MockTarget
from gnomon.targets.openai_compat import OpenAICompatTarget
from gnomon.targets.session_target import SessionTarget


def build_target(cfg: TargetConfig) -> RagTarget:
    if cfg.kind == "mock":
        return MockTarget(
            answer="The game master narrates the world.",
            contexts=["The game master narrates the world to the players."],
            total_tokens=137,
            latency_ms=512.0,
        )
    api_key = os.environ.get(cfg.api_key_env) if cfg.api_key_env else None
    return OpenAICompatTarget(
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=api_key,
        timeout_s=cfg.timeout_s,
        contexts_field=cfg.contexts_field,
        include_context=cfg.include_context,
    )


def build_judge(cfg: JudgeConfig) -> Judge:
    if cfg.provider == "stub":
        return StubJudge()
    return OllamaJudge(
        model=cfg.model,
        base_url=cfg.base_url,
        cache=JudgeCache(),
        timeout_s=cfg.timeout_s,
    )


_logger = logging.getLogger(__name__)


def _build_judge_model(cfg):
    """Wraps DeepEval's model interface to try NIM first, then an optional
    secondary provider (Groq, fast but still free-tier), then fall back to
    local Ollama on any failure -- required per this feature's design doc
    (no free hosted judge is assumed reliable enough to be a single point
    of failure). secondary_model is optional so existing configs without it
    keep the original NIM -> Ollama 2-tier behavior unchanged."""
    from deepeval.models import DeepEvalBaseLLM

    class NimThenGroqThenOllama(DeepEvalBaseLLM):
        def load_model(self):
            return None

        def generate(self, prompt: str) -> str:
            try:
                return self._call_nim(prompt)
            except Exception as exc:  # noqa: BLE001 - any NIM failure falls back
                if cfg.secondary_model:
                    _logger.warning(
                        "NIM judge call failed (%s), falling back from %s to Groq %s: %s",
                        type(exc).__name__,
                        cfg.primary_model,
                        cfg.secondary_model,
                        exc,
                    )
                    return self._call_groq_then_ollama(prompt)
                _logger.warning(
                    "NIM judge call failed (%s), falling back from %s to Ollama %s: %s",
                    type(exc).__name__,
                    cfg.primary_model,
                    cfg.fallback_model,
                    exc,
                )
                return self._call_ollama(prompt)

        def _call_groq_then_ollama(self, prompt: str) -> str:
            try:
                return self._call_groq(prompt)
            except Exception as exc:  # noqa: BLE001 - any Groq failure falls back
                _logger.warning(
                    "Groq judge call failed (%s), falling back from %s to Ollama %s: %s",
                    type(exc).__name__,
                    cfg.secondary_model,
                    cfg.fallback_model,
                    exc,
                )
                return self._call_ollama(prompt)

        async def a_generate(self, prompt: str) -> str:
            return self.generate(prompt)

        def get_model_name(self) -> str:
            return f"{cfg.primary_model} (fallback: {cfg.fallback_model})"

        def _call_nim(self, prompt: str) -> str:
            import litellm

            response = litellm.completion(
                model=f"nvidia_nim/{cfg.primary_model}",
                messages=[{"role": "user", "content": prompt}],
                timeout=10,
            )
            return response.choices[0].message.content

        def _call_groq(self, prompt: str) -> str:
            import litellm

            response = litellm.completion(
                model=f"groq/{cfg.secondary_model}",
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content

        def _call_ollama(self, prompt: str) -> str:
            import litellm

            response = litellm.completion(
                model=f"ollama/{cfg.fallback_model}",
                api_base=cfg.fallback_base_url,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content

    return NimThenGroqThenOllama()


def run_from_config(cfg: RunConfig):
    cases = load_dataset(cfg.dataset_path)
    target = build_target(cfg.target)
    judge = build_judge(cfg.judge)
    report = run_eval(cases, target, judge, cfg.eval)
    gate = evaluate_gate(report, cfg.gate.thresholds)
    return report, gate


def run_session_from_config(cfg: SessionRunConfig) -> dict:
    # Fail loudly on config values the session command does not implement:
    # SessionConfig inherits TargetConfig fields and reuses JudgeConfig, but
    # only the HTTP openai_compat target and the live ollama judge are wired.
    if cfg.target.kind != "openai_compat":
        raise ValueError(
            f"session command supports target kind 'openai_compat', got {cfg.target.kind!r}"
        )
    if cfg.judge.provider != "ollama":
        raise ValueError(
            f"session command supports judge provider 'ollama', got {cfg.judge.provider!r}"
        )
    sessions = load_sessions(cfg.sessions_path)
    target = SessionTarget(
        base_url=cfg.target.base_url,
        model=cfg.target.model,
        timeout_s=cfg.target.timeout_s,
        recall_max_tokens=cfg.target.recall_max_tokens,
        window_turns=cfg.target.window_turns,
    )
    judge = SessionOllamaJudge(
        model=cfg.judge.model,
        base_url=cfg.judge.base_url,
        cache=JudgeCache(),
        timeout_s=cfg.judge.timeout_s,
    )
    report = run_sessions(
        sessions,
        target,
        judge,
        judge_runs=cfg.eval.judge_runs,
        seed=cfg.eval.seed,
        confidence_level=cfg.eval.confidence_level,
        window_turns=cfg.target.window_turns,
    )
    return savings_report(report, seed=cfg.eval.seed, confidence_level=cfg.eval.confidence_level)


def session_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gnomon session", description="Run a GNOMON session evaluation."
    )
    parser.add_argument("-c", "--config", required=True, help="path to the session run config TOML")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = parser.parse_args(argv)

    cfg = SessionRunConfig.from_file(args.config)
    report = run_session_from_config(cfg)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(session_to_text(report))
    return 0 if report["quality_gate"] == "pass" else 1


_PILOT_CASE_COUNT = 5


def _pilot_priority(case) -> int:
    # Cases without .criteria/.criteria_metric (e.g. plain test doubles)
    # fall through to the lowest priority rather than crashing.
    criteria = getattr(case, "criteria", None)
    metric = getattr(case, "criteria_metric", None)
    if criteria and metric == "hallucination":
        return 0
    if criteria and metric == "tone_brand":
        return 1
    return 2


def select_pilot_cases(cases: list, n: int = _PILOT_CASE_COUNT) -> list:
    """Pick --pilot's cases so all 3 gate metrics get representative coverage.

    A plain `cases[:n]` file-order slice structurally excludes the
    tone_brand/hallucination cases whenever they are not near the front of
    the dataset -- tool_selection_accuracy is scored for every case
    unconditionally, but those two are conditional on case.criteria, so
    pilot mode must deliberately front-load them. Sort is stable, so cases
    within the same priority keep their original relative order.
    """
    return sorted(cases, key=_pilot_priority)[:n]


def _print_pilot_case_score(case, result, case_scores: dict, reasons: dict) -> None:
    reply_excerpt = result.reply_text[:200]
    print(
        f"  case={case.id} tool_called={result.tool_called!r} "
        f"expected_tools={case.expected_tools!r} reply={reply_excerpt!r} "
        f"scores={case_scores}"
    )
    for metric_name, reason in reasons.items():
        if reason:
            print(f"    {metric_name} reason: {reason}")


class _PilotScorePrinter:
    """Wraps a judge so --pilot prints per-case scores as they're computed --
    pilot's whole point is a human sanity-checking the judge, which needs
    this per-case visibility (see run_chat_eval's own on_case_scored hook,
    used here at the CLI layer via wrapping instead of passing the kwarg
    through, so cli.run_chat_eval's call signature stays exactly what
    existing tests already monkeypatch against). Also prints each metric's
    .reason when the wrapped judge exposes a last_reasons mapping (ChatJudge
    does) -- a bare score can't explain a surprising result on its own."""

    def __init__(self, judge):
        self._judge = judge

    def score(self, case, result):
        case_scores = self._judge.score(case, result)
        reasons = getattr(self._judge, "last_reasons", {})
        _print_pilot_case_score(case, result, case_scores, reasons)
        return case_scores


def run_chat_from_config(cfg: ChatRunConfig, *, pilot: bool):
    from deepeval.metrics import GEval, ToolCorrectnessMetric
    from deepeval.test_case import LLMTestCaseParams

    cases = load_chat_cases(cfg.dataset_path)
    if pilot:
        cases = select_pilot_cases(cases)

    target = ChatTarget(
        script_path=cfg.target.script_path, cwd=cfg.target.cwd, timeout_s=cfg.target.timeout_s
    )

    def tool_metric_factory():
        return ToolCorrectnessMetric(model=_build_judge_model(cfg.judge))

    def geval_factory(criteria: str):
        return GEval(
            name="chat_criteria",
            criteria=criteria,
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=_build_judge_model(cfg.judge),
        )

    judge = ChatJudge(tool_metric_factory=tool_metric_factory, geval_factory=geval_factory)
    if pilot:
        judge = _PilotScorePrinter(judge)
    report = run_chat_eval(cases, target, judge, seed=cfg.seed)
    gate = evaluate_gate(report, cfg.gate.thresholds)
    return report, gate


def chat_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gnomon chat", description="Run a ChatEval evaluation.")
    parser.add_argument("-c", "--config", required=True, help="path to the chat run config TOML")
    parser.add_argument("--pilot", action="store_true", help="run only the first 5 cases")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = parser.parse_args(argv)

    cfg = ChatRunConfig.from_file(args.config)
    report, gate = run_chat_from_config(cfg, pilot=args.pilot)

    if args.json:
        print(json.dumps(to_dict(report), indent=2))
    else:
        print(to_text(report))
    for failure in gate.failures:
        print(f"GATE FAIL: {failure}", file=sys.stderr)
    return 0 if gate.passed else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "session":
        return session_main(argv[1:])
    if argv and argv[0] == "chat":
        return chat_main(argv[1:])

    parser = argparse.ArgumentParser(prog="gnomon", description="Run a GNOMON evaluation.")
    parser.add_argument("-c", "--config", required=True, help="path to the run config TOML")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = parser.parse_args(argv)

    cfg = RunConfig.from_file(args.config)
    report, gate = run_from_config(cfg)

    if args.json:
        print(json.dumps(to_dict(report), indent=2))
    else:
        print(to_text(report))
    for failure in gate.failures:
        print(f"GATE FAIL: {failure}", file=sys.stderr)
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
