import json

import pytest

from gnomon.domain.chat import ChatCase
from gnomon.targets.chat_target import ChatTarget, ChatTargetRuntimeError


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
                }
            ),
        )

    target = ChatTarget(
        script_path="gateway/scripts/run_chateval_case.py",
        cwd="/Users/samdev/dev/lina",
        subprocess_runner=fake_runner,
    )
    result = target.run(_case())

    assert result.tool_called == "answer_question"
    assert result.reply_text == "Funcionamos das 9h as 18h."
    assert captured["cwd"] == "/Users/samdev/dev/lina"
    sent = json.loads(captured["input"])
    assert sent["conversation"] == _case().conversation


def test_run_raises_on_nonzero_exit():
    def failing_runner(args, *, input, cwd, capture_output, text, timeout):
        return FakeCompletedProcess(1, "", stderr="boom")

    target = ChatTarget(
        script_path="gateway/scripts/run_chateval_case.py",
        cwd="/Users/samdev/dev/lina",
        subprocess_runner=failing_runner,
    )
    with pytest.raises(ChatTargetRuntimeError):
        target.run(_case())


def test_run_raises_on_unparseable_stdout():
    def bad_output_runner(args, *, input, cwd, capture_output, text, timeout):
        return FakeCompletedProcess(0, "not json")

    target = ChatTarget(
        script_path="gateway/scripts/run_chateval_case.py",
        cwd="/Users/samdev/dev/lina",
        subprocess_runner=bad_output_runner,
    )
    with pytest.raises(ChatTargetRuntimeError):
        target.run(_case())
