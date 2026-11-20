import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { iconFileUrl, listIcons } from "../api";
import type { IconLibrary, LibraryIcon } from "../types";

/** What the style editor hands the card when its Icon row is opened. */
export interface IconPickRequest {
  /** The selection it is for: a new selection closes the picker. */
  ownerId: string;
  /** "Icon · All “Database” (1)": the scope stays in view while picking. */
  title: string;
  /** The current icon's path as written, to start on. */
  current?: string;
  /** Show `url` on the canvas, or the icon as it was for `null`. */
  onPreview: (url: string | null) => void;
  /** Write it to the DSL: a library path, or a path or URL typed in. */
  onUse: (value: string) => void;
}

/** Tiles drawn at most; past it the search needs to be narrower. */
const SHOWN = 60;

/**
 * Pick an element's icon from `icons/` beside the workspace (PP-233).
 *
 * It takes the card over rather than opening under the Icon row: the card
 * already scrolls at 1024px, so a grid under the row would open out of
 * sight, and a popover over the canvas would hide the box being
 * previewed. Search comes first, since a full pack is hundreds of icons.
 * Focusing a tile previews it on the canvas; Enter, a double click or
 * Use writes it; Escape goes back to the rows with the canvas as it was.
 */
export function IconPicker({
  request,
  onClose,
}: {
  request: IconPickRequest;
  onClose: () => void;
}) {
  const [library, setLibrary] = useState<IconLibrary | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pack, setPack] = useState<string | null>(null);
  const [focused, setFocused] = useState<LibraryIcon | null>(null);
  const [typed, setTyped] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const grid = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    listIcons()
      .then((result) => live && setLibrary(result))
      .catch((err: unknown) => live && setFailed(err instanceof Error ? err.message : "Could not list icons"));
    search.current?.focus();
    return () => {
      live = false;
    };
  }, []);

  const packs = useMemo(() => {
    const counts = new Map<string, number>();
    for (const icon of library?.icons ?? []) counts.set(icon.pack, (counts.get(icon.pack) ?? 0) + 1);
    return [...counts.entries()].filter(([name]) => name !== "");
  }, [library]);
  // One pack is nothing to choose between.
  const choosePack = packs.length > 1;

  const { shown, more } = useMemo(() => {
    const icons = (library?.icons ?? []).filter((icon) => pack === null || icon.pack === pack);
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    let matches: LibraryIcon[];
    if (words.length === 0) {
      // Not every icon on open: what the workspace already uses, or a pack.
      matches = pack === null ? icons.filter((icon) => icon.used) : icons;
    } else {
      const phrase = words.join(" ");
      const rank = (icon: LibraryIcon) => {
        const name = icon.name.toLowerCase();
        return name === phrase ? 0 : name.startsWith(phrase) ? 1 : name.includes(phrase) ? 2 : 3;
      };
      matches = icons
        .filter((icon) => {
          const haystack = `${icon.name} ${icon.path}`.toLowerCase();
          return words.every((word) => haystack.includes(word));
        })
        .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
    }
    return { shown: matches.slice(0, SHOWN), more: Math.max(0, matches.length - SHOWN) };
  }, [library, pack, query]);

  const cancel = () => {
    request.onPreview(null);
    onClose();
  };
  const use = (value: string) => {
    request.onUse(value);
    onClose();
  };
  const focus = (icon: LibraryIcon) => {
    setFocused(icon);
    request.onPreview(iconFileUrl(icon.path));
  };

  const tiles = () => [...(grid.current?.querySelectorAll<HTMLButtonElement>(".icon-picker__tile") ?? [])];

  const onKeyDown = (event: KeyboardEvent) => {
    // The card closes on Escape; here it only steps back to the rows.
    if (event.key === "Escape") {
      event.stopPropagation();
      cancel();
    }
  };

  const onSearchKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      tiles()[0]?.focus();
    } else if (event.key === "Enter" && shown.length > 0) {
      event.preventDefault();
      use((focused ?? shown[0]).path);
    }
  };

  const onTileKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const all = tiles();
    const width = grid.current?.clientWidth ?? 0;
    const columns = Math.max(1, Math.floor((width + 4) / 44));
    const step: Record<string, number> = {
      ArrowRight: 1,
      ArrowLeft: -1,
      ArrowDown: columns,
      ArrowUp: -columns,
    };
    if (event.key in step) {
      event.preventDefault();
      const next = index + step[event.key];
      if (next < 0) search.current?.focus();
      else all[Math.min(next, all.length - 1)]?.focus();
    } else if (event.key === "Home") {
      event.preventDefault();
      all[0]?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      all[all.length - 1]?.focus();
    } else if (event.key === "Enter") {
      event.preventDefault();
      use(shown[index].path);
    } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
      // Typing goes back to the search, carrying the key with it.
      event.preventDefault();
      setQuery((current) => current + event.key);
      search.current?.focus();
    }
  };

  let empty: ReactNode = null;
  if (failed) {
    empty = <p className="icon-picker__empty icon-picker__empty--error">{failed}</p>;
  } else if (library === null) {
    empty = <p className="icon-picker__empty">Reading icons…</p>;
  } else if (!library.exists || library.icons.length === 0) {
    empty = (
      <div className="icon-picker__empty">
        <p>
          {library.exists ? "No images in " : "No "}
          <code>{library.folder}/</code>
          {library.exists ? "." : " folder beside the workspace."} Download a pack (AWS Architecture
          Icons, Font Awesome Free, Simple Icons) into it and it appears here. Commit it with the
          workspace.
        </p>
        <form
          className="icon-picker__typed"
          onSubmit={(event) => {
            event.preventDefault();
            if (typed.trim()) use(typed.trim());
          }}
        >
          <input
            aria-label="Icon path or URL"
            placeholder="A path or an https:// URL"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
          <button type="submit" disabled={!typed.trim()}>
            Use
          </button>
        </form>
      </div>
    );
  } else if (shown.length === 0) {
    empty = (
      <p className="icon-picker__empty">
        {query
          ? `No icons match “${query}”.`
          : `Type to search ${library.icons.length} icons${choosePack ? ", or choose a pack" : ""}.`}
      </p>
    );
  }

  return (
    <div className="icon-picker" role="dialog" aria-label="Choose an icon" onKeyDown={onKeyDown}>
      <div className="icon-picker__head">
        <button className="icon-picker__back" onClick={cancel} title="Back to the style (Esc)">
          ←
        </button>
        <span className="icon-picker__title">{request.title}</span>
      </div>
      <input
        ref={search}
        className="icon-picker__search"
        type="search"
        aria-label="Search icons"
        placeholder="Search icons"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={onSearchKey}
      />
      {choosePack ? (
        <div className="icon-picker__packs" role="group" aria-label="Packs">
          {[["", 0] as [string, number], ...packs].map(([name, count]) => {
            const value = name === "" ? null : name;
            return (
              <button
                key={name}
                className="icon-picker__pack"
                aria-pressed={pack === value}
                onClick={() => setPack(value)}
              >
                {name === "" ? "all" : `${name} ${count}`}
              </button>
            );
          })}
        </div>
      ) : null}
      {!query && pack === null && shown.length > 0 ? (
        <p className="icon-picker__section">In this workspace</p>
      ) : null}
      {empty ?? (
        <div className="icon-picker__grid" ref={grid} role="listbox" aria-label="Icons">
          {shown.map((icon, index) => (
            <button
              key={icon.path}
              role="option"
              aria-selected={focused?.path === icon.path}
              aria-label={icon.name}
              title={icon.path}
              className="icon-picker__tile"
              tabIndex={(focused ? focused.path === icon.path : index === 0) ? 0 : -1}
              onFocus={() => focus(icon)}
              onDoubleClick={() => use(icon.path)}
              onKeyDown={(event) => onTileKey(event, index)}
            >
              <img src={iconFileUrl(icon.path)} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
      {more > 0 ? <p className="icon-picker__more">{more} more: narrow the search</p> : null}
      {library?.truncated ? (
        <p className="icon-picker__more">The folder holds more images than are listed.</p>
      ) : null}
      <div className="icon-picker__foot">
        <span className="icon-picker__caption" title={focused?.path}>
          {focused
            ? `${focused.name} — ${library ? focused.path.slice(library.folder.length + 1) : focused.path}`
            : "Arrows to preview · Enter to use · Esc to go back"}
        </span>
        <button
          className="icon-picker__use"
          disabled={focused === null}
          onClick={() => focused && use(focused.path)}
        >
          Use
        </button>
      </div>
    </div>
  );
}
