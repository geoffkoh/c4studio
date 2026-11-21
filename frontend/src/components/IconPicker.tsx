import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { bundledIconUrl, copyBundledIcon, iconFileUrl, listBundledIcons, listIcons } from "../api";
import type { BundledPack, IconLibrary } from "../types";

/** What the style editor hands the card when its Icon row is opened. */
export interface IconPickRequest {
  /** The selection it is for: a new selection closes the picker. */
  ownerId: string;
  /** "Icon · All “Database” (1)": the scope stays in view while picking. */
  title: string;
  /** The current icon's path as written, to start on. */
  current?: string;
  /** Show `url` on the canvas, or the icon as it was for `null`. `tint`
      paints it in the box's text colour, as a one-colour icon is drawn. */
  onPreview: (url: string | null, tint?: boolean) => void;
  /** Write it to the DSL: a library path, or a path or URL typed in. */
  onUse: (value: string) => void;
}

/**
 * One tile: an icon in the workspace's `icons/`, or one c4studio ships,
 * which is copied into the workspace when used (PP-239).
 */
interface Choice {
  key: string;
  name: string;
  pack: string;
  src: string;
  /** Lower-cased: name, path, and a bundled icon's category and tags. */
  haystack: string;
  used: boolean;
  /** Drawn in `currentColor`: previewed in the text colour. */
  tint: boolean;
  /** A workspace icon's root-relative path. */
  path?: string;
  /** A bundled icon, not yet in the workspace. */
  bundled?: { pack: string; name: string; folder: string };
}

/** Tiles drawn at most; past it the search needs to be narrower. */
const SHOWN = 60;

