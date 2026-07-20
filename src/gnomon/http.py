"""Thin HTTP seam so target adapter and judge stay testable without network.

Concrete adapters depend on the HttpTransport Protocol, not on urllib, so a
test injects a fake transport and no socket is opened. The stdlib
UrllibTransport keeps the dependency footprint at zero beyond pydantic.
"""

import json
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable


class TransportError(Exception):
    """Network-level failure: connection refused, timeout, unreachable host."""


@runtime_checkable
class HttpTransport(Protocol):
    def post_json(
        self, url: str, payload: dict, *, headers: dict[str, str], timeout_s: float
    ) -> tuple[int, dict]:
        """POST payload as JSON; return (status_code, parsed_body)."""
        ...


class UrllibTransport:
    """Default HttpTransport over the standard library."""

    def post_json(
        self, url: str, payload: dict, *, headers: dict[str, str], timeout_s: float
    ) -> tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - endpoint is caller-configured harness input.
            url,
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - request uses the caller-configured endpoint.
                request, timeout=timeout_s
            ) as response:
                body = response.read().decode("utf-8")
                return response.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as exc:  # non-2xx with a body
            body = exc.read().decode("utf-8")
            return exc.code, (json.loads(body) if body else {})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(f"POST {url} failed: {exc}") from exc
