"""Subprocess-based ChatEval target: shells out to lina-mvp's adapter script
per case (ADR-0001's adapter-based-target philosophy, extended from HTTP to
a subprocess boundary since the thing under evaluation here is a local repo's
own conversation loop, not a hosted API)."""

import json
import subprocess
import time
from collections.abc import Callable

from gnomon.domain.chat import ChatCase, ChatResult


class ChatTargetError(Exception):
    """Base for chat target failures."""


class ChatTargetRuntimeError(ChatTargetError):
    """The adapter script exited non-zero or returned unparseable output."""


class ChatTarget:
    def __init__(
        self,
        *,
        script_path: str,
        cwd: str,
        subprocess_runner: Callable | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._script_path = script_path
        self._cwd = cwd
        self._run = subprocess_runner or subprocess.run
        self._timeout_s = timeout_s

    def run(self, case: ChatCase) -> ChatResult:
        payload = json.dumps({"conversation": case.conversation, "tenant": case.tenant})
        start = time.perf_counter()
        completed = self._run(
            ["python3", self._script_path],
            input=payload,
            cwd=self._cwd,
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        if completed.returncode != 0:
            raise ChatTargetRuntimeError(
                f"adapter script exited {completed.returncode}: {completed.stderr}"
            )

        try:
            body = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ChatTargetRuntimeError(
                f"adapter script did not return valid JSON: {exc}"
            ) from exc

        try:
            return ChatResult(
                tool_called=body.get("tool_called"),
                tool_args=body.get("tool_args", {}),
                reply_text=body["reply_text"],
                total_tokens=body.get("total_tokens", 0),
                latency_ms=latency_ms,
            )
        except KeyError as exc:
            raise ChatTargetRuntimeError(
                f"adapter script response missing required field: {exc}"
            ) from exc
