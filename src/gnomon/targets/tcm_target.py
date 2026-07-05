"""TCM test-body target for story quality evaluation.

Implements the RagTarget protocol. For each story description, extracts the
Story ID (pattern: S-<digits>), finds the matching test function body in the
tests directory, and returns it as context for the judge to evaluate.

Supports .py files via ast.parse and .ts/.tsx files via regex.
"""

import ast
import re
import time
from pathlib import Path

from gnomon.domain.models import RagResponse

_STORY_ID_RE = re.compile(r"S-(\d+)", re.IGNORECASE)
_TS_TEST_RE = re.compile(r'(?:it|test)\s*\(\s*[\'"]([^\'"]+)', re.IGNORECASE)

_NO_TEST_FOUND = "(no test found)"


def _normalize_id(story_id: str) -> list[str]:
    """'S-01' -> ['s01', 's_01', 's-01', 's 01']."""
    base = story_id.lower()  # 's-01'
    digits = re.sub(r"[^a-z0-9]", "", base)  # 's01'
    suffix = digits[1:]  # '01'
    return [digits, f"s_{suffix}", base, f"s {suffix}"]


def _find_py_body(path: Path, variants: list[str]) -> str | None:
    """Return source of the first matching function in a .py file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return None

    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not any(v in node.name.lower() for v in variants):
            continue
        end = getattr(node, "end_lineno", None)
        if end is None:
            return node.name
        return "".join(lines[node.lineno - 1 : end])
    return None


def _find_ts_body(path: Path, variants: list[str]) -> str | None:
    """Return a snippet starting at the first matching test label in a .ts/.tsx file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    for m in _TS_TEST_RE.finditer(source):
        label = m.group(1).lower()
        if any(v in label for v in variants):
            return source[m.start() : m.start() + 4096]
    return None


class TcmTarget:
    """RagTarget that serves test bodies for TCM story quality evaluation."""

    def __init__(self, plan_path: str, tests_dir: str) -> None:
        self._plan_path = plan_path
        self._tests_dir = Path(tests_dir)

    def query(self, story_description: str) -> RagResponse:
        """Find the test body for the Story ID in story_description.

        Returns a RagResponse where contexts[0] is the test function source,
        or '(no test found)' when no matching test exists.
        """
        m = _STORY_ID_RE.search(story_description)
        if not m:
            return RagResponse(answer="", contexts=[_NO_TEST_FOUND], total_tokens=0, latency_ms=0.0)

        variants = _normalize_id(f"S-{m.group(1)}")

        t0 = time.perf_counter()
        body = self._find_test(variants)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return RagResponse(
            answer="",
            contexts=[body if body is not None else _NO_TEST_FOUND],
            total_tokens=0,
            latency_ms=latency_ms,
        )

    def _find_test(self, variants: list[str]) -> str | None:
        """Walk tests_dir recursively and return the first matching test body."""
        if not self._tests_dir.exists():
            return None

        for path in sorted(self._tests_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix == ".py":
                body = _find_py_body(path, variants)
            elif path.suffix in (".ts", ".tsx"):
                body = _find_ts_body(path, variants)
            else:
                continue
            if body:
                return body
        return None
