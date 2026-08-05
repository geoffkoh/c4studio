import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  deleteLayout,
  getStatus,
  getViewGraph,
  getWorkspace,
  listFiles,
  listViews,
  loadFile,
  saveLayout,
} from "./api";
import type { ViewInfo, Workspace } from "./types";
import { buildTrail } from "./navigation";
import { isTypingTarget } from "./shortcuts";
import { DocsPane } from "./components/DocsPane";
import { ElementTree } from "./components/ElementTree";
import { ExplorerPane } from "./components/ExplorerPane";
import { FilePicker } from "./components/FilePicker";
import { GraphPane } from "./components/GraphPane";
import { ShortcutHelp } from "./components/ShortcutHelp";
import { SourcePane, type CodeFocus } from "./components/SourcePane";
import { TopBar, type AppPage } from "./components/TopBar";
import { ViewList } from "./components/ViewList";

/** How often to ask the server whether the loaded source changed on disk. */
const RELOAD_POLL_MS = 2000;

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export default function App() {
  const [files, setFiles] = useState<string[]>([]);
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [loadingPath, setLoadingPath] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [views, setViews] = useState<ViewInfo[]>([]);
  const [selectedView, setSelectedView] = useState<ViewInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadError, setReloadError] = useState<string | null>(null);
  const [page, setPage] = useState<AppPage>("diagrams");
  const [codeFocus, setCodeFocus] = useState<CodeFocus | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);
  const generationRef = useRef(0);

  // App-level keyboard shortcuts (diagrams page): j/k cycle views, u goes
  // up a level, ? toggles the help overlay. Graph-scoped keys (f/p/s/h)
  // live in KeyboardShortcuts inside the graph pane.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key === "Escape") {
        setHelpOpen(false);
        return;
      }
      if (page !== "diagrams") return;
      if (event.key === "?") {
        setHelpOpen((open) => !open);
        event.preventDefault();
        return;
      }
      if (event.key === "j" || event.key === "k") {
        const renderable = views.filter((v) => v.supported);
        if (renderable.length === 0) return;
        setSelectedView((current) => {
          const index = current
            ? renderable.findIndex((v) => v.key === current.key)
            : -1;
          const step = event.key === "j" ? 1 : -1;
          const next =
            (index + step + renderable.length) % renderable.length;
          return renderable[next];
        });
        event.preventDefault();
        return;
      }
      if (event.key === "u") {
        setSelectedView((current) => {
          if (!current) return current;
          const trail = buildTrail(current, views, workspace);
          const position = trail.findIndex((v) => v.key === current.key);
          return position > 0 ? trail[position - 1] : current;
        });
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [page, views, workspace]);

  // Load the file list once on mount.
  useEffect(() => {
    listFiles()
      .then(setFiles)
      .catch((err: unknown) =>
        setError(errorMessage(err, "Failed to list files")),
      );
  }, []);

  // If a workspace is already loaded server-side, hydrate the UI on mount.
  useEffect(() => {
    let cancelled = false;
    Promise.all([getWorkspace(), listViews(), getStatus()])
      .then(([ws, vs, status]) => {
        if (cancelled) return;
        setWorkspace(ws);
        setViews(vs);
        setCurrentPath(status.path);
        generationRef.current = status.generation;
      })
      .catch(() => {
        // 409 (nothing loaded yet) is expected; ignore.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Refetch workspace + views after a server-side live reload. */
  const refresh = useCallback(async () => {
    const [ws, vs] = await Promise.all([getWorkspace(), listViews()]);
    setWorkspace(ws);
    setViews(vs);
    setReloadTick((tick) => tick + 1);
    // Keep the current view selected by key; a fresh object identity makes
    // the graph pane refetch. Deselect if the view no longer exists.
    setSelectedView((previous) =>
      previous ? (vs.find((v) => v.key === previous.key) ?? null) : null,
    );
  }, []);

  // Live reload: poll the server; when its generation changes the source
  // was edited on disk and successfully reloaded.
  useEffect(() => {
    if (!currentPath) return;
    const timer = window.setInterval(() => {
      getStatus()
        .then((status) => {
          setReloadError(status.error);
          if (status.generation !== generationRef.current) {
            generationRef.current = status.generation;
            void refresh();
          }
        })
        .catch(() => {
          // Server briefly unreachable (e.g. restart); try again next tick.
        });
    }, RELOAD_POLL_MS);
    return () => window.clearInterval(timer);
  }, [currentPath, refresh]);

  /** Double-click in the Elements tree: open the definition in Source. */
  const handleShowDefinition = useCallback((elementId: string) => {
    setCodeFocus({ elementId, nonce: Date.now() });
    setPage("source");
  }, []);

  /** "Appears in" link in the Explorer: jump to the view's diagram. */
  const handleOpenView = useCallback((view: ViewInfo) => {
    setSelectedView(view);
    setPage("diagrams");
  }, []);

  const handleSelectFile = useCallback(async (path: string) => {
    setLoadingPath(path);
    setError(null);
    setReloadError(null);
    try {
      const result = await loadFile(path);
      setCurrentPath(result.path);
      setViews(result.views);
      setSelectedView(null);
      setPage("diagrams");
      setCodeFocus(null);
      setReloadTick((tick) => tick + 1);
      const [ws, status] = await Promise.all([getWorkspace(), getStatus()]);
      setWorkspace(ws);
      generationRef.current = status.generation;
    } catch (err) {
      setError(errorMessage(err, "Failed to load file"));
    } finally {
      setLoadingPath(null);
    }
  }, []);

  return (
    <div className="app">
      <TopBar
        workspaceName={workspace?.name ?? null}
        filePath={currentPath}
        page={page}
        onPageChange={setPage}
        sectionCount={workspace?.documentation.sections.length ?? 0}
        decisionCount={workspace?.documentation.decisions.length ?? 0}
      />
      <div className="body">
        <aside className="sidebar">
          {error ? <div className="error">{error}</div> : null}
          {reloadError ? (
            <div className="error">
              <strong>Live reload paused:</strong> {reloadError}
            </div>
          ) : null}
          <FilePicker
            files={files}
            currentPath={currentPath}
            loadingPath={loadingPath}
            onSelect={handleSelectFile}
          />
          <ViewList
            views={views}
            selectedKey={selectedView?.key ?? null}
            onSelect={setSelectedView}
          />
          <ElementTree
            workspace={workspace}
            onShowDefinition={handleShowDefinition}
          />
        </aside>
        <main className="main">
          {page === "diagrams" ? (
            <GraphPane
              view={selectedView}
              views={views}
              workspace={workspace}
              onNavigate={setSelectedView}
              loadGraph={getViewGraph}
              saveLayout={saveLayout}
              resetLayout={deleteLayout}
            />
          ) : page === "explorer" ? (
            <ExplorerPane
              views={views}
              workspace={workspace}
              reloadTick={reloadTick}
              onOpenView={handleOpenView}
              onShowDefinition={handleShowDefinition}
            />
          ) : page === "source" ? (
            <SourcePane reloadTick={reloadTick} focus={codeFocus} />
          ) : (
            <DocsPane workspace={workspace} mode={page} />
          )}
        </main>
      </div>
      {helpOpen ? <ShortcutHelp onClose={() => setHelpOpen(false)} /> : null}
    </div>
  );
}
