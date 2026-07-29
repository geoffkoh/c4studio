"""FastAPI application factory and JSON API for the React web app.

The API is intentionally thin: it browses Structurizr sources under a root
directory, loads a selected workspace into :class:`AppState`, and serves
view metadata plus React Flow graph data. All mutable state lives on
``app.state`` (via dependency injection) so there are no module-level
globals.
"""

from __future__ import annotations

import dataclasses
import importlib.resources
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pystructurizr.models import View, Workspace
from pystructurizr.parser.locations import element_locations
from pystructurizr.webapp.view_graph import apply_positions, apply_sizes
from pystructurizr.webapp import graph, model_graph
from pystructurizr.webapp.loader import (
    WorkspaceLoadError,
    load_workspace,
    watched_files,
)


_SOURCE_SUFFIXES = frozenset({".dsl", ".json", ".structurizr"})
_SKIP_DIRS = frozenset({"node_modules", ".venv", "__pycache__"})
_MAX_DEPTH = 5


@dataclass
class AppState:
    """Mutable server state, stored on ``app.state``.

    Attributes:
        root: The directory sources are browsed and resolved within.
        current_path: The absolute path of the currently loaded source, if any.
        workspace: The currently loaded workspace, if any.
        diagrams: Per-view-key cache of computed React Flow graph data.
        watch_files: Source files (root + !include targets) to watch.
        watch_token: mtime fingerprint of watch_files at last (re)load.
        generation: Bumped on every successful live reload so clients know
            to refetch.
        load_error: Parse error from the last failed live reload, if any.
        source_cache: Cached /api/source payload; cleared on (re)load.
        waypoints: Relationship bend points from the layout sidecar, as
            ``{view_key: {edge_id: [[x, y], ...]}}``. Held here rather than
            on the workspace because deployment and dynamic views synthesise
            edges that have no RelationshipView to hang vertices on.
    """

    root: Path
    current_path: Path | None = None
    workspace: Workspace | None = None
    diagrams: dict[str, dict[str, Any]] = field(default_factory=dict)
    watch_files: list[Path] = field(default_factory=list)
    watch_token: str = ""
    generation: int = 0
    load_error: str = ""
    source_cache: dict[str, Any] | None = None
    waypoints: dict[str, dict[str, list[list[int]]]] = field(default_factory=dict)


class LoadRequest(BaseModel):
    """Body for ``POST /api/load``."""

    path: str


class LayoutRequest(BaseModel):
    """Body for ``POST /api/views/{key}/layout``."""

    positions: dict[str, tuple[int, int]]
    # Boundary node dimensions, persisted alongside positions.
    sizes: dict[str, tuple[int, int]] = {}
    # Relationship bend points, keyed by edge id. An edge present with an
    # empty list has had its waypoints cleared.
    waypoints: dict[str, list[tuple[int, int]]] = {}


def _get_state(request: Request) -> AppState:
    """Return the :class:`AppState` attached to the running app."""
    state: AppState = request.app.state.app_state
    return state


def _require_workspace(state: AppState) -> Workspace:
    """Return the loaded workspace or raise 409 if none is loaded."""
    if state.workspace is None:
        raise HTTPException(status_code=409, detail="No workspace loaded")
    return state.workspace


