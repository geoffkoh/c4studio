"""FastAPI application factory and JSON API for the React web app.

The API is intentionally thin: it browses Structurizr sources under a root
directory, loads a selected workspace into :class:`AppState`, and serves
view metadata plus React Flow graph data. All mutable state lives on
``app.state`` (via dependency injection) so there are no module-level
globals.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import importlib.resources
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from c4studio.diagnostics import Diagnostic, Severity
from c4studio.models import View, Workspace
from c4studio.parser.dsl import ParseError, parse_dsl
from c4studio.parser.locations import element_locations
from c4studio.graph.view_graph import apply_positions, apply_sizes
from c4studio.webapp import graph, model_graph
from c4studio.webapp.loader import (
    WorkspaceLoadError,
    load_workspace,
    watched_files,
)


_SOURCE_SUFFIXES = frozenset({".dsl", ".json", ".structurizr"})
_SKIP_DIRS = frozenset({"node_modules", ".venv", "__pycache__"})
_MAX_DEPTH = 5


@dataclass(frozen=True)
class AppConfig:
    """Immutable per-app configuration, fixed at startup.

    Held on :class:`AppState` rather than in a module global so tests can
    build independent apps, and so every route keeps its single
    ``Depends(_get_state)``.

    Attributes:
        read_only: Serve in Viewer mode — DSL cannot be written. Layout
            and expansion state still persist: you cannot change the
            model, but you can arrange the view, and the sidecar holding
            that arrangement is gitignored per-user UI state either way.
    """

    read_only: bool = False


@dataclass
class AppState:
    """Mutable server state, stored on ``app.state``.

    Attributes:
        config: Immutable startup configuration (see :class:`AppConfig`).
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
        discovery: Cached /api/files walk, revalidated by stat rather than
            invalidated by an event — the tree changes underneath this
            server, so there is nothing to hook.
        waypoints: Relationship bend points from the layout sidecar, as
            ``{view_key: {edge_id: [[x, y], ...]}}``. Held here rather than
            on the workspace because deployment and dynamic views synthesise
            edges that have no RelationshipView to hang vertices on.
        labels: Dragged edge-label offsets, as
            ``{view_key: {edge_id: [dx, dy]}}``, relative to where the label
            would otherwise sit. Held here for the same reason as waypoints,
            and additionally because Structurizr has no per-view label
            position to store it in — upstream places labels with the
            ``position`` relationship style (0-100 along the line), so a
            free 2-D offset is ours alone and belongs in per-user UI state.
    """

    root: Path
    config: AppConfig = field(default_factory=AppConfig)
    current_path: Path | None = None
    workspace: Workspace | None = None
    diagrams: dict[str, dict[str, Any]] = field(default_factory=dict)
    watch_files: list[Path] = field(default_factory=list)
    watch_token: str = ""
    generation: int = 0
    load_error: str = ""
    source_cache: dict[str, Any] | None = None
    discovery: _Discovery | None = None
    waypoints: dict[str, dict[str, list[list[int]]]] = field(default_factory=dict)
    labels: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    # Per-view UI state from the sidecar's `expanded`/`collapsed` sections:
    # element ids expanded in place and group node ids collapsed, as
    # ``{view_key: [id, ...]}``. Applied when a graph request names neither.
    expanded: dict[str, list[str]] = field(default_factory=dict)
    collapsed: dict[str, list[str]] = field(default_factory=dict)
    # Dragged diagram-chrome positions (title, legend) from the sidecar's
    # `chrome` section, as ``{view_key: {"title"|"legend": [x, y]}}``.
    # Absent chrome keeps its computed placement.
    chrome: dict[str, dict[str, list[int]]] = field(default_factory=dict)


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
    # Dragged label offsets, keyed by edge id. An edge present with a zero
    # offset has been dragged back to its default place.
    labels: dict[str, tuple[int, int]] = {}
    # Dragged diagram-chrome positions ("title", "legend"), absolute flow
    # coordinates. Only chrome the user actually moved is sent; anything
    # absent returns to its computed placement.
    chrome: dict[str, tuple[int, int]] = {}


class CheckRequest(BaseModel):
    """Body for ``POST /api/check``."""

    # Root-relative path the buffer belongs to.
    path: str
    # The buffer's current text, saved or not.
    content: str
    # Which file to parse as the workspace root. Normally inferred: a
    # buffer that is part of the loaded workspace is checked in its
    # context, anything else on its own.
    root: str | None = None


class SaveSourceRequest(BaseModel):
    """Body for ``PUT /api/source``."""

    path: str
    content: str
    # The file as the client last saw it. ``None`` asserts the file does
    # not exist yet, which is how a new fragment is created — and what
    # makes an accidental create-over-existing a 409 rather than a clobber.
    fingerprint: str | None = None
    # Save anyway, discarding what is on disk. Set by the client only after
    # a person has seen the conflict and chosen.
    force: bool = False


class ExpansionRequest(BaseModel):
    """Body for ``POST /api/views/{key}/expansion``."""

    # Element ids expanded in place, and group node ids collapsed. Both are
    # complete lists for the view; empty means none.
    expanded: list[str] = []
    collapsed: list[str] = []


def _version() -> str:
    """The installed distribution version, or ``"unknown"`` from a checkout."""
    try:
        return importlib.metadata.version("c4studio")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source tree
        return "unknown"


def _get_state(request: Request) -> AppState:
    """Return the :class:`AppState` attached to the running app."""
    state: AppState = request.app.state.app_state
    return state


def _require_workspace(state: AppState) -> Workspace:
    """Return the loaded workspace or raise 409 if none is loaded."""
    if state.workspace is None:
        raise HTTPException(status_code=409, detail="No workspace loaded")
    return state.workspace


def _require_writable(state: AppState = Depends(_get_state)) -> AppState:
    """Return the state, or raise 403 when serving in Viewer mode.

    A dependency rather than a call inside each route body: a route that
    writes cannot forget to depend on it the way it could forget a call,
    and the requirement shows up in the generated OpenAPI.
    """
    if state.config.read_only:
        raise HTTPException(
            status_code=403,
            detail="Server is running in viewer (read-only) mode",
        )
    return state


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


def _signature(path: Path, *, with_size: bool) -> str:
    """Stat-based change token for one directory or file.

    A directory's mtime moves when an entry is added, removed or renamed in
    it, which is exactly what would change the walk's result. A file's mtime
    and size stand in for "might this still be a workspace root?".
    """
    try:
        info = path.stat()
    except OSError:
        return "missing"
    return f"{info.st_mtime_ns}:{info.st_size}" if with_size else str(info.st_mtime_ns)


@dataclass
class _Discovery:
    """A completed walk, plus everything its result depended on.

    Attributes:
        files: The walk's answer — POSIX-relative paths of loadable sources.
        directories: Every directory the walk descended into, with the
            signature it had at the time.
        candidates: Every file whose workspace-root test was run, with its
            signature and the answer, so an unchanged file is never opened
            and read again.
    """

    files: list[str]
    directories: dict[Path, str]
    candidates: dict[Path, tuple[str, bool]]

    def is_current(self) -> bool:
        """Whether re-walking would reach the same answer.

        Any addition, removal or rename moves the mtime of the directory
        holding it, and any edit that could change a file's workspace-root
        answer moves that file's mtime or size — so re-stat-ing what the
        walk depended on is enough. Stat is ~40x cheaper than the 8 KB
        reads it avoids.
        """
        return all(
            _signature(directory, with_size=False) == token
            for directory, token in self.directories.items()
        ) and all(
            _signature(file, with_size=True) == token
            for file, (token, _) in self.candidates.items()
        )


def _walk_source_files(root: Path, previous: _Discovery | None) -> _Discovery:
    """Walk ``root`` for loadable sources, reusing ``previous`` where valid.

    Recurses up to ``_MAX_DEPTH`` levels, skipping hidden directories,
    well-known noise directories (``node_modules``, ``.venv`` ...) and DSL
    fragment files that only exist to be ``!include``-ed.

    A file whose signature is unchanged keeps the answer the previous walk
    computed for it, so the 8 KB read happens once per edit rather than once
    per request.
    """
    known = previous.candidates if previous else {}
    files: list[str] = []
    directories: dict[Path, str] = {}
    candidates: dict[Path, tuple[str, bool]] = {}

    def walk(directory: Path, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        directories[directory] = _signature(directory, with_size=False)
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.is_dir():
                if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                    continue
                walk(entry, depth + 1)
            elif entry.suffix.lower() in _SOURCE_SUFFIXES:
                token = _signature(entry, with_size=True)
                cached = known.get(entry)
                is_root = (
                    cached[1]
                    if cached and cached[0] == token
                    else _is_workspace_root(entry)
                )
                candidates[entry] = (token, is_root)
                if is_root:
                    files.append(entry.relative_to(root).as_posix())

    walk(root, 0)
    return _Discovery(files=files, directories=directories, candidates=candidates)


def _iter_source_files(root: Path, state: AppState) -> list[str]:
    """Return POSIX-relative paths of loadable source files under ``root``.

    Cached on ``state`` — not in a module global, so two apps over one root
    cannot see each other's answer.

    The cache is deliberately stat-based, which shares the granularity
    caveat spelled out on :func:`_fingerprint`: a content change that lands
    within the same mtime tick *and* keeps the byte count identical is not
    noticed. The consequence is a file missing from, or lingering in, the
    picker until its next change — never wrong content, and never data loss.
    """
    cached = state.discovery
    if cached is not None and cached.is_current():
        return list(cached.files)

    discovery = _walk_source_files(root, cached)
    state.discovery = discovery
    return list(discovery.files)


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


def _fingerprint(path: Path) -> str | None:
    """Content hash of a file, or ``None`` when it does not exist.

    A hash rather than an mtime, because this answers "is this still the
    text the editor last saw?". Mtimes move when a file is copied, checked
    out or restored without its content changing, and two writes inside one
    filesystem clock tick share one mtime.

    Mtime keeps its own job in :func:`_watch_token`, where the question is
    the cheaper "did anything change?" and hashing every watched file on
    every poll would be far too expensive. Two questions, two mechanisms.
    """
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _read_source(path: Path) -> tuple[str, bool]:
    """Return a file's text and whether it is safe to edit.

    A file that is not valid UTF-8 is still *shown* — with the offending
    bytes replaced, which is what a viewer wants — but is flagged
    uneditable, and :func:`save_source` refuses it. Round-tripping replaced
    bytes through an editor would write U+FFFD over whatever was really
    there, destroying data to no purpose.
    """
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8"), True
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), False


def _atomic_write(path: Path, content: str) -> None:
    """Write text by renaming a sibling temp file over the target.

    A sibling rather than the system temp directory, so the rename stays
    within one filesystem — which is what makes ``os.replace`` atomic. A
    reader either sees the old file or the new one, never a half-written
    file, which matters here because the live-reload watcher may be reading
    at any moment.

    ``newline=""`` writes the buffer's line endings verbatim instead of
    translating them, so saving on Windows does not rewrite every line of a
    file it was only meant to touch one line of.
    """
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8", newline="")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _client_diagnostic(root: Path, diagnostic: Diagnostic) -> dict[str, Any]:
    """``Diagnostic.to_dict()`` with ``path`` made relative to the root.

    The client matches diagnostics against editor tabs, which are keyed by
    root-relative path. ``to_dict`` stays the single source of key names so
    this and ``c4 check --json`` never drift apart.
    """
    data = diagnostic.to_dict()
    if diagnostic.path is not None:
        try:
            data["path"] = diagnostic.path.relative_to(root).as_posix()
        except ValueError:
            data["path"] = diagnostic.path.name
    return data


def _reload_now(state: AppState) -> None:
    """Re-parse the loaded source, keeping the last good workspace on failure.

    The watch token is claimed *before* the attempt, so a source that does
    not parse is not re-parsed on every poll until it changes again.

    On failure the watched file list is still refreshed. Without that, a
    root that fails to parse keeps watching the files it referenced when it
    last parsed — so adding ``!include model/new.dsl`` before ``new.dsl``
    exists means nothing ever starts watching ``new.dsl``, and creating it
    reloads nothing. Rare with an external editor, which touches the root
    on save anyway; the normal order in an in-app editor.

    Called from the ``/api/status`` heartbeat and, once editing lands, from
    the save path — one reload implementation, not two.
    """
    if state.workspace is None or state.current_path is None:
        return
    state.watch_token = _watch_token(state.watch_files)
    try:
        workspace = load_workspace(state.current_path)
    except WorkspaceLoadError as exc:
        state.load_error = str(exc)
        state.watch_files = watched_files(state.current_path)
        state.watch_token = _watch_token(state.watch_files)
        return
    state.workspace = workspace
    state.diagrams.clear()
    _begin_watching(state, state.current_path)
    _apply_saved_layout(state)
    state.generation += 1


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


def _read_layout_labels(source: Path) -> dict[str, dict[str, list[int]]]:
    """Read the sidecar's ``{view_key: {edge_id: [dx, dy]}}`` mapping.

    Its own top-level section for the same reason as ``edges``: sidecars
    written before label dragging existed have no ``labels`` key and load
    unchanged.
    """
    labels = _read_sidecar_data(source).get("labels")
    if not isinstance(labels, dict):
        return {}
    cleaned: dict[str, dict[str, list[int]]] = {}
    for key, by_edge in labels.items():
        if not isinstance(by_edge, dict):
            continue
        offsets = {
            edge_id: [int(offset[0]), int(offset[1])]
            for edge_id, offset in by_edge.items()
            if isinstance(offset, list) and len(offset) == 2
        }
        if offsets:
            cleaned[key] = offsets
    return cleaned


def _read_layout_chrome(source: Path) -> dict[str, dict[str, list[int]]]:
    """Read the sidecar's ``{view_key: {chrome_name: [x, y]}}`` mapping.

    Its own additive top-level ``chrome`` section, like ``edges`` and
    ``labels``: sidecars written before movable chrome existed have no
    such key and load unchanged.
    """
    chrome = _read_sidecar_data(source).get("chrome")
    if not isinstance(chrome, dict):
        return {}
    cleaned: dict[str, dict[str, list[int]]] = {}
    for key, by_name in chrome.items():
        if not isinstance(by_name, dict):
            continue
        points = {
            name: [int(point[0]), int(point[1])]
            for name, point in by_name.items()
            if isinstance(point, list) and len(point) == 2
        }
        if points:
            cleaned[key] = points
    return cleaned


def _read_layout_ids(source: Path, section: str) -> dict[str, list[str]]:
    """Read a sidecar section of ``{view_key: [id, ...]}`` string lists.

    Backs the ``expanded`` and ``collapsed`` sections — per-view UI state,
    each its own additive top-level section so sidecars written before it
    existed load unchanged.
    """
    raw = _read_sidecar_data(source).get(section)
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for key, ids in raw.items():
        if isinstance(ids, list):
            wanted = [i for i in ids if isinstance(i, str) and i]
            if wanted:
                cleaned[key] = wanted
    return cleaned


def _write_layout_sidecar(
    source: Path,
    views: dict[str, dict[str, list[int]]],
    waypoints: dict[str, dict[str, list[list[int]]]],
    labels: dict[str, dict[str, list[int]]] | None = None,
    expanded: dict[str, list[str]] | None = None,
    collapsed: dict[str, list[str]] | None = None,
    chrome: dict[str, dict[str, list[int]]] | None = None,
) -> Path:
    """Write every sidecar section, removing the file when nothing is left."""
    sidecar = _layout_sidecar(source)
    document: dict[str, Any] = {"version": 1, "views": views}
    if waypoints:
        document["edges"] = waypoints
    if labels:
        document["labels"] = labels
    if expanded:
        document["expanded"] = expanded
    if collapsed:
        document["collapsed"] = collapsed
    if chrome:
        document["chrome"] = chrome
    if not any((views, waypoints, labels, expanded, collapsed, chrome)):
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


def _attach_labels(data: dict[str, Any], labels: dict[str, list[int]]) -> None:
    """Add saved label offsets onto matching edges of a graph payload.

    Stale ids are skipped exactly as waypoints are: the entry stays in the
    sidecar until that view's layout is saved again, and never reaches the
    client.
    """
    if not labels:
        return
    for edge in data.get("edges", []):
        offset = labels.get(edge.get("id", ""))
        if offset:
            edge["labelOffset"] = [int(offset[0]), int(offset[1])]


def _apply_saved_layout(state: AppState) -> None:
    """Apply sidecar positions onto the loaded workspace's views."""
    if state.workspace is None or state.current_path is None:
        return
    # Waypoints stay on the state: they are keyed by edge id, and synthesised
    # deployment/dynamic edges have no RelationshipView to hold them.
    state.waypoints = _read_layout_waypoints(state.current_path)
    state.labels = _read_layout_labels(state.current_path)
    state.expanded = _read_layout_ids(state.current_path, "expanded")
    state.collapsed = _read_layout_ids(state.current_path, "collapsed")
    state.chrome = _read_layout_chrome(state.current_path)
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
    root: Path,
    initial: Path | None = None,
    static_dir: Path | None = None,
    *,
    read_only: bool = False,
) -> FastAPI:
    """Build the FastAPI app serving the web backend.

    Args:
        root: Directory that sources are browsed and resolved within.
        initial: Optional source to load eagerly on startup.
        static_dir: Directory holding the built SPA. When ``None`` the
            packaged ``c4studio/webapp/static`` directory is used.
        read_only: Serve in Viewer mode — routes that write DSL refuse
            with 403. Keyword-only, so existing positional callers are
            unaffected.

    Returns:
        A configured :class:`fastapi.FastAPI` instance.
    """
    root = root.resolve()
    app = FastAPI(title="c4studio webapp")
    state = AppState(root=root, config=AppConfig(read_only=read_only))

    if initial is not None:
        initial = initial.resolve()
        state.workspace = load_workspace(initial)
        state.current_path = initial
        _begin_watching(state, initial)
        _apply_saved_layout(state)

    app.state.app_state = state

    @app.get("/api/capabilities")
    def capabilities(state: AppState = Depends(_get_state)) -> dict[str, Any]:
        """Report what this server allows, so the SPA can gate its UI.

        Answers with no workspace loaded — it describes the server, not a
        workspace. ``features`` is an open map for the same reason the
        layout sidecar's sections are additive: a later release can add a
        key without a shape change, and an older client ignores what it
        does not recognise.
        """
        read_only = state.config.read_only
        return {
            "readOnly": read_only,
            "mode": "viewer" if read_only else "studio",
            "version": _version(),
            "features": {
                "editSource": not read_only,
                # Arranging a diagram is part of reading it, so Viewer
                # keeps its layout writes (the sidecar is gitignored
                # per-user UI state regardless).
                "saveLayout": True,
                "checkSource": True,
                "assistant": False,
            },
        }

    @app.post("/api/check")
    def check_source(
        body: CheckRequest, state: AppState = Depends(_get_state)
    ) -> dict[str, Any]:
        """Parse DSL text and report its problems, touching nothing.

        Writes no file and mutates no server state — the loaded workspace,
        the graph caches and the reload generation are all left exactly as
        they were. It answers a question about some text; that is all.

        Not guarded by :func:`_require_writable`: checking is a read, and
        Viewer wants diagnostics for the file it is displaying too.

        A fragment is not a valid workspace on its own, so a buffer that
        belongs to the loaded workspace is parsed *in its root's context*
        with the buffer standing in for the file on disk. Checking a
        fragment in isolation would report a missing ``workspace`` block
        and nothing useful.
        """
        target = _safe_resolve(state.root, body.path)
        if body.root is not None:
            root = _safe_resolve(state.root, body.root)
        elif state.current_path is not None and (
            target == state.current_path or target in state.watch_files
        ):
            root = state.current_path
        else:
            root = target

        overlay = {target: body.content}
        # `overlay.get(root)` covers "the buffer is the root"; the overlay
        # itself covers "the buffer is a fragment of it". One path, both.
        root_text = overlay.get(root)
        if root_text is None:
            try:
                root_text = root.read_text(encoding="utf-8")
            except OSError as exc:
                raise HTTPException(
                    status_code=404, detail=f"Cannot read {body.path}: {exc}"
                ) from exc

        workspace: Workspace | None = None
        try:
            workspace = parse_dsl(
                root_text, base_dir=root.parent, path=root, overlay=overlay
            )
        except ParseError as error:
            # Every problem found, not just the one that stopped parsing.
            diagnostics = list(error.diagnostics)
        else:
            diagnostics = list(workspace.diagnostics)

        return {
            "ok": not any(d.severity is Severity.ERROR for d in diagnostics),
            "diagnostics": [_client_diagnostic(state.root, d) for d in diagnostics],
            "name": workspace.name if workspace is not None else None,
            # Free, since the workspace is already in hand, and it lets the
            # editor show a view appearing or disappearing as you type —
            # including a warning that the view you are looking at is about
            # to go away.
            "views": _views_index(workspace) if workspace is not None else [],
        }

    @app.put("/api/source")
    def save_source(
        body: SaveSourceRequest, state: AppState = Depends(_require_writable)
    ) -> dict[str, Any]:
        """Write DSL text to a file under the root.

        Saving is the render trigger: the write changes the file's mtime,
        which is the signal the live-reload watcher exists to notice. Rather
        than leave that to the next poll, the reload happens here and the
        resulting ``generation`` comes back in the response — so the client
        can tell its own save apart from someone else's edit and leave the
        buffer alone for the former.

        **Invalid DSL still saves.** An editor that refuses to save
        mid-thought is unusable. The text lands on disk, the response
        carries the diagnostics, and the last good workspace keeps being
        served — the same fail-soft contract the watcher already honours.
        """
        target = _safe_resolve(state.root, body.path)

        on_disk = _fingerprint(target)
        if not body.force and on_disk != body.fingerprint:
            # Someone else wrote to this file since the buffer was loaded.
            # Hand back what is actually there, so the client can show both
            # sides without a second round trip.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "conflict",
                    "path": body.path,
                    "fingerprint": on_disk,
                    "content": (
                        _read_source(target)[0] if on_disk is not None else None
                    ),
                },
            )

        if on_disk is not None and not _read_source(target)[1]:
            # Writing it would replace whatever those bytes really were
            # with the U+FFFD the reader substituted.
            raise HTTPException(
                status_code=422,
                detail=f"{body.path} is not valid UTF-8 and cannot be edited here",
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, body.content)

        # Unconditional, and before the reload: `_begin_watching` clears
        # this too, but only on a *successful* load. Leaving it to that
        # would serve pre-save text after a save that does not parse, and
        # the editor's fingerprints would silently diverge from disk.
        state.source_cache = None

        reloaded = state.current_path is not None and (
            target == state.current_path or target in state.watch_files
        )
        if reloaded:
            _reload_now(state)

        workspace = state.workspace
        return {
            "path": body.path,
            # Recomputed from disk rather than hashed from the request, so
            # the client's next save is exact even if the filesystem
            # normalised something.
            "fingerprint": _fingerprint(target),
            "generation": state.generation,
            "reloaded": reloaded,
            "error": state.load_error or None,
            "diagnostics": [
                _client_diagnostic(state.root, d)
                for d in (workspace.diagnostics if workspace else [])
            ],
            "views": _views_index(workspace) if workspace else [],
        }

    @app.get("/api/files")
    def list_files(state: AppState = Depends(_get_state)) -> list[str]:
        """List relative paths of all source files under the root."""
        return _iter_source_files(state.root, state)

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
        if _watch_token(state.watch_files) != state.watch_token:
            _reload_now(state)
        return {
            "path": state.current_path.relative_to(state.root).as_posix(),
            "generation": state.generation,
            "error": state.load_error or None,
            # Constructs the parser understood but skipped. Always been in
            # the model and never surfaced here, so even Viewer showed a
            # clean diagram for a workspace it had quietly dropped parts of.
            "diagnostics": [
                _client_diagnostic(state.root, d)
                for d in (state.workspace.diagnostics if state.workspace else [])
            ],
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
        files: list[dict[str, Any]] = []
        seen: set[Path] = set()
        candidates = [state.current_path] + list(state.watch_files)
        for file in candidates:
            if file in seen:
                continue
            seen.add(file)
            if file.suffix.lower() not in dsl_suffixes and file != state.current_path:
                continue
            try:
                content, editable = _read_source(file)
            except OSError:
                continue
            try:
                rel = file.relative_to(state.root).as_posix()
            except ValueError:
                rel = file.name
            files.append(
                {
                    "path": rel,
                    "content": content,
                    # The editor's baseline for conflict detection, and its
                    # cue not to offer editing a file it cannot faithfully
                    # write back.
                    "fingerprint": _fingerprint(file),
                    "editable": editable,
                }
            )

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
        key: str,
        expand: str | None = None,
        collapse: str | None = None,
        state: AppState = Depends(_get_state),
    ) -> dict[str, Any]:
        """Return React Flow graph data for the view with ``key``.

        ``expand`` is a comma-separated list of element ids to expand in
        place; ``collapse`` one of group node ids to collapse. Omitting a
        parameter (as opposed to sending it empty) applies the state saved
        in the layout sidecar, and the payload echoes what was applied as
        ``expandedIds``/``collapsedIds`` so clients can seed their toggles.
        """
        workspace = _require_workspace(state)
        expand_ids = (
            set(state.expanded.get(key, []))
            if expand is None
            else {part for part in expand.split(",") if part}
        )
        collapse_ids = (
            set(state.collapsed.get(key, []))
            if collapse is None
            else {part for part in collapse.split(",") if part}
        )
        cache_key = (
            f"{key}::{','.join(sorted(expand_ids))}::{','.join(sorted(collapse_ids))}"
        )
        if cache_key in state.diagrams:
            return state.diagrams[cache_key]
        view = _find_view(workspace, key)
        data = graph.react_flow_graph(
            workspace, view, expand_ids or None, collapse_ids or None
        )
        _attach_waypoints(data, state.waypoints.get(key, {}))
        _attach_labels(data, state.labels.get(key, {}))
        # Dragged title/legend positions; absent chrome is placed by the
        # client's own computation.
        if state.chrome.get(key):
            data["chrome"] = {
                name: [int(x), int(y)] for name, (x, y) in state.chrome[key].items()
            }
        data["expandedIds"] = sorted(expand_ids)
        data["collapsedIds"] = sorted(collapse_ids)
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

        # A zero offset means "dragged back to default", so it is dropped
        # rather than stored — the sidecar records deviations only.
        offsets = {
            edge_id: [int(dx), int(dy)]
            for edge_id, (dx, dy) in body.labels.items()
            if dx or dy
        }
        all_labels = _read_layout_labels(state.current_path)
        if offsets:
            all_labels[key] = offsets
        else:
            all_labels.pop(key, None)
        state.labels = all_labels

        # Only chrome the user dragged arrives; an empty map means every
        # piece is back on (or never left) its computed placement.
        chrome_points = {name: [int(x), int(y)] for name, (x, y) in body.chrome.items()}
        if chrome_points:
            state.chrome[key] = chrome_points
        else:
            state.chrome.pop(key, None)

        sidecar = _write_layout_sidecar(
            state.current_path,
            saved,
            all_waypoints,
            all_labels,
            state.expanded,
            state.collapsed,
            state.chrome,
        )
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
        all_labels = _read_layout_labels(state.current_path)
        # Reset means back to auto-layout: straight edges, labels at their
        # default place on the line, chrome at its computed placement, and
        # expansion state cleared.
        sections = (
            saved,
            all_waypoints,
            all_labels,
            state.expanded,
            state.collapsed,
            state.chrome,
        )
        if any(key in section for section in sections):
            for section in sections:
                section.pop(key, None)
            # The waypoint/label dicts were re-read from disk above; the
            # popped copies must replace the in-memory state or the next
            # graph request re-attaches what was just reset.
            state.waypoints = all_waypoints
            state.labels = all_labels
            _write_layout_sidecar(
                state.current_path,
                saved,
                all_waypoints,
                all_labels,
                state.expanded,
                state.collapsed,
                state.chrome,
            )
        return {"reset": key}

    @app.post("/api/views/{key}/expansion")
    def save_expansion(
        key: str, body: ExpansionRequest, state: AppState = Depends(_get_state)
    ) -> dict[str, str]:
        """Persist a view's expanded/collapsed ids to the layout sidecar.

        Sent whenever the user toggles an in-place expansion or collapses a
        group, so the state survives reloads. Empty lists clear the view's
        entry — the sidecar records deviations only.
        """
        _require_workspace(state)
        if state.current_path is None:
            raise HTTPException(status_code=409, detail="No source file loaded")
        if body.expanded:
            state.expanded[key] = list(dict.fromkeys(body.expanded))
        else:
            state.expanded.pop(key, None)
        if body.collapsed:
            state.collapsed[key] = list(dict.fromkeys(body.collapsed))
        else:
            state.collapsed.pop(key, None)
        _invalidate_view_cache(state, key)
        sidecar = _write_layout_sidecar(
            state.current_path,
            _read_layout_sidecar(state.current_path),
            _read_layout_waypoints(state.current_path),
            _read_layout_labels(state.current_path),
            state.expanded,
            state.collapsed,
            state.chrome,
        )
        return {"saved": str(sidecar)}

    _mount_static(app, static_dir)
    return app


def _mount_static(app: FastAPI, static_dir: Path | None) -> None:
    """Mount the built SPA, or expose a hint if it is not built yet.

    Args:
        app: The application to mount static assets on.
        static_dir: Directory holding the built SPA. When ``None`` the
            packaged ``c4studio/webapp/static`` directory is used.
    """
    if static_dir is None:
        static_dir = Path(str(importlib.resources.files("c4studio.webapp") / "static"))
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


def run_server(
    root: Path,
    initial: Path | None,
    host: str,
    port: int,
    *,
    read_only: bool = False,
) -> None:
    """Run the web backend with uvicorn.

    Args:
        root: Directory sources are browsed and resolved within.
        initial: Optional source to load eagerly on startup.
        host: Interface to bind to.
        port: TCP port to listen on.
        read_only: Serve in Viewer mode (see :func:`create_app`).
    """
    import uvicorn

    uvicorn.run(
        create_app(root, initial, read_only=read_only),
        host=host,
        port=port,
        log_level="info",
    )
