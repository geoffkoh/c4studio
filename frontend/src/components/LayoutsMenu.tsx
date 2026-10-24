import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, type SavedLayout } from "../api";

/** What the menu needs from the server; GraphPane passes it through. */
export interface LayoutsApi {
  list: (key: string) => Promise<SavedLayout[]>;
  save: (key: string, name: string, overwrite: boolean) => Promise<SavedLayout[]>;
  apply: (key: string, name: string) => Promise<unknown>;
  remove: (key: string, name: string) => Promise<SavedLayout[]>;
}

interface LayoutsMenuProps {
  viewKey: string;
  api: LayoutsApi;
  /** Write the working layout to disk; resolves false if that failed.
      Saving a named layout copies what is on disk, so this runs first. */
  flush: () => Promise<boolean>;
  /** A named layout became the working one: refetch the view. */
  onApplied: () => void;
}

/**
 * The toolbar's Layouts menu (PP-197): keep the current arrangement of a
 * view under a name, and switch between the ones kept.
 *
 * A named layout is a snapshot. The working layout is still the one
 * autosave writes and `c4 render` draws; loading a snapshot copies it into
 * the working layout, and rearranging afterwards changes only the working
 * copy until it is saved under the name again. Loading asks first, because
 * it replaces an arrangement that may exist nowhere else.
 */
export function LayoutsMenu({ viewKey, api, flush, onApplied }: LayoutsMenuProps) {
  const [open, setOpen] = useState(false);
  const [layouts, setLayouts] = useState<SavedLayout[]>([]);
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setMessage(null);
  }, []);

  // A menu left open across a view switch would list another view's
  // layouts under this one's name.
  useEffect(close, [viewKey, close]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api
      .list(viewKey)
      .then((found) => {
        if (!cancelled) setLayouts(found);
      })
      .catch(() => {
        if (!cancelled) setMessage("Could not list saved layouts");
      });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => {
      cancelled = true;
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown, true);
    };
  }, [open, viewKey, api, close]);

  const handleSave = async (event: FormEvent) => {
    event.preventDefault();
    const wanted = name.trim();
    if (!wanted || busy) return;
    const exists = layouts.some((layout) => layout.name === wanted);
    if (exists && !window.confirm(`Replace the saved layout “${wanted}”?`)) {
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      if (!(await flush())) {
        setMessage("Could not save the current layout");
        return;
      }
      setLayouts(await api.save(viewKey, wanted, exists));
      // Only if it still says what was saved: anything typed while the
      // save was in flight is the next name, not this one.
      setName((current) => (current.trim() === wanted ? "" : current));
      setMessage(`Saved “${wanted}”`);
    } catch (error) {
      setMessage(
        error instanceof ApiError && error.status === 409
          ? `“${wanted}” already exists`
          : "Could not save the layout",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async (layout: SavedLayout) => {
    if (
      !window.confirm(
        `Load “${layout.name}”? It replaces this view's current arrangement` +
          " — save that under a name first to keep it.",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await api.apply(viewKey, layout.name);
      onApplied();
      close();
    } catch {
      setMessage(`Could not load “${layout.name}”`);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (layout: SavedLayout) => {
    if (!window.confirm(`Delete the saved layout “${layout.name}”?`)) return;
    setBusy(true);
    try {
      setLayouts(await api.remove(viewKey, layout.name));
    } catch {
      setMessage(`Could not delete “${layout.name}”`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="layouts-menu" ref={ref}>
      <button
        className={
          "edge-style__option" + (open ? " edge-style__option--active" : "")
        }
        title="Save this arrangement under a name, or load one saved earlier"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
      >
        Layouts ▾
      </button>
      {open ? (
        <div className="layouts-menu__popover" role="dialog" aria-label="Layouts">
          <form className="layouts-menu__save" onSubmit={handleSave}>
            <input
              className="layouts-menu__name"
              aria-label="Layout name"
              placeholder="Name this layout"
              maxLength={80}
              value={name}
              autoFocus
              onChange={(event) => setName(event.target.value)}
            />
            <button
              type="submit"
              className="layouts-menu__button"
              disabled={busy || !name.trim()}
            >
              Save
            </button>
          </form>
          {layouts.length === 0 ? (
            <p className="layouts-menu__empty">No saved layouts for this view</p>
          ) : (
            <ul className="layouts-menu__list" aria-label="Saved layouts">
              {layouts.map((layout) => (
                <li key={layout.name} className="layouts-menu__row">
                  <button
                    className="layouts-menu__load"
                    title={
                      layout.savedAt
                        ? `Saved ${new Date(layout.savedAt).toLocaleString()}`
                        : undefined
                    }
                    disabled={busy}
                    onClick={() => void handleApply(layout)}
                  >
                    {layout.name}
                  </button>
                  <button
                    className="layouts-menu__delete"
                    aria-label={`Delete ${layout.name}`}
                    title="Delete"
                    disabled={busy}
                    onClick={() => void handleDelete(layout)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          {message ? (
            <p className="layouts-menu__message" role="status">
              {message}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
