import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, checkSource, saveConflict, saveSource } from "../api";
import type { CheckResult, SaveConflict, SaveSourceResult } from "../types";
import type { DslCompletionModel } from "../dslComplete";
import { isDirty, tabPaths } from "../sourceBuffers";
import type { SourceBuffers } from "../useSourceBuffers";
import { AssistantPanel } from "./AssistantPanel";
import { EditorTabs } from "./EditorTabs";
import { DslEditor, type EditorFlash } from "./DslEditor";

export interface CodeFocus {
  elementId: string;
  /** Changes on every request so re-focusing the same element re-flashes. */
  nonce: number;
}

export type { OpenRequest } from "../useSourceBuffers";

/** How long typing has to pause before the buffer is sent to /api/check. */
const CHECK_DEBOUNCE_MS = 400;

interface SourcePaneProps {
  /** The buffers, owned by App so they survive this pane unmounting. */
  source: SourceBuffers;
  focus: CodeFocus | null;
  /** Viewer mode: the server refuses DSL writes, so nothing offers them. */
  readOnly: boolean;
  /** Identifiers and view keys from the loaded workspace, for completion. */
  completions: DslCompletionModel;
  /** Whether this server has the assistant enabled. Off by default, and
      the only feature that uses the network. */
  assistantEnabled: boolean;
  /** Called after a successful write so the app can adopt the reload
      generation and refresh the diagram. */
  onSaved: (result: SaveSourceResult) => void;
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
  source,
  focus,
  readOnly,
  completions,
  assistantEnabled,
  onSaved,
}: SourcePaneProps) {
  const { data, state, error } = source;
  const { buffers, selectedPath } = state;
  const [flash, setFlash] = useState<EditorFlash | null>(null);
  const [check, setCheck] = useState<{ path: string; result: CheckResult } | null>(
    null,
  );
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<SaveConflict | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const appliedFocus = useRef<number | null>(null);

  // Apply an element focus once the source is available. Tracked by nonce
  // so a live reload does not re-scroll to a definition asked for minutes
  // ago, possibly in a file that is no longer the one being edited.
  useEffect(() => {
    if (!focus || !data || appliedFocus.current === focus.nonce) return;
    const location = data.locations[focus.elementId];
    if (!location) return;
    appliedFocus.current = focus.nonce;
    source.select(location.path);
    setFlash({ line: location.line, nonce: focus.nonce });
  }, [focus, data, source]);

  const buffer = selectedPath ? (buffers[selectedPath] ?? null) : null;
  const text = buffer?.text ?? null;

  const dirty = buffer !== null && isDirty(buffer);

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

  const handleChange = useCallback(
    (value: string) => {
      if (selectedPath) source.edit(selectedPath, value);
    },
    [selectedPath, source],
  );

  const write = useCallback(
    async (path: string, content: string, fingerprint: string | null, force: boolean) => {
      setSaving(true);
      setSaveError(null);
      try {
        const result = await saveSource(path, content, fingerprint, force);
        setConflict(null);
        source.markSaved(path, content, result.fingerprint);
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
    [onSaved, source],
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
    source.takeDisk(conflict.path, conflict.content ?? "", conflict.fingerprint);
    setConflict(null);
    setSaveError(null);
  }, [conflict, source]);

  const handleSelectFile = useCallback(
    (path: string) => {
      source.select(path);
      setFlash(null);
      setConflict(null);
      setSaveError(null);
    },
    [source],
  );

  const tabs = useMemo(() => tabPaths(state), [state]);

  /** Closing a dirty tab throws work away, so it asks first. */
  const handleCloseTab = useCallback(
    (path: string) => {
      const buffer = state.buffers[path];
      if (!buffer) return;
      if (
        isDirty(buffer) &&
        !window.confirm(`Discard unsaved changes to ${path}?`)
      ) {
        return;
      }
      source.closeTab(path, true);
      setConflict(null);
      setSaveError(null);
    },
    [source, state.buffers],
  );

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
    <div className="source">
      <div className="editor">
        <EditorTabs
          state={state}
          paths={tabs}
          onSelect={handleSelectFile}
          onClose={handleCloseTab}
        />
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
          {assistantEnabled && !editorReadOnly ? (
            <button
              className="editor__assistant"
              onClick={() => setAssistantOpen((open) => !open)}
              title="Ask for a change. Sends your workspace to an external API."
            >
              Assistant
            </button>
          ) : null}
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

        {assistantOpen && assistantEnabled && !editorReadOnly ? (
          <AssistantPanel
            path={selectedPath}
            content={buffer.text}
            onApply={handleChange}
            onClose={() => setAssistantOpen(false)}
          />
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
