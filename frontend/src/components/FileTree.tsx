import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { buildRows, ancestorsOf, initialExpansion } from "../fileTree";
import type { SourceEntry } from "../types";
import { ContextMenu, type MenuAction } from "./ContextMenu";
import { FileOpsDialog, type FileOpRequest } from "./FileOpsDialog";

/** The four things the tree can do to the filesystem.

    Injected as one object so the capability gate is structural: Viewer
    passes `null` and there is no menu at all, rather than a menu whose
    items are disabled and whose requests the server would 403 anyway. */
export interface FileOperations {
  createFile: (path: string) => Promise<unknown>;
  createFolder: (path: string) => Promise<unknown>;
  rename: (path: string, to: string) => Promise<unknown>;
  deleteFile: (path: string) => Promise<unknown>;
  deleteFolder: (path: string) => Promise<unknown>;
}

/** Uniform row height, in px. Must match `.tree__row` in index.css.

    Uniformity is what makes windowing tractable without a dependency:
    row N is always at `N * ROW_HEIGHT`, so the visible slice is arithmetic
    rather than measurement. */
const ROW_HEIGHT = 24;

/** Rows rendered beyond each edge, so a fast scroll does not show gaps. */
const OVERSCAN = 6;

/** Tallest the tree grows before it scrolls within the sidebar. */
const MAX_VIEWPORT = 320;

interface FileTreeProps {
  entries: SourceEntry[];
  currentPath: string | null;
  loadingPath: string | null;
  /** A loadable workspace was picked. */
  onSelect: (path: string) => void;
  /** Any file was picked, for opening in the editor. Fired for workspaces
      too, so clicking one both loads it and shows its source. */
  onOpen: (path: string, kind: "workspace" | "fragment") => void;
  /** Null in Viewer mode: the tree then offers no file operations. */
  fileOps: FileOperations | null;
  /** Called after an operation changes the tree on disk. */
  onChanged: () => void;
}

/**
 * The source browser: a searchable, windowed tree over `GET /api/files`.
 *
 * Replaces a flat list that rendered every path at full depth, unfiltered
 * and unvirtualised — fine for the four sample files it was written
 * against, and the first thing to break as workspaces grow in both
 * directions.
 *
 * Fragments are shown and can be opened in the editor, but never loaded:
 * `POST /api/load` would fail on a file with no `workspace` block.
 */
