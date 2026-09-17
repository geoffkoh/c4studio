"""Dynamic perspectives: values fetched from a URL (PP-179).

A perspective may carry a ``url`` instead of a fixed ``value``. Upstream's
viewer polls it and shows the response as the live value, falling back to
the HTTP status code when the body is empty or the request fails
(``runDynamicPerspective`` in ``structurizr-diagram.js``).

**Off unless asked for.** This is the second feature that leaves the
machine, after the assistant, and it differs from the assistant in that
the URLs come from the *workspace file* rather than from a setting — so
opening someone else's model must not make this machine call their hosts.
``c4 webapp --dynamic-perspectives`` is the switch, the capability is
reported by ``GET /api/capabilities``, and the route refuses with 403
when it is off.

Fetching happens here, on the server, rather than in the page: the
browser could not reach most hosts without CORS headers, and a failure
there would be silent. Here it is one place that can be timed out, capped
and reported.

Only ``http`` and ``https`` are followed. A workspace is a file like any
other, and ``file://`` in one must not turn a diagram into a way to read
this disk.
"""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from urllib.parse import urlparse

from c4studio.graph.view_graph import perspectives_by_element
from c4studio.models import Perspective, Workspace

#: Upstream's `structurizr.perspective.timeout`, in seconds.
DEFAULT_TIMEOUT_SECONDS = 10.0

#: Most of a response is a status word or a number; anything longer is
#: not a badge, and reading it all would let one URL hold the poll open.
MAX_VALUE_BYTES = 256

#: How many distinct URLs one refresh will call, so a large model cannot
#: turn a single poll into hundreds of outbound requests.
MAX_REQUESTS = 50

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class PerspectiveFetchError(Exception):
    """Raised when a refresh cannot be attempted at all."""


def dynamic_urls(workspace: Workspace, name: str) -> list[str]:
    """Every distinct URL perspective ``name`` reads its value from.

    Keyed by URL rather than by item because a relationship declared in
    DSL has no id of its own — the graph layer names its edge after its
    endpoints, per view — and because two items watching one endpoint
    should cost one request, not two. The client already knows which of
    its items carry which URL.

    Args:
        workspace: The workspace to scan.
        name: The perspective being shown.

    Returns:
        Distinct URLs in model order, capped at :data:`MAX_REQUESTS`.
    """
    urls: list[str] = []
    seen: set[str] = set()

    def collect(perspectives: list[Perspective]) -> None:
        for perspective in perspectives:
            if perspective.name.strip() != name or not perspective.url:
                continue
            if perspective.url not in seen:
                seen.add(perspective.url)
                urls.append(perspective.url)

    for perspectives in perspectives_by_element(workspace).values():
        collect(perspectives)
    for relationship in workspace.relationships:
        collect(relationship.perspectives)
    return urls[:MAX_REQUESTS]


def fetch_value(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Read one perspective's live value.

    Follows upstream: the response body is the value, and an empty body or
    a failed request falls back to the HTTP status code — a perspective
    that says ``503`` is more use than one that silently keeps its old
    value.

    Args:
        url: The URL to read.
        timeout: Seconds to wait before giving up.

    Returns:
        The value to show. Never raises for a failed request.

    Raises:
        PerspectiveFetchError: If the URL is not ``http``/``https``.
    """
    scheme = urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise PerspectiveFetchError(
            f"{scheme or 'relative'} URLs are not fetched; use http or https"
        )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            # The scheme is checked above, which is what S310 is about.
            body = response.read(MAX_VALUE_BYTES).decode("utf-8", "replace").strip()
            return body or str(response.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # A hostname that does not resolve has no status code to report,
        # so the reason is the value — it is going on a badge either way.
        return _short_reason(exc)


def _short_reason(exc: Exception) -> str:
    """A badge-sized description of why a fetch failed."""
    reason = getattr(exc, "reason", None)
    text = str(reason if reason is not None else exc).strip()
    return (text[:40] or "unreachable") if text else "unreachable"


async def refresh_values(
    workspace: Workspace,
    name: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, str]:
    """Read the live value behind every URL perspective ``name`` declares.

    The URLs are read concurrently in worker threads — ``urlopen`` blocks,
    and one slow host must not decide how long the whole refresh takes.

    Args:
        workspace: The loaded workspace.
        name: The perspective being shown.
        timeout: Per-request timeout in seconds.

    Returns:
        URL → value. A perspective with a fixed value contributes nothing:
        there was nothing to read, and the client already has it.
    """
    urls = dynamic_urls(workspace, name)
    if not urls:
        return {}
    values = await asyncio.gather(
        *(asyncio.to_thread(_safe_fetch, url, timeout) for url in urls)
    )
    return dict(zip(urls, values, strict=True))


def _safe_fetch(url: str, timeout: float) -> str:
    """``fetch_value`` with the scheme refusal turned into a badge value."""
    try:
        return fetch_value(url, timeout)
    except PerspectiveFetchError as exc:
        return str(exc)[:40]