/**
 * Pick an element's icon from `icons/` beside the workspace (PP-233), or
 * from the packs c4studio ships (PP-239).
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
  const [packsShipped, setPacksShipped] = useState<BundledPack[]>([]);
  const [failed, setFailed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pack, setPack] = useState<string | null>(null);
  const [focused, setFocused] = useState<Choice | null>(null);
  const [typed, setTyped] = useState("");
  const [copying, setCopying] = useState(false);
  const search = useRef<HTMLInputElement>(null);
  const grid = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    listIcons()
      .then((result) => live && setLibrary(result))
      .catch((err: unknown) => live && setFailed(err instanceof Error ? err.message : "Could not list icons"));
    // Without them the workspace's own icons are still worth showing.
    listBundledIcons()
      .then((result) => live && setPacksShipped(result))
      .catch(() => undefined);
    search.current?.focus();
    return () => {
      live = false;
    };
  }, []);

  const choices = useMemo(() => {
    if (library === null) return [];
    const shippedNames = new Set(packsShipped.map((p) => p.name));
    const own: Choice[] = library.icons.map((icon) => ({
      key: icon.path,
      name: icon.name,
      pack: icon.pack,
      src: iconFileUrl(icon.path),
      haystack: `${icon.name} ${icon.path}`.toLowerCase(),
      used: icon.used,
      tint: shippedNames.has(icon.pack),
      path: icon.path,
    }));
    const copied = new Set(own.map((c) => c.key));
    const shipped: Choice[] = packsShipped.flatMap((p) =>
      p.icons
        .filter((icon) => !copied.has(`${library.folder}/${p.name}/${icon.name}.svg`))
        .map((icon) => ({
          key: `${p.name}:${icon.name}`,
          name: icon.name,
          pack: p.name,
          src: bundledIconUrl(p.name, icon.name),
          haystack: `${icon.name} ${icon.category} ${icon.tags}`.toLowerCase(),
          used: false,
          tint: true,
          bundled: { pack: p.name, name: icon.name, folder: p.folder },
        })),
    );
    return [...own, ...shipped];
  }, [library, packsShipped]);

  const packs = useMemo(() => {
    const counts = new Map<string, number>();
    for (const choice of choices) counts.set(choice.pack, (counts.get(choice.pack) ?? 0) + 1);
    return [...counts.entries()].filter(([name]) => name !== "");
  }, [choices]);
  // One pack is nothing to choose between.
  const choosePack = packs.length > 1;
  const builtIn = new Set(packsShipped.map((p) => p.name));
  const ownCount = library?.icons.length ?? 0;

  const { shown, more } = useMemo(() => {
    const pool = choices.filter((choice) => pack === null || choice.pack === pack);
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    let matches: Choice[];
    if (words.length === 0) {
      // Not every icon on open: what the workspace already uses, or a pack.
      matches = pack === null ? pool.filter((choice) => choice.used) : pool;
    } else {
      const phrase = words.join(" ");
      const rank = (choice: Choice) => {
        const name = choice.name.toLowerCase();
        return name === phrase ? 0 : name.startsWith(phrase) ? 1 : name.includes(phrase) ? 2 : 3;
      };
      // The workspace's own icons before the shipped ones, rank for rank.
      matches = pool
        .filter((choice) => words.every((word) => choice.haystack.includes(word)))
        .sort(
          (a, b) =>
            rank(a) - rank(b) ||
            Number(Boolean(a.bundled)) - Number(Boolean(b.bundled)) ||
            a.name.localeCompare(b.name),
        );
    }
    return { shown: matches.slice(0, SHOWN), more: Math.max(0, matches.length - SHOWN) };
  }, [choices, pack, query]);

  const cancel = () => {
    request.onPreview(null);
    onClose();
  };
  const use = (choice: Choice | string) => {
    if (typeof choice === "string" || choice.path !== undefined) {
      request.onUse(typeof choice === "string" ? choice : (choice.path as string));
      onClose();
      return;
    }
    const { pack: from, name } = choice.bundled!;
    setCopying(true);
    copyBundledIcon(from, name)
      .then((copy) => {
        request.onUse(copy.path);
        onClose();
      })
      .catch((err: unknown) => {
        setCopying(false);
        setFailed(err instanceof Error ? err.message : `Could not copy ${name}`);
      });
  };
  const focus = (choice: Choice) => {
    setFocused(choice);
    request.onPreview(choice.src, choice.tint);
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
    } else if (event.key === "Enter" && shown.length > 0 && !copying) {
      event.preventDefault();
      use(focused ?? shown[0]);
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
      if (!copying) use(shown[index]);
    } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
      // Typing goes back to the search, carrying the key with it.
      event.preventDefault();
      setQuery((current) => current + event.key);
      search.current?.focus();
    }
  };

  // A path or URL typed in, offered while the workspace has no icons of its own.
  const typedForm = (
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
  );

  let empty: ReactNode = null;
  if (failed && library === null) {
    empty = <p className="icon-picker__empty icon-picker__empty--error">{failed}</p>;
  } else if (library === null) {
    empty = <p className="icon-picker__empty">Reading icons…</p>;
  } else if (choices.length === 0) {
    empty = (
      <div className="icon-picker__empty">
        <p>
          {library.exists ? "No images in " : "No "}
          <code>{library.folder}/</code>
          {library.exists ? "." : " folder beside the workspace."} Download a pack (AWS Architecture
          Icons, Font Awesome Free, Simple Icons) into it and it appears here. Commit it with the
          workspace.
        </p>
        {typedForm}
      </div>
    );
  } else if (shown.length === 0) {
    const shipped = packsShipped.map((p) => `${p.name} ${p.icons.length}`).join(", ");
    empty = (
      <div className="icon-picker__empty">
        <p>
          {query
            ? `No icons match “${query}”.`
            : `Type to search ${choices.length} icons${choosePack ? ", or choose a pack" : ""}.`}
        </p>
        {!query && ownCount === 0 ? (
          <>
            <p>
              Built in: {shipped}, copied into <code>{library.folder}/</code> when used. Packs you
              download into <code>{library.folder}/</code> appear here too.
            </p>
            {typedForm}
          </>
        ) : null}
      </div>
    );
  }

  const focusedCaption = (choice: Choice) => {
    if (choice.bundled) {
      const folder = library ? `${library.folder}/${choice.pack}` : choice.bundled.folder;
      return `${choice.name} — built in, copied to ${folder}/ with its licence`;
    }
    const path = choice.path ?? "";
    return `${choice.name} — ${library ? path.slice(library.folder.length + 1) : path}`;
  };

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
                title={builtIn.has(name) ? "Built into c4studio; copied into the workspace when used" : undefined}
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
          {shown.map((choice, index) => (
            <button
              key={choice.key}
              role="option"
              aria-selected={focused?.key === choice.key}
              aria-label={choice.name}
              title={choice.bundled ? `${choice.pack}/${choice.name} (built in)` : choice.path}
              className="icon-picker__tile"
              tabIndex={(focused ? focused.key === choice.key : index === 0) ? 0 : -1}
              onFocus={() => focus(choice)}
              onDoubleClick={() => !copying && use(choice)}
              onKeyDown={(event) => onTileKey(event, index)}
            >
              <img src={choice.src} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
      {more > 0 ? <p className="icon-picker__more">{more} more: narrow the search</p> : null}
      {library?.truncated ? (
        <p className="icon-picker__more">The folder holds more images than are listed.</p>
      ) : null}
      {failed && library !== null ? (
        <p className="icon-picker__more icon-picker__empty--error" role="status">
          {failed}
        </p>
      ) : null}
      <div className="icon-picker__foot">
        <span className="icon-picker__caption" title={focused?.path}>
          {focused ? focusedCaption(focused) : "Arrows to preview · Enter to use · Esc to go back"}
        </span>
        <button
          className="icon-picker__use"
          disabled={focused === null || copying}
          onClick={() => focused && use(focused)}
        >
          {copying ? "Copying…" : "Use"}
        </button>
      </div>
    </div>
  );
}
