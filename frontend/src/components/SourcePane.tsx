import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  checkSource,
  getFile,
  getSource,
  saveConflict,
  saveSource,
} from "../api";
import type {
  CheckResult,
  SaveConflict,
  SaveSourceResult,
  SourceFile,
  SourceResult,
} from "../types";
import type { DslCompletionModel } from "../dslComplete";
import { DslEditor, type EditorFlash } from "./DslEditor";

export interface CodeFocus {
  elementId: string;
  /** Changes on every request so re-focusing the same element re-flashes. */
  nonce: number;
}

/** One file's editing state. `text !== disk` is the definition of dirty. */
interface Buffer {
  /** Text as last seen on disk, or as last written by this editor. */
  disk: string;
  text: string;
  /** Fingerprint matching `disk`, sent back on save so an edit made
      elsewhere in the meantime is a 409 rather than a silent overwrite. */
  fingerprint: string | null;
  /** False for a file that is not valid UTF-8: shown, never written. */
  editable: boolean;
  /** The file changed on disk while this buffer had unsaved edits. */
  staleOnDisk: boolean;
  /** False for a buffer opened from the tree rather than served by
      `/api/source` — a file belonging to some other workspace, or to none.
      It is kept across reloads instead of being dropped by the merge. */
  attached: boolean;
  /** Whether `POST /api/check` can say anything true about this file.

      The server infers a root only for the loaded workspace. A fragment
      belonging to some *other* workspace, checked standalone, would be
      reported as missing a `workspace` block — a confident error about a
      perfectly good file. Saying nothing is better than saying that. */
  checkable: boolean;
}

/** What the tree asks the editor to open. */
export interface OpenRequest {
  path: string;
  /** From `/api/files`: a workspace root can be checked on its own. */
  kind: "workspace" | "fragment";
  /** Changes per click, so re-opening the same file re-selects it. */
  nonce: number;
}

/** How long typing has to pause before the buffer is sent to /api/check. */
const CHECK_DEBOUNCE_MS = 400;

interface SourcePaneProps {
  /** Bumped by the app whenever a live reload refreshed the workspace. */
  reloadTick: number;
  focus: CodeFocus | null;
  /** Viewer mode: the server refuses DSL writes, so nothing offers them. */
  readOnly: boolean;
  /** Identifiers and view keys from the loaded workspace, for completion. */
  completions: DslCompletionModel;
  /** A file the tree asked to open, which may not belong to the loaded
      workspace at all. */
  open: OpenRequest | null;
  /** Called after a successful write so the app can adopt the reload
      generation and refresh the diagram. */
  onSaved: (result: SaveSourceResult) => void;
}

/** Fold a fresh payload into the buffers already open.

    `attached` distinguishes the two sources: files the server listed for
    the loaded workspace, and files opened from the tree. Detached buffers
    survive a merge — the reload did not mention them because they were
    never the workspace's, not because they closed. */
function mergeBuffers(
  previous: Record<string, Buffer>,
  files: SourceFile[],
  attached: boolean,
): Record<string, Buffer> {
  const next: Record<string, Buffer> = attached
    ? Object.fromEntries(
        Object.entries(previous).filter(([, buffer]) => !buffer.attached),
      )
    : { ...previous };
  for (const file of files) {
    const open = previous[file.path];
    const editable = file.editable ?? true;
    if (open && open.text !== open.disk) {
      // Unsaved edits outrank the reload: discarding someone's typing to
      // show them a file they did not change is the worse failure. The old
      // fingerprint is kept deliberately, so saving raises the conflict
      // instead of overwriting whatever arrived.
      next[file.path] = {
        ...open,
        editable,
        attached: attached || open.attached,
        staleOnDisk: open.staleOnDisk || file.content !== open.disk,
      };
      continue;
    }
    next[file.path] = {
      disk: file.content,
      text: file.content,
      fingerprint: file.fingerprint ?? null,
      editable,
      staleOnDisk: false,
      attached,
      // A file the workspace includes is checked in its root's context.
      // One opened on its own keeps whatever it was opened with.
      checkable: attached || (open?.checkable ?? false),
    };
  }
  return next;
}

/**
 * The DSL source page: the workspace's files (root plus `!include`
 * fragments) listed on the left, the selected one open in a CodeMirror
 * editor on the right.
 *
 * Editing is text-first — saving writes the buffer verbatim and the live
 * reload re-renders the diagram from it, so the diagram is a preview of
 * the text and never the other way round. Diagnostics come from
 * `POST /api/check` as you type; they are advisory, and invalid DSL still
 * saves, because an editor that refuses to save mid-thought is unusable.
 *
 * In Viewer mode, and for any file that is not valid UTF-8, the same
 * editor is mounted read-only.
 */