def _safe_resolve(root: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``root``, rejecting traversal and bad suffixes.

    Args:
        root: The directory that resolved paths must stay within.
        rel: A relative path supplied by the client.

    Returns:
        The resolved absolute path.

    Raises:
        HTTPException: 400 if the path escapes ``root`` or has an unsupported
            suffix.
    """
    candidate = (root / rel).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Path escapes the root directory")
    if candidate.suffix.lower() not in _SOURCE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {candidate.suffix or '(none)'}",
        )
    return candidate


def _find_view(workspace: Workspace, key: str) -> View:
    """Return the view with ``key`` or raise 404."""
    for view in workspace.views:
        if view.key == key:
            return view
    raise HTTPException(status_code=404, detail=f"Unknown view key: {key}")


def _views_index(workspace: Workspace) -> list[dict[str, Any]]:
    """Return the serialisable index of all views in ``workspace``.

    The DSL ``default`` view (when set) is flagged and listed first so the
    frontend's pick-the-first-view behaviour opens it initially.
    """
    default_key = workspace.views.configuration.default_view
    entries = [
        {
            "key": view.key,
            "type": view.type.value,
            "title": view.title,
            "element_id": view.element_id,
            "supported": graph.is_supported(view),
            "default": bool(default_key) and view.key == default_key,
        }
        for view in workspace.views
    ]
    if default_key:
        entries.sort(key=lambda entry: not entry["default"])
    return entries


_WORKSPACE_RE = re.compile(r"^\s*workspace\b", re.MULTILINE)


def _is_workspace_root(path: Path) -> bool:
    """Whether a source file defines a workspace of its own.

    DSL sources split across files via ``!include`` contain fragment files
    (elements/relationships only) that cannot be loaded standalone; only
    files declaring a ``workspace`` block are offered in the browser. JSON
    exports are always complete workspaces.
    """
    if path.name.endswith(".layout.json"):
        return False  # layout sidecars are not loadable workspaces
    if path.suffix.lower() == ".json":
        return True
    try:
        with path.open(encoding="utf-8", errors="ignore") as handle:
            head = handle.read(8192)
    except OSError:
        return False
    return _WORKSPACE_RE.search(head) is not None


def _iter_source_files(root: Path) -> list[str]:
    """Return POSIX-relative paths of loadable source files under ``root``.

    Recurses up to ``_MAX_DEPTH`` levels, skipping hidden directories,
    well-known noise directories (``node_modules``, ``.venv`` ...) and DSL
    fragment files that only exist to be ``!include``-ed.
    """
    found: list[str] = []

    def walk(directory: Path, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.is_dir():
                if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                    continue
                walk(entry, depth + 1)
            elif entry.suffix.lower() in _SOURCE_SUFFIXES and _is_workspace_root(entry):
                found.append(entry.relative_to(root).as_posix())

    walk(root, 0)
    return found


def _watch_token(files: list[Path]) -> str:
    """Fingerprint of the given files' mtimes, for change detection."""
    parts: list[str] = []
    for file in files:
        try:
            parts.append(f"{file}:{file.stat().st_mtime_ns}")
        except OSError:
            parts.append(f"{file}:missing")
    return "|".join(parts)


def _begin_watching(state: AppState, path: Path) -> None:
    """Point live-reload watching at ``path`` and its include fragments."""
    state.watch_files = watched_files(path)
    state.watch_token = _watch_token(state.watch_files)
    state.load_error = ""
    state.source_cache = None


def _layout_sidecar(source: Path) -> Path:
    """Path of the layout sidecar stored next to a workspace source."""
    return source.with_name(f"{source.stem}.layout.json")


def _read_sidecar_data(source: Path) -> dict[str, Any]:
    """Read and parse the whole sidecar document, or ``{}`` if unusable."""
    sidecar = _layout_sidecar(source)
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_layout_sidecar(source: Path) -> dict[str, dict[str, list[int]]]:
    """Read the sidecar's ``{view_key: {element_id: [x, y]}}`` mapping."""
    views = _read_sidecar_data(source).get("views")
    return views if isinstance(views, dict) else {}


def _read_layout_waypoints(source: Path) -> dict[str, dict[str, list[list[int]]]]:
    """Read the sidecar's ``{view_key: {edge_id: [[x, y], ...]}}`` mapping.

    Kept in a separate top-level ``edges`` section rather than folded into
    ``views``, whose entries are element-id keyed: sidecars written before
    waypoints existed simply have no ``edges`` key and still load.
    """
    edges = _read_sidecar_data(source).get("edges")
    if not isinstance(edges, dict):
        return {}
    cleaned: dict[str, dict[str, list[list[int]]]] = {}
    for key, by_edge in edges.items():
        if not isinstance(by_edge, dict):
            continue
        points = {
            edge_id: [[int(p[0]), int(p[1])] for p in pts]
            for edge_id, pts in by_edge.items()
            if isinstance(pts, list)
            and all(isinstance(p, list) and len(p) == 2 for p in pts)
        }
        if points:
            cleaned[key] = points
    return cleaned


def _write_layout_sidecar(
    source: Path,
    views: dict[str, dict[str, list[int]]],
    waypoints: dict[str, dict[str, list[list[int]]]],
) -> Path:
    """Write both sidecar sections, removing the file when nothing is left."""
    sidecar = _layout_sidecar(source)
    document: dict[str, Any] = {"version": 1, "views": views}
    if waypoints:
        document["edges"] = waypoints
    if not views and not waypoints:
        sidecar.unlink(missing_ok=True)
        return sidecar
    sidecar.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    return sidecar


def _attach_waypoints(
    data: dict[str, Any], waypoints: dict[str, list[list[int]]]
) -> None:
    """Add saved bend points onto matching edges of a graph payload.

    Edges whose id no longer appears in the view are simply skipped: the
    stale entry stays in the sidecar until that view's layout is saved
    again, and never reaches the client.
    """
    if not waypoints:
        return
    for edge in data.get("edges", []):
        points = waypoints.get(edge.get("id", ""))
        if points:
            edge["waypoints"] = [[int(x), int(y)] for x, y in points]


def _apply_saved_layout(state: AppState) -> None:
    """Apply sidecar positions onto the loaded workspace's views."""
    if state.workspace is None or state.current_path is None:
        return
    # Waypoints stay on the state: they are keyed by edge id, and synthesised
    # deployment/dynamic edges have no RelationshipView to hold them.
    state.waypoints = _read_layout_waypoints(state.current_path)
    saved = _read_layout_sidecar(state.current_path)
    if not saved:
        return
    views_by_key = {view.key: view for view in state.workspace.views}
    for key, positions in saved.items():
        view = views_by_key.get(key)
        if view is None or not isinstance(positions, dict):
            continue
        entries = {
            eid: geometry
            for eid, geometry in positions.items()
            if isinstance(geometry, list) and len(geometry) in (2, 4)
        }
        apply_positions(
            view,
            {eid: (int(g[0]), int(g[1])) for eid, g in entries.items()},
        )
        apply_sizes(
            view,
            {eid: (int(g[2]), int(g[3])) for eid, g in entries.items() if len(g) == 4},
        )


def create_app(
    root: Path, initial: Path | None = None, static_dir: Path | None = None
) -> FastAPI:
    """Build the FastAPI app serving the web backend.

    Args:
        root: Directory that sources are browsed and resolved within.
        initial: Optional source to load eagerly on startup.
        static_dir: Directory holding the built SPA. When ``None`` the
            packaged ``pystructurizr/webapp/static`` directory is used.

    Returns:
        A configured :class:`fastapi.FastAPI` instance.
    """
    root = root.resolve()
    app = FastAPI(title="pystructurizr webapp")
    state = AppState(root=root)

    if initial is not None:
        initial = initial.resolve()
        state.workspace = load_workspace(initial)
        state.current_path = initial
        _begin_watching(state, initial)
        _apply_saved_layout(state)

    app.state.app_state = state

    @app.get("/api/files")
    def list_files(state: AppState = Depends(_get_state)) -> list[str]:
        """List relative paths of all source files under the root."""
        return _iter_source_files(state.root)

    @app.post("/api/load")
    def load(
        body: LoadRequest, state: AppState = Depends(_get_state)
    ) -> dict[str, Any]:
        """Load the workspace at the given relative path."""
        path = _safe_resolve(state.root, body.path)
        try:
            workspace = load_workspace(path)
        except WorkspaceLoadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        state.workspace = workspace
        state.current_path = path
        state.diagrams.clear()
        _begin_watching(state, path)
        _apply_saved_layout(state)
        return {
            "path": path.relative_to(state.root).as_posix(),
            "name": workspace.name,
            "views": _views_index(workspace),
        }

    @app.get("/api/status")
    def status(state: AppState = Depends(_get_state)) -> dict[str, Any]:
        """Live-reload heartbeat: reload the workspace if its files changed.

        Returns the loaded path, a ``generation`` counter that increments on
        every successful reload (clients refetch when it changes), and the
        parse error of the last failed reload, if any — the previous good
        workspace stays served in that case.
        """
        if state.workspace is None or state.current_path is None:
            return {"path": None, "generation": state.generation, "error": None}
        current = _watch_token(state.watch_files)
        if current != state.watch_token:
            state.watch_token = current
            try:
                workspace = load_workspace(state.current_path)
            except WorkspaceLoadError as exc:
                state.load_error = str(exc)
            else:
                state.workspace = workspace
                state.diagrams.clear()
                _begin_watching(state, state.current_path)
                _apply_saved_layout(state)
                state.generation += 1
        return {
            "path": state.current_path.relative_to(state.root).as_posix(),
            "generation": state.generation,
            "error": state.load_error or None,
        }

    @app.get("/api/source")
    def get_source(state: AppState = Depends(_get_state)) -> dict[str, Any]:
        """Return the loaded workspace's DSL source files and element sites.

        ``files`` holds every DSL file (root plus ``!include`` fragments)
        with root-relative paths; ``locations`` maps element ids to the
        file and 1-based line where they are defined, for the source
        viewer's double-click-to-definition.
        """
        _require_workspace(state)
        if state.current_path is None:
            raise HTTPException(status_code=409, detail="No source file loaded")
        if state.source_cache is not None:
            return state.source_cache

        dsl_suffixes = {".dsl", ".structurizr"}
        files: list[dict[str, str]] = []
        seen: set[Path] = set()
        candidates = [state.current_path] + list(state.watch_files)
        for file in candidates:
            if file in seen:
                continue
            seen.add(file)
            if file.suffix.lower() not in dsl_suffixes and file != state.current_path:
                continue
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            try:
                rel = file.relative_to(state.root).as_posix()
            except ValueError:
                rel = file.name
            files.append({"path": rel, "content": content})

        locations: dict[str, dict[str, Any]] = {}
        if state.current_path.suffix.lower() in dsl_suffixes:
            for eid, (path, line) in element_locations(state.current_path).items():
                try:
                    rel = path.relative_to(state.root).as_posix()
                except ValueError:
                    rel = path.name
                locations[eid] = {"path": rel, "line": line}

        state.source_cache = {"files": files, "locations": locations}
        return state.source_cache

    @app.get("/api/workspace")
    def get_workspace(state: AppState = Depends(_get_state)) -> dict[str, Any]:
        """Return the full loaded workspace as a JSON-safe dict."""
        workspace = _require_workspace(state)
        return dataclasses.asdict(workspace)

    @app.get("/api/views")
    def get_views(state: AppState = Depends(_get_state)) -> list[dict[str, Any]]:
        """Return the index of all views in the loaded workspace."""
        workspace = _require_workspace(state)
        return _views_index(workspace)

    @app.get("/api/model/graph")
    def get_model_graph(
        level: str = "containers", state: AppState = Depends(_get_state)
    ) -> dict[str, Any]:
        """Return the full-model explorer graph at the given level.

        ``level`` is one of ``systems``, ``containers`` or ``components``
        and controls how deep the element hierarchy is exploded. The
        payload also carries a flat element search index, the declared
        relationships and an element-to-view-keys membership map.
        """
        workspace = _require_workspace(state)
        if level not in model_graph.LEVELS:
            raise HTTPException(
                status_code=400,
                detail=f"level must be one of {', '.join(model_graph.LEVELS)}",
            )
        cache_key = f"__model__::{level}"
        if cache_key not in state.diagrams:
            state.diagrams[cache_key] = model_graph.model_graph(workspace, level)
        return state.diagrams[cache_key]

    @app.get("/api/views/{key}/graph")
    def get_view_graph(
        key: str, expand: str = "", state: AppState = Depends(_get_state)
    ) -> dict[str, Any]:
        """Return React Flow graph data for the view with ``key``.

        ``expand`` is an optional comma-separated list of container ids to
        expand in place (container views only).
        """
        workspace = _require_workspace(state)
        expand_ids = {part for part in expand.split(",") if part}
        cache_key = f"{key}::{','.join(sorted(expand_ids))}"
        if cache_key in state.diagrams:
            return state.diagrams[cache_key]
        view = _find_view(workspace, key)
        data = graph.react_flow_graph(workspace, view, expand_ids or None)
        _attach_waypoints(data, state.waypoints.get(key, {}))
        state.diagrams[cache_key] = data
        return data

    def _invalidate_view_cache(state: AppState, key: str) -> None:
        for cached in [k for k in state.diagrams if k.split("::")[0] == key]:
            state.diagrams.pop(cached)

    @app.post("/api/views/{key}/layout")
    def save_layout(
        key: str, body: LayoutRequest, state: AppState = Depends(_get_state)
    ) -> dict[str, str]:
        """Persist node positions for a view to the layout sidecar.

        The sidecar (``<source>.layout.json``) holds a compact
        ``{view_key: {element_id: [x, y]}}`` mapping, merged per view and
        re-applied whenever the workspace is (re)loaded.
        """
        workspace = _require_workspace(state)
        if state.current_path is None:
            raise HTTPException(status_code=409, detail="No source file loaded")
        view = _find_view(workspace, key)
        apply_positions(view, dict(body.positions))
        apply_sizes(view, dict(body.sizes))
        _invalidate_view_cache(state, key)

        saved = _read_layout_sidecar(state.current_path)
        entries: dict[str, list[int]] = {
            eid: [int(x), int(y)] for eid, (x, y) in body.positions.items()
        }
        for eid, (width, height) in body.sizes.items():
            if eid in entries:
                entries[eid] += [int(width), int(height)]
        saved[key] = entries

        # An edge sent with an empty list has had its bend points cleared,
        # so drop it rather than persisting an empty entry.
        bends = {
            edge_id: [[int(x), int(y)] for x, y in points]
            for edge_id, points in body.waypoints.items()
            if points
        }
        all_waypoints = _read_layout_waypoints(state.current_path)
        if bends:
            all_waypoints[key] = bends
        else:
            all_waypoints.pop(key, None)
        state.waypoints = all_waypoints

        sidecar = _write_layout_sidecar(state.current_path, saved, all_waypoints)
        return {"saved": str(sidecar)}

    @app.delete("/api/views/{key}/layout")
    def delete_layout(
        key: str, state: AppState = Depends(_get_state)
    ) -> dict[str, str]:
        """Discard saved positions for a view (back to auto-layout)."""
        workspace = _require_workspace(state)
        if state.current_path is None:
            raise HTTPException(status_code=409, detail="No source file loaded")
        view = _find_view(workspace, key)
        view.element_views = [
            ve
            for ve in view.element_views
            if ve.x is None and ve.y is None and ve.width is None and ve.height is None
        ]
        _invalidate_view_cache(state, key)

        saved = _read_layout_sidecar(state.current_path)
        all_waypoints = _read_layout_waypoints(state.current_path)
        # Reset means back to auto-layout, which includes straight edges.
        if key in saved or key in all_waypoints:
            saved.pop(key, None)
            all_waypoints.pop(key, None)
            state.waypoints = all_waypoints
            _write_layout_sidecar(state.current_path, saved, all_waypoints)
        return {"reset": key}

    _mount_static(app, static_dir)
    return app


def _mount_static(app: FastAPI, static_dir: Path | None) -> None:
    """Mount the built SPA, or expose a hint if it is not built yet.

    Args:
        app: The application to mount static assets on.
        static_dir: Directory holding the built SPA. When ``None`` the
            packaged ``pystructurizr/webapp/static`` directory is used.
    """
    if static_dir is None:
        static_dir = Path(
            str(importlib.resources.files("pystructurizr.webapp") / "static")
        )
    if static_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="spa",
        )
    else:

        @app.get("/")
        def spa_not_built() -> dict[str, str]:
            """Explain that the frontend bundle is missing."""
            return {"detail": "frontend not built - run npm run build in frontend/"}


def run_server(root: Path, initial: Path | None, host: str, port: int) -> None:
    """Run the web backend with uvicorn.

    Args:
        root: Directory sources are browsed and resolved within.
        initial: Optional source to load eagerly on startup.
        host: Interface to bind to.
        port: TCP port to listen on.
    """
    import uvicorn

    uvicorn.run(create_app(root, initial), host=host, port=port, log_level="info")
