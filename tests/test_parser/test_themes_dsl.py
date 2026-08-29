"""``theme default`` selects the built-in theme, as in structurizr-java."""

from __future__ import annotations

from c4studio.parser.dsl import parse_dsl

DEFAULT_THEME_URL = "https://static.structurizr.com/themes/default/theme.json"


def _themes(body: str) -> list[str]:
    workspace = parse_dsl(
        'workspace "T" {\n    model {\n    }\n    views {\n'
        f"        {body}\n"
        "    }\n}\n"
    )
    return workspace.views.configuration.themes


def test_theme_default_resolves_to_the_builtin_url() -> None:
    assert _themes("theme default") == [DEFAULT_THEME_URL]


def test_theme_default_is_case_insensitive() -> None:
    """structurizr-java compares with equalsIgnoreCase."""
    assert _themes("theme Default") == [DEFAULT_THEME_URL]


def test_quoted_theme_url_still_works() -> None:
    assert _themes('theme "https://example.com/theme.json"') == [
        "https://example.com/theme.json"
    ]


def test_themes_accepts_default_alongside_urls() -> None:
    assert _themes('themes default "https://example.com/theme.json"') == [
        DEFAULT_THEME_URL,
        "https://example.com/theme.json",
    ]


def test_unknown_bare_theme_name_is_reported() -> None:
    """No installed-theme concept here, so say so rather than ignore it."""
    workspace = parse_dsl(
        'workspace "T" {\n    model {\n    }\n    views {\n'
        "        theme corporate\n"
        "    }\n}\n"
    )

    assert workspace.views.configuration.themes == []
    assert any("corporate" in d.message for d in workspace.diagnostics)