export function SourcePane({
  reloadTick,
  focus,
  readOnly,
  completions,
  open,
  onSaved,
}: SourcePaneProps) {
  const [data, setData] = useState<SourceResult | null>(null);
  const [buffers, setBuffers] = useState<Record<string, Buffer>>({});
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [flash, setFlash] = useState<EditorFlash | null>(null);
  const [check, setCheck] = useState<{ path: string; result: CheckResult } | null>(
    null,
  );
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<SaveConflict | null>(null);
  const appliedFocus = useRef<number | null>(null);
  const appliedOpen = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSource()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
        setBuffers((previous) => mergeBuffers(previous, result.files, true));
        setSelectedPath((previous) =>
          previous &&
          (result.files.some((f) => f.path === previous) ||
            detachedRef.current.has(previous))
            ? previous
            : (result.files[0]?.path ?? null),
        );
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load source");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  // A reload refreshes the workspace's own files through /api/source, which
  // says nothing about detached ones. Left alone they would drift out of
  // date silently, and the next save would 409 for no visible reason.
  useEffect(() => {
    const paths = [...detachedRef.current];
    if (paths.length === 0) return;
    let cancelled = false;
    void Promise.all(
      paths.map((path) =>
        getFile(path)
          .then((file) => [path, file] as const)
          // A 404 here means the file was deleted or renamed underneath
          // the buffer, which the tree can now do.
          .catch(() => [path, null] as const),
      ),
    ).then((results) => {
      if (cancelled) return;
      setBuffers((previous) => {
        const next = { ...previous };
        for (const result of results) {
          const [path, file] = result;
          const open = next[path];
          if (!open) continue;
          if (file === null) {
            // Gone from disk. Drop a clean buffer — there is nothing left
            // to show. Keep a dirty one: the work is only in this buffer
            // now, and saving it back recreates the file.
            if (open.text === open.disk) delete next[path];
            else next[path] = { ...open, staleOnDisk: true };
            continue;
          }
          if (open.text !== open.disk) {
            // Same rule as the attached merge: typing wins, and the stale
            // fingerprint turns the next save into a conflict.
            if (file.content !== open.disk) {
              next[path] = { ...open, staleOnDisk: true };
            }
            continue;
          }
          next[path] = {
            ...open,
            disk: file.content,
            text: file.content,
            fingerprint: file.fingerprint,
            editable: file.editable,
            staleOnDisk: false,
          };
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  // Apply an element focus once the source is available. Tracked by nonce
  // so a live reload does not re-scroll to a definition asked for minutes
  // ago, possibly in a file that is no longer the one being edited.
  useEffect(() => {
    if (!focus || !data || appliedFocus.current === focus.nonce) return;
    const location = data.locations[focus.elementId];
    if (!location) return;
    appliedFocus.current = focus.nonce;
    setSelectedPath(location.path);
    setFlash({ line: location.line, nonce: focus.nonce });
  }, [focus, data]);

  // Read inside the /api/source callback, which must not re-run when a
  // file is opened — a ref rather than a dependency.
  const detachedRef = useRef<Set<string>>(new Set());
  detachedRef.current = new Set(
    Object.entries(buffers)
      .filter(([, value]) => !value.attached)
      .map(([path]) => path),
  );

  // Open a file the tree asked for. One already served by /api/source is
  // just selected; anything else is fetched and kept as a detached buffer.
  useEffect(() => {
    if (!open || appliedOpen.current === open.nonce) return;
    appliedOpen.current = open.nonce;
    setFlash(null);
    setConflict(null);
    setSaveError(null);
    if (buffers[open.path]) {
      setSelectedPath(open.path);
      return;
    }
    let cancelled = false;
    getFile(open.path)
      .then((file) => {
        if (cancelled) return;
        setBuffers((previous) =>
          previous[open.path]
            ? previous
            : {
                ...previous,
                [open.path]: {
                  disk: file.content,
                  text: file.content,
                  fingerprint: file.fingerprint,
                  editable: file.editable,
                  staleOnDisk: false,
                  attached: false,
                  checkable: open.kind === "workspace",
                },
              },
        );
        setSelectedPath(open.path);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to open file");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, buffers]);

  const buffer = selectedPath ? (buffers[selectedPath] ?? null) : null;
  const text = buffer?.text ?? null;

  // The selected buffer can vanish: a detached file deleted from the tree,
  // or a fragment the workspace no longer includes. Fall back rather than
  // rendering "no source loaded" over a workspace that is loaded.
  useEffect(() => {
    if (!data || !selectedPath || buffers[selectedPath]) return;
    setSelectedPath(data.files[0]?.path ?? null);
  }, [buffers, data, selectedPath]);
  const dirty = buffer !== null && buffer.text !== buffer.disk;

  // Diagnostics for the buffer as it stands, not as it was last parsed
  // from disk. Cheap enough to re-run on a pause in typing; if it ever
  // bites on a large workspace, memoise on (root, hash) server-side.
  const checkable = buffer?.checkable ?? false;
  useEffect(() => {
    if (selectedPath === null || text === null || !checkable) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      checkSource(selectedPath, text)
        .then((result) => {
          if (!cancelled) setCheck({ path: selectedPath, result });
        })
        .catch(() => {
          if (!cancelled) setCheck(null);
        });
    }, CHECK_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [selectedPath, text, checkable]);

  // Browsers only honour this when the page has been interacted with, which
  // by definition it has if there is anything unsaved.
  const anyDirty = Object.values(buffers).some((b) => b.text !== b.disk);
  useEffect(() => {
    if (!anyDirty) return;
    const handler = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [anyDirty]);

  const handleChange = useCallback(
    (value: string) => {
      if (!selectedPath) return;
      setBuffers((previous) => {
        const open = previous[selectedPath];
        if (!open || open.text === value) return previous;
        return { ...previous, [selectedPath]: { ...open, text: value } };
      });
    },
    [selectedPath],
  );

  const write = useCallback(
    async (path: string, content: string, fingerprint: string | null, force: boolean) => {
      setSaving(true);
      setSaveError(null);
      try {
        const result = await saveSource(path, content, fingerprint, force);
        setConflict(null);
        // `disk` is what was actually written, not the buffer as it stands
        // now: anything typed while the request was in flight stays dirty.
        setBuffers((previous) => {
          const open = previous[path];
          if (!open) return previous;
          return {
            ...previous,
            [path]: {
              ...open,
              disk: content,
              fingerprint: result.fingerprint,
              staleOnDisk: false,
            },
          };
        });
        // The write succeeded even when the text does not parse — the file
        // is on disk and the previous workspace keeps being served.
        setSaveError(result.error);
        onSaved(result);
      } catch (err: unknown) {
        const clash = saveConflict(err);
        if (clash) setConflict(clash);
        else setSaveError(err instanceof ApiError ? err.message : "Failed to save");
      } finally {
        setSaving(false);
      }
    },
    [onSaved],
  );

  const canSave = !readOnly && buffer !== null && buffer.editable && dirty && !saving;

  const handleSave = useCallback(() => {
    if (!selectedPath || !buffer || readOnly || !buffer.editable || saving) return;
    void write(selectedPath, buffer.text, buffer.fingerprint, false);
  }, [buffer, readOnly, saving, selectedPath, write]);

  /** Conflict resolved in favour of the buffer: overwrite what is on disk. */
  const handleOverwrite = useCallback(() => {
    if (!selectedPath || !buffer) return;
    void write(selectedPath, buffer.text, buffer.fingerprint, true);
  }, [buffer, selectedPath, write]);

  /** Conflict resolved in favour of disk: the buffer's edits are dropped. */
  const handleTakeDisk = useCallback(() => {
    if (!conflict) return;
    const path = conflict.path;
    const content = conflict.content ?? "";
    setBuffers((previous) => {
      const open = previous[path];
      if (!open) return previous;
      return {
        ...previous,
        [path]: {
          ...open,
          disk: content,
          text: content,
          fingerprint: conflict.fingerprint,
          staleOnDisk: false,
        },
      };
    });
    setConflict(null);
    setSaveError(null);
  }, [conflict]);

  const handleSelectFile = useCallback((path: string) => {
    setSelectedPath(path);
    setFlash(null);
    setConflict(null);
    setSaveError(null);
  }, []);

  // The workspace's files first, then anything opened from the tree.
  const listed = useMemo(() => {
    const own = data?.files.map((file) => file.path) ?? [];
    const detached = Object.entries(buffers)
      .filter(([path, value]) => !value.attached && !own.includes(path))
      .map(([path]) => path)
      .sort();
    return [
      ...own.map((path) => ({ path, attached: true })),
      ...detached.map((path) => ({ path, attached: false })),
    ];
  }, [data, buffers]);

  const current = check?.path === selectedPath ? check.result : null;
  const fileDiagnostics = useMemo(
    () => (current?.diagnostics ?? []).filter((d) => d.path === selectedPath),
    [current, selectedPath],
  );
  const otherDiagnostics = useMemo(
    () => (current?.diagnostics ?? []).filter((d) => d.path !== selectedPath),
    [current, selectedPath],
  );
  const errorCount = (current?.diagnostics ?? []).filter(
    (d) => d.severity === "error",
  ).length;
  const warningCount = (current?.diagnostics ?? []).length - errorCount;

  if (error) {
    return (
      <div className="notice">
        <div className="notice__title">Could not load the source</div>
        <p>{error}</p>
      </div>
    );
  }

  if (!data || !selectedPath || !buffer) {
    return (
      <div className="notice">
        <div className="notice__title">No source loaded</div>
        <p>Load a DSL workspace to browse and edit its files.</p>
      </div>
    );
  }

  const editorReadOnly = readOnly || !buffer.editable;

  return (
    <div className="docs">
      <nav className="docs__toc docs__toc--compact">
        {listed.map((entry) => {
          const open = buffers[entry.path];
          return (
            <button
              key={entry.path}
              className={
                "docs__toc-item" +
                (entry.path === selectedPath ? " docs__toc-item--active" : "")
              }
              onClick={() => handleSelectFile(entry.path)}
              title={
                entry.attached
                  ? entry.path
                  : `${entry.path} — not part of the loaded workspace`
              }
            >
              {entry.attached ? null : (
                <span className="editor__detached" aria-hidden="true">
                  ↗{" "}
                </span>
              )}
              {entry.path}
              {open && open.text !== open.disk ? (
                <span className="editor__dot" title="Unsaved changes">
                  ●
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>
      <div className="editor">
        <div className="editor__toolbar">
          <span className="editor__path">{selectedPath}</span>
          {dirty ? <span className="editor__badge">Unsaved</span> : null}
          {readOnly ? (
            <span className="editor__badge" title="Started with --viewer">
              Viewer — read-only
            </span>
          ) : !buffer.editable ? (
            <span className="editor__badge editor__badge--warn">
              Not valid UTF-8 — read-only
            </span>
          ) : null}
          <span className="editor__spacer" />
          {!editorReadOnly ? (
            <button
              className="editor__save"
              onClick={handleSave}
              disabled={!canSave}
            >
              {saving ? "Saving…" : "Save"}
              <kbd className="editor__kbd">⌘S</kbd>
            </button>
          ) : null}
        </div>

        {conflict ? (
          <div className="editor__banner editor__banner--conflict">
            <div>
              <strong>{conflict.path} changed on disk</strong> since you opened
              it. Saving would lose that change.
            </div>
            <div className="editor__banner-actions">
              <button onClick={handleOverwrite} disabled={saving}>
                Overwrite with mine
              </button>
              <button onClick={handleTakeDisk} disabled={saving}>
                Discard mine, take disk
              </button>
              <button onClick={() => setConflict(null)}>Keep editing</button>
            </div>
          </div>
        ) : null}

        {!conflict && buffer.staleOnDisk ? (
          <div className="editor__banner">
            This file changed on disk while you were editing it. Saving will
            ask what to keep.
          </div>
        ) : null}

        {saveError ? (
          <div className="editor__banner editor__banner--error">{saveError}</div>
        ) : null}

        <DslEditor
          docKey={selectedPath}
          value={buffer.text}
          readOnly={editorReadOnly}
          diagnostics={fileDiagnostics}
          completions={completions}
          flash={flash}
          onChange={handleChange}
          onSave={handleSave}
        />

        <div className="editor__status">
          {!buffer.checkable ? (
            <span
              className="editor__status-item"
              title="Its workspace is not loaded, so there is no context to check it in"
            >
              Not checked — open its workspace for diagnostics
            </span>
          ) : current === null ? (
            <span className="editor__status-item">Checking…</span>
          ) : errorCount === 0 && warningCount === 0 ? (
            <span className="editor__status-item">No problems</span>
          ) : (
            <span className="editor__status-item">
              {errorCount} {errorCount === 1 ? "error" : "errors"},{" "}
              {warningCount} {warningCount === 1 ? "warning" : "warnings"}
            </span>
          )}
          {otherDiagnostics.slice(0, 3).map((diagnostic, index) => (
            <button
              key={index}
              className="editor__status-jump"
              onClick={() =>
                diagnostic.path ? handleSelectFile(diagnostic.path) : undefined
              }
            >
              {diagnostic.path ?? "workspace"}
              {diagnostic.line !== null ? `:${diagnostic.line}` : ""}{" "}
              {diagnostic.message}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
