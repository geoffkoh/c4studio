"""Inline element icons as ``data:`` URIs for headless rendering.

Theme icons are remote URLs — the official AWS/Azure/GCP themes resolve
service logos relative to the theme URL — which a browser fetches happily
but which would make an exported SVG depend on the network. Headless
rendering therefore fetches each icon once and embeds it, so a rendered
file looks the same offline, in a wiki, or attached to a ticket.

Fetching fails soft, exactly as theme loading does: an icon that cannot be
retrieved is logged and dropped, and the element renders without it. A
render must never fail because a CDN is down.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from functools import lru_cache
from typing import Any
from urllib.request import urlopen

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT_SECONDS = 5.0

#: Icons larger than this are skipped rather than embedded. A service logo
#: is a few KB; anything approaching this is a mistake in the theme, and
#: base64 would inflate it by a third inside every diagram that uses it.
MAX_ICON_BYTES = 256 * 1024

#: Only image types worth embedding. Anything else is likely an error page
#: served with 200, which would otherwise be encoded and rendered as junk.
_ALLOWED_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp"}
)


def _content_type(header: str | None, url: str) -> str | None:
    """Best-effort media type: the served one, else the URL's extension."""
    if header:
        media_type = header.split(";")[0].strip().lower()
        if media_type in _ALLOWED_TYPES:
            return media_type
    guessed, _ = mimetypes.guess_type(url)
    if guessed in _ALLOWED_TYPES:
        return guessed
    return None


@lru_cache(maxsize=128)
def data_uri(url: str) -> str | None:
    """Fetch ``url`` and return it as a ``data:`` URI, or None if unusable.

    Cached per process, including failures, so a diagram with twenty
    instances of one service fetches once and an unreachable host is not
    retried for every node.
    """
    if url.startswith("data:"):
        return url
    try:
        with urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            media_type = _content_type(response.headers.get("Content-Type"), url)
            if media_type is None:
                logger.warning("Skipping icon %s: not a supported image", url)
                return None
            payload = response.read(MAX_ICON_BYTES + 1)
    except (OSError, ValueError) as exc:
        logger.warning("Skipping icon %s: %s", url, exc)
        return None

    if len(payload) > MAX_ICON_BYTES:
        logger.warning("Skipping icon %s: larger than %d bytes", url, MAX_ICON_BYTES)
        return None
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def inline_icons(payload: dict[str, Any]) -> int:
    """Replace icon URLs in a graph payload with ``data:`` URIs, in place.

    Args:
        payload: Graph data as ``webapp.graph.react_flow_graph`` returns it.

    Returns:
        How many nodes ended up with an embedded icon.
    """
    embedded = 0
    for node in payload.get("nodes", []):
        data = node.get("data", {})
        url = data.get("icon")
        if not url:
            continue
        inlined = data_uri(url)
        if inlined is None:
            data.pop("icon", None)
            continue
        data["icon"] = inlined
        embedded += 1
    return embedded
