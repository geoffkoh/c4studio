"""Dynamic perspectives: values read from a URL (PP-179).

Against a real HTTP server on localhost rather than a patched fetcher —
the thing worth pinning is that the *route* reaches a URL, times out, and
falls back the way upstream does, and a stub of `urlopen` would assert
none of it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.parser.dsl import parse_dsl
from c4studio.webapp.perspectives import (
    MAX_REQUESTS,
    PerspectiveFetchError,
    dynamic_urls,
    fetch_value,
)
from c4studio.webapp.server import create_app


class _Handler(BaseHTTPRequestHandler):
    """Answers `/up` with a body, `/empty` with none, `/gone` with a 404."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        if self.path == "/up":
            body = b"Operational"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/empty":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *args: Any) -> None:
        """Silence the default stderr logging."""


@pytest.fixture(scope="module")
def origin() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _workspace_source(origin: str) -> str:
    return f"""
    workspace "W" {{
        model {{
            a = softwareSystem "A" {{
                perspectives {{
                    perspective "Uptime" {{
                        description "Live status"
                        url "{origin}/up"
                    }}
                }}
            }}
            b = softwareSystem "B" {{
                perspectives {{
                    perspective "Uptime" {{
                        url "{origin}/gone"
                    }}
                }}
            }}
            c = softwareSystem "C" {{
                perspectives {{
                    "Uptime" "Fixed, not fetched" "Static"
                }}
            }}
            rel = a -> b "Calls" {{
                perspectives {{
                    perspective "Uptime" {{
                        url "{origin}/empty"
                    }}
                }}
            }}
        }}
        views {{
            systemLandscape L {{
                include *
            }}
        }}
    }}
    """


@pytest.fixture()
def client(tmp_path: Path, origin: str) -> Iterator[TestClient]:
    source = tmp_path / "workspace.dsl"
    source.write_text(_workspace_source(origin), encoding="utf-8")
    app = create_app(tmp_path, source, dynamic_perspectives=True)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def guarded_client(tmp_path: Path, origin: str) -> Iterator[TestClient]:
    """The default server: the flag was never passed."""
    source = tmp_path / "workspace.dsl"
    source.write_text(_workspace_source(origin), encoding="utf-8")
    with TestClient(create_app(tmp_path, source)) as test_client:
        yield test_client


class TestTheSwitch:
    def test_off_by_default_and_the_route_refuses(
        self, guarded_client: TestClient
    ) -> None:
        """The guarantee lives on the server, not in a hidden button."""
        capabilities = guarded_client.get("/api/capabilities").json()
        assert capabilities["features"]["dynamicPerspectives"] is False

        response = guarded_client.get("/api/perspectives/Uptime/values")
        assert response.status_code == 403
        assert "--dynamic-perspectives" in response.json()["detail"]

    def test_on_when_asked_for(self, client: TestClient) -> None:
        capabilities = client.get("/api/capabilities").json()
        assert capabilities["features"]["dynamicPerspectives"] is True


class TestFetching:
    def test_values_come_back_keyed_by_url(
        self, client: TestClient, origin: str
    ) -> None:
        values = client.get("/api/perspectives/Uptime/values").json()["values"]
        # The body is the value, as upstream reads it.
        assert values[f"{origin}/up"] == "Operational"
        # A failed request falls back to the status code: a badge saying
        # 404 is more use than one silently keeping a stale value.
        assert values[f"{origin}/gone"] == "404"
        # An empty body falls back to the status too, and a relationship's
        # URL is read alongside the elements' — which is the reason these
        # are keyed by URL: a DSL relationship has no id to key on.
        assert values[f"{origin}/empty"] == "204"

    def test_a_fixed_value_is_not_fetched(
        self, client: TestClient, origin: str
    ) -> None:
        """Nothing was read for it, and the client already has it."""
        values = client.get("/api/perspectives/Uptime/values").json()["values"]
        assert list(values) == [f"{origin}/up", f"{origin}/gone", f"{origin}/empty"]

    def test_an_unknown_perspective_fetches_nothing(self, client: TestClient) -> None:
        values = client.get("/api/perspectives/Nope/values").json()["values"]
        assert values == {}


class TestRefusals:
    @pytest.mark.parametrize(
        "url", ["file:///etc/passwd", "ftp://example.com/x", "/relative"]
    )
    def test_only_http_and_https_are_followed(self, url: str) -> None:
        """A workspace is a file like any other; `file://` in one must not
        turn a diagram into a way to read this disk."""
        with pytest.raises(PerspectiveFetchError):
            fetch_value(url)

    def test_a_refused_scheme_reaches_the_badge_as_a_reason(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "workspace.dsl"
        source.write_text(
            """
            workspace "W" {
                model {
                    a = softwareSystem "A" {
                        perspectives {
                            perspective "Uptime" {
                                url "file:///etc/passwd"
                            }
                        }
                    }
                }
                views {
                    systemLandscape L {
                        include *
                    }
                }
            }
            """,
            encoding="utf-8",
        )
        app = create_app(tmp_path, source, dynamic_perspectives=True)
        with TestClient(app) as client:
            values = client.get("/api/perspectives/Uptime/values").json()["values"]
        assert "not fetched" in values["file:///etc/passwd"]

    def test_one_refresh_is_capped(self, origin: str) -> None:
        """A large model must not turn one poll into hundreds of calls."""
        items = "\n".join(
            f'''
            s{i} = softwareSystem "S{i}" {{
                perspectives {{
                    perspective "Uptime" {{
                        url "{origin}/up?s={i}"
                    }}
                }}
            }}'''
            for i in range(MAX_REQUESTS + 5)
        )
        workspace = parse_dsl(
            f'workspace "W" {{ model {{ {items} }} views {{ systemLandscape L {{ include * }} }} }}'
        )
        assert len(dynamic_urls(workspace, "Uptime")) == MAX_REQUESTS
