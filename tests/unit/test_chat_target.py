import json
import subprocess
import sys

import pytest

from gnomon.domain.chat import ChatCase
from gnomon.targets.chat_target import ChatTarget, ChatTargetRuntimeError

_LINA_CWD = "/path/to/lina-mvp"


class FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _case() -> ChatCase:
    return ChatCase(
        id="c1",
        conversation=[{"role": "user", "content": "Qual o horario?"}],
        tenant={"name": "Clinica Aurora", "tone": "amigavel"},
        expected_tools=["answer_question"],
    )


def _target(runner) -> ChatTarget:
    return ChatTarget(
        script_path="gateway/scripts/run_chateval_case.py",
        cwd=_LINA_CWD,
        subprocess_runner=runner,
    )


def test_run_parses_successful_subprocess_output():
    captured = {}

    def fake_runner(args, *, input, cwd, capture_output, text, timeout):
        captured["args"] = args
        captured["input"] = input
        captured["cwd"] = cwd
        return FakeCompletedProcess(
            0,
            json.dumps(
                {
                    "tool_called": "answer_question",
                    "tool_args": {"question": "Qual o horario?"},
                    "reply_text": "Funcionamos das 9h as 18h.",
                    "total_tokens": 50,
                }
            ),
        )

    result = _target(fake_runner).run(_case())

    assert result.tool_called == "answer_question"
    assert result.reply_text == "Funcionamos das 9h as 18h."
    assert result.total_tokens == 50
    assert captured["cwd"] == _LINA_CWD
    assert captured["args"][0] == sys.executable
    sent = json.loads(captured["input"])
    assert sent["conversation"] == _case().conversation


def test_run_raises_on_nonzero_exit():
    def failing_runner(args, *, input, cwd, capture_output, text, timeout):
        return FakeCompletedProcess(1, "", stderr="boom")

    with pytest.raises(ChatTargetRuntimeError):
        _target(failing_runner).run(_case())


def test_run_raises_on_unparseable_stdout():
    def bad_output_runner(args, *, input, cwd, capture_output, text, timeout):
        return FakeCompletedProcess(0, "not json")

    with pytest.raises(ChatTargetRuntimeError):
        _target(bad_output_runner).run(_case())


def test_run_raises_when_total_tokens_missing():
    def missing_tokens_runner(args, *, input, cwd, capture_output, text, timeout):
        return FakeCompletedProcess(0, json.dumps({"reply_text": "Oi!"}))

    with pytest.raises(ChatTargetRuntimeError):
        _target(missing_tokens_runner).run(_case())


def test_run_wraps_subprocess_timeout():
    def timing_out_runner(args, *, input, cwd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    with pytest.raises(ChatTargetRuntimeError):
        _target(timing_out_runner).run(_case())


def test_run_wraps_missing_executable_os_error():
    def missing_executable_runner(args, *, input, cwd, capture_output, text, timeout):
        raise FileNotFoundError("no such file or directory: python3")

    with pytest.raises(ChatTargetRuntimeError):
        _target(missing_executable_runner).run(_case())
