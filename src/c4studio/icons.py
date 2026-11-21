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
import re
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import unquote
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

    return _encode(payload, media_type, url)


def file_data_uri(path: Path) -> str | None:
    """Read a local image and return it as a ``data:`` URI, or None.

    The counterpart of :func:`data_uri` for icons shipped beside a
    file-based theme (PP-199), with the same type and size rules. Upstream
    does the same conversion when it inlines a file theme
    (``ThemeUtils.inlineAllStylesFromTheme``), which is what lets every
    surface — the browser included — show the icon with no file server.

    Args:
        path: The image file.

    Returns:
        The encoded image, or None when it is missing, unreadable, not a
        supported image type, or too large.
    """
    media_type = _content_type(None, path.name)
    if media_type is None:
        logger.warning("Skipping icon %s: not a supported image", path)
        return None
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_ICON_BYTES + 1)
    except OSError as exc:
        logger.warning("Skipping icon %s: %s", path, exc)
        return None
    return _encode(payload, media_type, str(path))


def _encode(payload: bytes, media_type: str, source: str) -> str | None:
    """Base64 an image payload, refusing anything over the size cap."""
    if len(payload) > MAX_ICON_BYTES:
        logger.warning("Skipping icon %s: larger than %d bytes", source, MAX_ICON_BYTES)
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
    # The workspace logo (PP-237) is a theme's URL as often as a file. Once
    # embedded it can be measured, which the renderer needs to size it.
    logo = payload.get("workspaceIcon")
    if isinstance(logo, dict) and logo.get("src"):
        inlined = data_uri(logo["src"])
        if inlined is None:
            payload.pop("workspaceIcon")
        else:
            logo["src"] = inlined
            size = image_size(inlined)
            if size is not None and "aspect" not in logo:
                logo["aspect"] = round(size[0] / size[1], 4)
    return embedded


_SVG_LENGTH = re.compile(r"^\s*([0-9.]+)\s*(px)?\s*$")


def _svg_size(svg: str) -> tuple[float, float] | None:
    """An SVG's drawn size: its ``viewBox``, else plain ``width``/``height``."""
    root = re.search(r"<svg\b[^>]*>", svg, re.IGNORECASE)
    if root is None:
        return None
    tag = root.group(0)
    view_box = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', tag)
    if view_box:
        parts = view_box.group(1).replace(",", " ").split()
        if len(parts) == 4:
            try:
                width, height = float(parts[2]), float(parts[3])
            except ValueError:
                return None
            return (width, height) if width > 0 and height > 0 else None
    sizes: list[float] = []
    for name in ("width", "height"):
        found = re.search(rf'\b{name}\s*=\s*["\']([^"\']+)["\']', tag)
        length = _SVG_LENGTH.match(found.group(1)) if found else None
        if length is None:
            return None
        sizes.append(float(length.group(1)))
    return (sizes[0], sizes[1]) if sizes[0] > 0 and sizes[1] > 0 else None


def _jpeg_size(data: bytes) -> tuple[float, float] | None:
    """Walk JPEG segments to the first start-of-frame marker."""
    index = 2
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        # SOF0-SOF15, less DHT (C4), JPG (C8) and DAC (CC).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return (float(width), float(height)) if width and height else None
        index += 2 + length
    return None


def _decode(uri: str) -> tuple[str, bytes] | None:
    """A ``data:`` URI's media type and bytes, or None for anything else."""
    if not uri.startswith("data:") or "," not in uri:
        return None
    header, _, payload = uri.partition(",")
    try:
        if header.endswith(";base64"):
            data = base64.b64decode(payload, validate=False)
        else:
            data = unquote(payload).encode("utf-8")
    except ValueError:
        return None
    return header[5:].split(";")[0].lower(), data


#: Every colour an SVG paints with, as an attribute or a style declaration.
_SVG_PAINT = re.compile(
    r"""(?:fill|stroke|stop-color|color)\s*(?:=\s*["']|:\s*)([^"';>]+)""",
    re.IGNORECASE,
)


@lru_cache(maxsize=256)
def paints_in_current_color(uri: str) -> bool:
    """Whether a ``data:`` SVG paints only in ``currentColor``.

    Such an icon asks to be drawn in the colour around it, which an
    ``<img>`` cannot give it: drawn as it is, it comes out black. Tabler
    (PP-239), Lucide and Feather are drawn this way, so an element with one
    is tinted to its text colour without being asked (``view_graph``).
    """
    decoded = _decode(uri)
    if decoded is None or decoded[0] != "image/svg+xml":
        return False
    svg = decoded[1].decode("utf-8", errors="replace")
    paints = {value.strip().lower() for value in _SVG_PAINT.findall(svg)}
    return "currentcolor" in paints and paints <= {"currentcolor", "none"}


def image_size(uri: str) -> tuple[float, float] | None:
    """The intrinsic size of a ``data:`` image, read from its header.

    For the workspace logo (PP-237): the headless renderer has no DOM to
    measure an image with, and a logo drawn in a square box would shrink
    a wide wordmark to nothing. PNG, GIF, JPEG and SVG are read; anything
    else, or a URL not yet embedded, is None and the caller assumes a
    square.
    """
    decoded = _decode(uri)
    if decoded is None:
        return None
    media_type, data = decoded
    if media_type == "image/svg+xml":
        return _svg_size(data.decode("utf-8", errors="replace"))
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return (float(width), float(height)) if width and height else None
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return (float(width), float(height)) if width and height else None
    if data[:2] == b"\xff\xd8":
        return _jpeg_size(data)
    return None
