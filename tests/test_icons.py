"""Theme icons embedded as data: URIs for headless rendering (PP-94).

Everything here works over ``file://`` URLs, so the suite stays offline
and deterministic; the fetch path is the same one real theme icons take.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from urllib.request import urlopen

from c4studio import icons
from c4studio.icons import MAX_ICON_BYTES, data_uri, inline_icons

# A one-pixel PNG, small enough to inline in the test.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """The fetch cache is per process; tests must not share entries."""
    data_uri.cache_clear()


def _icon_file(tmp_path: Path, name: str = "logo.png") -> str:
    path = tmp_path / name
    path.write_bytes(PNG_BYTES)
    return path.as_uri()


def _payload(*urls: str) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": f"n{i}", "data": {"label": f"N{i}", "kind": "container", "icon": u}}
            for i, u in enumerate(urls)
        ],
        "edges": [],
    }


class TestDataUri:
    def test_embeds_an_image(self, tmp_path: Path) -> None:
        uri = data_uri(_icon_file(tmp_path))
        assert uri is not None
        assert uri.startswith("data:image/png;base64,")
        assert base64.b64decode(uri.split(",", 1)[1]) == PNG_BYTES

    def test_passes_through_an_existing_data_uri(self) -> None:
        original = "data:image/svg+xml;base64,PHN2Zy8+"
        assert data_uri(original) == original

    def test_unreachable_icon_is_skipped(self, tmp_path: Path) -> None:
        assert data_uri((tmp_path / "missing.png").as_uri()) is None

    def test_non_image_is_skipped(self, tmp_path: Path) -> None:
        """An error page served as HTML must not be base64'd into a node."""
        path = tmp_path / "oops.html"
        path.write_text("<html>404</html>", encoding="utf-8")
        assert data_uri(path.as_uri()) is None

    def test_oversized_icon_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "huge.png"
        path.write_bytes(b"\x89PNG" + b"\0" * (MAX_ICON_BYTES + 10))
        assert data_uri(path.as_uri()) is None

    def test_fetched_once_per_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Twenty instances of one service must not mean twenty fetches."""
        url = _icon_file(tmp_path)
        calls: list[str] = []
        real = urlopen

        def counting(request: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append(str(request))
            return real(request, *args, **kwargs)

        monkeypatch.setattr(icons, "urlopen", counting)
        payload = _payload(*[url] * 20)
        assert inline_icons(payload) == 20
        assert len(calls) == 1


class TestInlineIcons:
    def test_replaces_urls_in_place(self, tmp_path: Path) -> None:
        payload = _payload(_icon_file(tmp_path))
        assert inline_icons(payload) == 1
        assert payload["nodes"][0]["data"]["icon"].startswith("data:image/png")

    def test_drops_icons_that_cannot_be_fetched(self, tmp_path: Path) -> None:
        """The diagram still renders; it just has no logo on that node."""
        payload = _payload((tmp_path / "gone.png").as_uri())
        assert inline_icons(payload) == 0
        assert "icon" not in payload["nodes"][0]["data"]

    def test_nodes_without_icons_are_untouched(self) -> None:
        payload: dict[str, Any] = {
            "nodes": [{"id": "a", "data": {"label": "A", "kind": "system"}}],
            "edges": [],
        }
        assert inline_icons(payload) == 0
        assert payload["nodes"][0]["data"] == {"label": "A", "kind": "system"}

    def test_a_failing_icon_does_not_stop_the_others(self, tmp_path: Path) -> None:
        payload = _payload(
            (tmp_path / "gone.png").as_uri(),
            _icon_file(tmp_path, "good.png"),
        )
        assert inline_icons(payload) == 1
        assert "icon" not in payload["nodes"][0]["data"]
        assert payload["nodes"][1]["data"]["icon"].startswith("data:")
