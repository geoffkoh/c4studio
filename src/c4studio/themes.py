"""Remote Structurizr theme loading.

A workspace can reference themes by URL (``theme "https://..."`` in the
DSL, or ``views.configuration.themes`` in JSON). Each theme is a JSON
document of tag-matched element/relationship styles — this is how the
official cloud-provider themes (AWS, Azure, GCP) attach service logos:
their element styles map tags like ``Amazon Web Services - Lambda`` to an
``icon`` image resolved relative to the theme URL.

Theme styles are merged *before* the workspace's own styles, so anything
declared in the workspace wins. Fetches are cached per process; a theme
that cannot be fetched or parsed is logged and skipped (the diagram
renders with local styles only), and the failure is cached too so an
offline session does not re-block on timeouts every render.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen

from c4studio.models import (
    ElementStyle,
    RelationshipStyle,
    Shape,
    Styles,
    Workspace,
)

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT_SECONDS = 5.0


class ThemeLoadError(Exception):
    """A theme document could not be fetched or parsed."""


def _shape(raw: str | None) -> Shape | None:
    if raw is None:
        return None
    try:
        return Shape(raw)
    except ValueError:
        return None


def _element_style(data: dict[str, Any], base_url: str) -> ElementStyle:
    icon = data.get("icon", "")
    if icon and base_url:
        icon = urljoin(base_url, icon)
    return ElementStyle(
        tag=data.get("tag", ""),
        width=data.get("width"),
        height=data.get("height"),
        background=data.get("background", ""),
        stroke=data.get("stroke", ""),
        stroke_width=data.get("strokeWidth"),
        color=data.get("color", ""),
        font_size=data.get("fontSize"),
        shape=_shape(data.get("shape")),
        icon=icon,
        opacity=data.get("opacity"),
        metadata=data.get("metadata"),
        description=data.get("description"),
    )


def _relationship_style(data: dict[str, Any]) -> RelationshipStyle:
    return RelationshipStyle(
        tag=data.get("tag", ""),
        thickness=data.get("thickness"),
        color=data.get("color", ""),
        font_size=data.get("fontSize"),
        width=data.get("width"),
        dashed=data.get("dashed"),
        opacity=data.get("opacity"),
    )


def parse_theme(text: str, base_url: str = "") -> Styles:
    """Parse a Structurizr theme JSON document into style rules.

    Args:
        text: The theme document.
        base_url: The theme's own URL; relative ``icon`` entries (as used
            by the official cloud-provider themes) are resolved against it.

    Returns:
        The theme's element and relationship styles.

    Raises:
        ThemeLoadError: If the document is not valid theme JSON.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ThemeLoadError(f"Theme is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ThemeLoadError("Theme JSON must be an object.")
    return Styles(
        element_styles=[
            _element_style(e, base_url)
            for e in data.get("elements", [])
            if isinstance(e, dict)
        ],
        relationship_styles=[
            _relationship_style(r)
            for r in data.get("relationships", [])
            if isinstance(r, dict)
        ],
    )


@lru_cache(maxsize=32)
def _fetch(url: str) -> Styles:
    """Fetch and parse one theme, caching the outcome (success or failure)."""
    try:
        with urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8", errors="replace")
        return parse_theme(text, base_url=url)
    except (OSError, ValueError, ThemeLoadError) as exc:
        logger.warning("Skipping theme %s: %s", url, exc)
        return Styles()


def theme_styles(workspace: Workspace) -> Styles:
    """Resolve every theme the workspace references into merged styles.

    Args:
        workspace: The workspace whose ``configuration.themes`` to load.

    Returns:
        All referenced themes' styles in declaration order; empty when the
        workspace references no (reachable) themes.
    """
    merged = Styles()
    for url in workspace.views.configuration.themes:
        styles = _fetch(url)
        merged.element_styles.extend(styles.element_styles)
        merged.relationship_styles.extend(styles.relationship_styles)
    return merged
