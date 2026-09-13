import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getFile, getSource } from "./api";
import * as buffers from "./sourceBuffers";
import type { BufferState } from "./sourceBuffers";
import type { SourceResult } from "./types";

/** What the file tree asks the editor to open. */
export interface OpenRequest {
  path: string;
  /** From `/api/files`: a workspace root can be checked on its own. */
  kind: "workspace" | "fragment";
  /** Changes per click, so re-opening the same file re-selects it. */
  nonce: number;
}

export interface SourceBuffers {
  /** The `/api/source` payload — files and element definition sites. */
  data: SourceResult | null;
  state: BufferState;
  error: string | null;
  select: (path: string) => void;
  edit: (path: string, text: string) => void;
  markSaved: (path: string, written: string, fingerprint: string | null) => void;
  takeDisk: (path: string, content: string, fingerprint: string | null) => void;
  closeTab: (path: string, discard?: boolean) => void;
}

/**
 * Own the editor's buffers, above the component that renders them.
 *
 * Called from App rather than from SourcePane, and that placement is the
 * whole point: `main` unmounts the pane on every page switch, so while the
 * pane owned this state, leaving the Source page destroyed every unsaved
 * edit without a prompt. Here it survives, and the `beforeunload` guard
 * stops being the only thing standing between a user and their work.
 *
 * All the state transitions live in `sourceBuffers.ts` as pure functions.
 * What is here is only the I/O that drives them.
 */
export function useSourceBuffers(
  reloadTick: number,
  open: OpenRequest | null,
): SourceBuffers {
  const [data, setData] = useState<SourceResult | null>(null);
  const [state, setState] = useState<BufferState>(buffers.EMPTY);
  const [error, setError] = useState<string | null>(null);
  const appliedOpen = useRef<number | null>(null);
  // Read inside effects that must not re-run when a buffer changes.
  const stateRef = useRef(state);
  stateRef.current = state;

  // The loaded workspace's files, on mount and after every live reload.
  useEffect(() => {
    let cancelled = false;
    getSource()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
        setState((previous) => buffers.mergeFromSource(previous, result.files));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load source");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  // Detached buffers are not in that payload, so they are refreshed
  // separately — otherwise they drift out of date silently and the next
  // save 409s for no visible reason.
  useEffect(() => {
    const paths = buffers.detachedPaths(stateRef.current);
    if (paths.length === 0) return;
    let cancelled = false;
    void Promise.all(
      paths.map((path) =>
        getFile(path)
          .then((file) => [path, file] as const)
          // A 404 means the file was deleted or renamed underneath the
          // buffer, which the tree can now do.
          .catch(() => [path, null] as const),
      ),
    ).then((results) => {
      if (cancelled) return;
      setState((previous) => buffers.refreshDetached(previous, results));
    });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  // Open what the tree asked for. A file already served by /api/source is
  // just selected; anything else is fetched and kept detached.
  useEffect(() => {
    if (!open || appliedOpen.current === open.nonce) return;
    appliedOpen.current = open.nonce;
    if (stateRef.current.buffers[open.path]) {
      setState((previous) => buffers.select(previous, open.path));
      return;
    }
    let cancelled = false;
    getFile(open.path)
      .then((file) => {
        if (cancelled) return;
        setState((previous) =>
          buffers.openDetached(previous, open.path, file, open.kind),
        );
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to open file");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Browsers only honour this when the page has been interacted with,
  // which by definition it has if there is anything unsaved. It now guards
  // only against closing the tab; an in-app page switch no longer loses
  // anything.
  const dirty = buffers.anyDirty(state);
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  return {
    data,
    state,
    error,
    select: useCallback(
      (path) => setState((previous) => buffers.select(previous, path)),
      [],
    ),
    edit: useCallback(
      (path, text) => setState((previous) => buffers.edit(previous, path, text)),
      [],
    ),
    markSaved: useCallback(
      (path, written, fingerprint) =>
        setState((previous) =>
          buffers.markSaved(previous, path, written, fingerprint),
        ),
      [],
    ),
    takeDisk: useCallback(
      (path, content, fingerprint) =>
        setState((previous) =>
          buffers.takeDisk(previous, path, content, fingerprint),
        ),
      [],
    ),
    closeTab: useCallback(
      (path, discard = false) =>
        setState((previous) => buffers.closeTab(previous, path, discard)),
      [],
    ),
  };
}
