"""Environment-variable expansion for config values.

Lets committed TOML configs reference per-machine values (Ollama hosts,
local repo paths) without hard-coding them: write ``${VAR}`` or
``${VAR:-default}`` and the real value comes from the environment (a
gitignored ``.env``), keeping private hosts/paths out of version control.
Only the explicit ``${...}`` form is touched; every other string is left as-is.
"""

from __future__ import annotations

import os
import re
from typing import Any

_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}")


def expand_env(obj: Any) -> Any:
    """Recursively expand ``${VAR}`` / ``${VAR:-default}`` in string values.

    Missing var with no default is left literal (surfaces the misconfig
    rather than silently blanking it).
    """
    if isinstance(obj, str):
        return _PATTERN.sub(_replace, obj)
    if isinstance(obj, dict):
        return {k: expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_env(v) for v in obj]
    return obj


def _replace(match: re.Match[str]) -> str:
    value = os.environ.get(match.group("name"))
    if value is not None:
        return value
    default = match.group("default")
    return default if default is not None else match.group(0)
