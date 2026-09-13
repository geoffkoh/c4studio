// The editor's buffers, as pure state and pure transitions.
//
// Lifted out of SourcePane for two reasons. The first is a bug: the pane
// unmounts on every page switch, and it owned the buffers, so leaving the
// Source page silently destroyed unsaved edits. State this long-lived
// belongs above the component that renders it.
//
// The second is that this is the most carefully-reasoned logic in the
// frontend — conflict detection, fingerprint handling, what happens when a
// file moves under a dirty buffer — and while it lived inside a component
// with network effects and CodeMirror, none of it could be tested without
// a DOM. Pure, it can be, and it is: see the probe in the PR for PP-147.
//
// Every rule below moved verbatim. Nothing here is a redesign.

import type { SingleFile, SourceFile } from "./types";

/** One file's editing state. `text !== disk` is the definition of dirty. */
export interface Buffer {
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

export type BufferMap = Record<string, Buffer>;

/** Buffers and the selection, together — the selection is only meaningful
    against a particular set of buffers, and keeping them in one object is
    what lets a merge drop a file and re-point the selection atomically. */
export interface BufferState {
  buffers: BufferMap;
  selectedPath: string | null;
}

export const EMPTY: BufferState = { buffers: {}, selectedPath: null };

export function isDirty(buffer: Buffer): boolean {
  return buffer.text !== buffer.disk;
}

export function anyDirty(state: BufferState): boolean {
  return Object.values(state.buffers).some(isDirty);
}

/** Paths of buffers that `/api/source` does not serve. */
export function detachedPaths(state: BufferState): string[] {
  return Object.entries(state.buffers)
    .filter(([, buffer]) => !buffer.attached)
    .map(([path]) => path);
}

/** The workspace's files first, then anything opened from the tree. */
export function listedPaths(
  state: BufferState,
  sourceFiles: readonly SourceFile[],
): { path: string; attached: boolean }[] {
  const own = sourceFiles.map((file) => file.path);
  const detached = detachedPaths(state)
    .filter((path) => !own.includes(path))
    .sort();
  return [
    ...own.map((path) => ({ path, attached: true })),
    ...detached.map((path) => ({ path, attached: false })),
  ];
}

/**
 * Fold a fresh `/api/source` payload into the buffers already open.
 *
 * Detached buffers survive — the reload did not mention them because they
 * were never the workspace's, not because they closed. The selection is
 * re-pointed here rather than in a follow-up effect, so there is never a
 * render where `selectedPath` names a buffer that does not exist.
 */
export function mergeFromSource(
  state: BufferState,
  files: readonly SourceFile[],
): BufferState {
  const next: BufferMap = Object.fromEntries(
    Object.entries(state.buffers).filter(([, buffer]) => !buffer.attached),
  );
  for (const file of files) {
    const open = state.buffers[file.path];
    const editable = file.editable ?? true;
    if (open && isDirty(open)) {
      // Unsaved edits outrank the reload: discarding someone's typing to
      // show them a file they did not change is the worse failure. The old
      // fingerprint is kept deliberately, so saving raises the conflict
      // instead of overwriting whatever arrived.
      next[file.path] = {
        ...open,
        editable,
        attached: true,
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
      attached: true,
      // A file the workspace includes is checked in its root's context.
      // One opened on its own keeps whatever it was opened with.
      checkable: true,
    };
  }
  const keep =
    state.selectedPath !== null && next[state.selectedPath] !== undefined;
  return {
    buffers: next,
    selectedPath: keep ? state.selectedPath : (files[0]?.path ?? null),
  };
}

/**
 * Fold refreshed detached files back in.
 *
 * `/api/source` says nothing about detached buffers, so left alone they
 * drift out of date and the next save 409s for no visible reason. A `null`
 * file means it is gone from disk — which the file tree can now do.
 */
export function refreshDetached(
  state: BufferState,
  results: readonly (readonly [string, SingleFile | null])[],
): BufferState {
  const next: BufferMap = { ...state.buffers };
  for (const [path, file] of results) {
    const open = next[path];
    if (!open) continue;
    if (file === null) {
      // Drop a clean buffer — there is nothing left to show. Keep a dirty
      // one: the work is only in this buffer now, and saving it back
      // recreates the file.
      if (isDirty(open)) next[path] = { ...open, staleOnDisk: true };
      else delete next[path];
      continue;
    }
    if (isDirty(open)) {
      // Same rule as the attached merge: typing wins, and the stale
      // fingerprint turns the next save into a conflict.
      if (file.content !== open.disk) next[path] = { ...open, staleOnDisk: true };
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
  const keep =
    state.selectedPath !== null && next[state.selectedPath] !== undefined;
  return {
    buffers: next,
    selectedPath: keep ? state.selectedPath : firstPath(next),
  };
}

/** Add a buffer for a file outside the loaded workspace, and select it. */
export function openDetached(
  state: BufferState,
  path: string,
  file: SingleFile,
  kind: "workspace" | "fragment",
): BufferState {
  if (state.buffers[path]) return { ...state, selectedPath: path };
  return {
    buffers: {
      ...state.buffers,
      [path]: {
        disk: file.content,
        text: file.content,
        fingerprint: file.fingerprint,
        editable: file.editable,
        staleOnDisk: false,
        attached: false,
        checkable: kind === "workspace",
      },
    },
    selectedPath: path,
  };
}

export function select(state: BufferState, path: string): BufferState {
  return state.buffers[path] ? { ...state, selectedPath: path } : state;
}

export function edit(
  state: BufferState,
  path: string,
  text: string,
): BufferState {
  const open = state.buffers[path];
  if (!open || open.text === text) return state;
  return {
    ...state,
    buffers: { ...state.buffers, [path]: { ...open, text } },
  };
}

/**
 * Record a successful write.
 *
 * `disk` becomes what was actually written, not the buffer as it stands
 * now — anything typed while the request was in flight stays dirty.
 */
export function markSaved(
  state: BufferState,
  path: string,
  written: string,
  fingerprint: string | null,
): BufferState {
  const open = state.buffers[path];
  if (!open) return state;
  return {
    ...state,
    buffers: {
      ...state.buffers,
      [path]: { ...open, disk: written, fingerprint, staleOnDisk: false },
    },
  };
}

/** Conflict resolved in favour of disk: the buffer's edits are dropped. */
export function takeDisk(
  state: BufferState,
  path: string,
  content: string,
  fingerprint: string | null,
): BufferState {
  const open = state.buffers[path];
  if (!open) return state;
  return {
    ...state,
    buffers: {
      ...state.buffers,
      [path]: {
        ...open,
        disk: content,
        text: content,
        fingerprint,
        staleOnDisk: false,
      },
    },
  };
}

function firstPath(buffers: BufferMap): string | null {
  const paths = Object.keys(buffers);
  return paths.length > 0 ? paths[0] : null;
}
