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
    """Wraps DeepEval's model interface to try NIM first, fall back to local
    Ollama on any failure -- required per this feature's design doc (no free
    hosted judge is assumed reliable enough to be a single point of failure)."""
    from deepeval.models import DeepEvalBaseLLM

    class NimThenOllama(DeepEvalBaseLLM):
        def load_model(self):
            return None

        def generate(self, prompt: str) -> str:
            try:
                return self._call_nim(prompt)
            except Exception as exc:  # noqa: BLE001 - any NIM failure falls back
                _logger.warning(
                    "NIM judge call failed (%s), falling back from %s to Ollama %s: %s",
                    type(exc).__name__,
                    cfg.primary_model,
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

    return NimThenOllama()


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


def run_chat_from_config(cfg: ChatRunConfig, *, pilot: bool):
    from deepeval.metrics import GEval, ToolCorrectnessMetric
    from deepeval.test_case import LLMTestCaseParams

    cases = load_chat_cases(cfg.dataset_path)
    if pilot:
        cases = cases[:5]

    target = ChatTarget(
        script_path=cfg.target.script_path, cwd=cfg.target.cwd, timeout_s=cfg.target.timeout_s
    )

    def tool_metric_factory():
        return ToolCorrectnessMetric()

    def geval_factory(criteria: str):
        return GEval(
            name="chat_criteria",
            criteria=criteria,
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=_build_judge_model(cfg.judge),
        )

    judge = ChatJudge(tool_metric_factory=tool_metric_factory, geval_factory=geval_factory)
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