export function FileTree({
  entries,
  currentPath,
  loadingPath,
  onSelect,
  onOpen,
  fileOps,
  onChanged,
}: FileTreeProps) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(() => initialExpansion(currentPath));
  const [scrollTop, setScrollTop] = useState(0);
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    request: Omit<FileOpRequest, "kind">;
  } | null>(null);
  const [dialog, setDialog] = useState<FileOpRequest | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Loading a workspace reveals where it lives, rather than leaving the
  // user to find a selection inside a folder that is still shut.
  useEffect(() => {
    if (!currentPath) return;
    setExpanded((previous) => {
      const ancestors = ancestorsOf(currentPath);
      if (ancestors.every((path) => previous.has(path))) return previous;
      const next = new Set(previous);
      for (const path of ancestors) next.add(path);
      return next;
    });
  }, [currentPath]);

  const rows = useMemo(
    () => buildRows(entries, { query, expanded }),
    [entries, query, expanded],
  );

  // A shorter result must not leave the viewport scrolled past the end.
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [query]);

  const viewport = Math.min(MAX_VIEWPORT, Math.max(rows.length, 1) * ROW_HEIGHT);
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const end = Math.min(
    rows.length,
    Math.ceil((scrollTop + viewport) / ROW_HEIGHT) + OVERSCAN,
  );
  const visible = rows.slice(start, end);

  /** Where a new entry goes: inside a folder, or beside a file. */
  const openMenu = (
    event: React.MouseEvent,
    path: string,
    isFolder: boolean,
  ) => {
    if (!fileOps) return;
    event.preventDefault();
    const parent = isFolder
      ? path
      : path.split("/").slice(0, -1).join("/");
    setMenu({
      x: event.clientX,
      y: event.clientY,
      request: { target: path, parent, isFolder },
    });
  };

  const runOperation = useCallback(
    async (value: string) => {
      if (!fileOps || !dialog) return;
      const joined = dialog.parent ? `${dialog.parent}/${value}` : value;
      switch (dialog.kind) {
        case "new-file":
          await fileOps.createFile(joined);
          break;
        case "new-folder":
          await fileOps.createFolder(joined);
          break;
        case "rename": {
          const folder = dialog.target.split("/").slice(0, -1).join("/");
          await fileOps.rename(dialog.target, folder ? `${folder}/${value}` : value);
          break;
        }
        case "delete":
          await (dialog.isFolder
            ? fileOps.deleteFolder(dialog.target)
            : fileOps.deleteFile(dialog.target));
          break;
      }
      onChanged();
    },
    [dialog, fileOps, onChanged],
  );

  const menuActions = (request: Omit<FileOpRequest, "kind">): MenuAction[] => [
    {
      label: "New file…",
      onSelect: () => setDialog({ ...request, kind: "new-file" }),
    },
    {
      label: "New folder…",
      onSelect: () => setDialog({ ...request, kind: "new-folder" }),
    },
    {
      label: "Rename…",
      onSelect: () => setDialog({ ...request, kind: "rename" }),
      disabled: request.isFolder,
    },
    {
      label: request.isFolder ? "Delete folder" : "Delete file",
      onSelect: () => setDialog({ ...request, kind: "delete" }),
      destructive: true,
    },
  ];

  const toggle = (path: string) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (!next.delete(path)) next.add(path);
      return next;
    });

  return (
    <section className="section">
      <h2 className="section__title">Files</h2>
      <input
        className="tree__search"
        type="search"
        value={query}
        placeholder="Search files…"
        aria-label="Search files"
        onChange={(event) => setQuery(event.target.value)}
      />
      {entries.length === 0 ? (
        <p className="muted">No source files found.</p>
      ) : rows.length === 0 ? (
        <p className="muted">Nothing matches “{query.trim()}”.</p>
      ) : (
        <div
          className="tree__scroll"
          ref={scrollRef}
          style={{ height: viewport }}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        >
          <div
            className="tree__spacer"
            style={{ height: rows.length * ROW_HEIGHT }}
          >
            {visible.map((row, index) => {
              const top = (start + index) * ROW_HEIGHT;
              const style = {
                top,
                paddingLeft: 6 + row.depth * 12,
              };
              if (row.kind === "dir") {
                return (
                  <button
                    key={row.path}
                    type="button"
                    className="tree__row tree__row--dir"
                    style={style}
                    onClick={() => toggle(row.path)}
                    onContextMenu={(event) => openMenu(event, row.path, true)}
                    title={row.path}
                  >
                    <span className="tree__twisty">
                      {row.expanded ? "▾" : "▸"}
                    </span>
                    <span className="tree__name">{row.name}</span>
                    <span className="tree__count">{row.count}</span>
                  </button>
                );
              }
              // Bound to a const so the narrowing from the `dir` branch
              // above survives into the click handler: TypeScript resets
              // narrowing on a parameter captured by a closure.
              const kind = row.kind;
              const isFragment = kind === "fragment";
              return (
                <button
                  key={row.path}
                  type="button"
                  className={
                    "tree__row" +
                    (row.path === currentPath ? " tree__row--active" : "") +
                    (isFragment ? " tree__row--fragment" : "")
                  }
                  style={style}
                  disabled={loadingPath !== null}
                  onClick={() => {
                    if (!isFragment) onSelect(row.path);
                    onOpen(row.path, kind);
                  }}
                  onContextMenu={(event) => openMenu(event, row.path, false)}
                  title={
                    isFragment
                      ? `${row.path} — an !include fragment: opens in the editor, but cannot be loaded on its own`
                      : row.path
                  }
                >
                  <span className="tree__name">{row.name}</span>
                  {row.path === loadingPath ? (
                    <span className="badge">loading…</span>
                  ) : isFragment ? (
                    <span className="tree__tag">fragment</span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          title={menu.request.target}
          actions={menuActions(menu.request)}
          onClose={() => setMenu(null)}
        />
      ) : null}
      {dialog ? (
        <FileOpsDialog
          request={dialog}
          onConfirm={runOperation}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </section>
  );
}
