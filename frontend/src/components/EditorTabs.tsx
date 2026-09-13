import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { isDirty, type BufferState } from "../sourceBuffers";

interface EditorTabsProps {
  state: BufferState;
  paths: string[];
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
}

/** `hedge_fund/model/oms.dsl` -> `oms.dsl`. */
function basename(path: string): string {
  return path.split("/").pop() ?? path;
}

/**
 * One tab per open buffer, replacing the file list that used to sit in its
 * own 200px column beside the editor.
 *
 * That column was the second of two file navigators on this page, and the
 * duplication was really a naming failure: the sidebar tree is *files on
 * disk*, this is *what I have open*. Tabs say so without a label, because
 * every editor works this way — the idiom carries the meaning.
 *
 * Tabs also cost no horizontal space, which is the other half of the
 * problem they solve.
 */
export function EditorTabs({
  state,
  paths,
  onSelect,
  onClose,
}: EditorTabsProps) {
  if (paths.length === 0) return null;

  // Left/Right moves between tabs, as a tablist should. The arrow keys are
  // free here: CodeMirror has focus while you are typing, not the strip.
  const onKeyDown = (event: ReactKeyboardEvent, index: number) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const step = event.key === "ArrowLeft" ? -1 : 1;
    const next = paths[(index + step + paths.length) % paths.length];
    onSelect(next);
    event.preventDefault();
  };

  return (
    <div className="tabs" role="tablist" aria-label="Open files">
      {paths.map((path, index) => {
        const buffer = state.buffers[path];
        if (!buffer) return null;
        const active = path === state.selectedPath;
        const dirty = isDirty(buffer);
        return (
          <div
            key={path}
            className={"tabs__tab" + (active ? " tabs__tab--active" : "")}
          >
            <button
              role="tab"
              aria-selected={active}
              className="tabs__label"
              // The full path in the title, because the basename alone is
              // ambiguous across fragments — several workspaces have a
              // model/people.dsl.
              title={
                buffer.attached
                  ? path
                  : `${path} — not part of the loaded workspace`
              }
              onClick={() => onSelect(path)}
              onKeyDown={(event) => onKeyDown(event, index)}
              onAuxClick={(event) => {
                // Middle-click closes, as everywhere else.
                if (event.button === 1) {
                  event.preventDefault();
                  onClose(path);
                }
              }}
            >
              {buffer.attached ? null : (
                <span className="tabs__detached" aria-hidden="true">
                  ↗
                </span>
              )}
              <span className="tabs__name">{basename(path)}</span>
            </button>
            <button
              className={"tabs__close" + (dirty ? " tabs__close--dirty" : "")}
              aria-label={dirty ? `Close ${path}, discarding changes` : `Close ${path}`}
              title={dirty ? "Unsaved changes" : "Close"}
              onClick={() => onClose(path)}
            >
              {dirty ? "●" : "✕"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
