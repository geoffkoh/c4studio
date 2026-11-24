import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { bundledIconUrl, copyBundledIcon, iconFileUrl, listBundledIcons, listIcons } from "../api";
import {
  SUGGESTED,
  groupVariants,
  queryWords,
  score,
  tokenise,
  variantRank,
  variantSuffixes,
  type Searchable,
} from "../iconSearch";
import type { BundledPack, IconLibrary } from "../types";

/** What the style editor hands the card when its Icon row is opened. */
export interface IconPickRequest {
  /** The selection it is for: a new selection closes the picker. */
  ownerId: string;
  /** "Icon · All “Database” (1)": the scope stays in view while picking. */
  title: string;
  /** The current icon's path as written, to start on. */
  current?: string;
  /** The box's paint, for the preview strip: the icon as it will be drawn. */
  box?: { background?: string; color?: string };
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
interface Choice extends Searchable {
  key: string;
  pack: string;
  src: string;
  used: boolean;
  /** Drawn in `currentColor`: previewed in the text colour. */
  tint: boolean;
  /** A workspace icon's root-relative path. */
  path?: string;
  /** A built-in icon, not yet in the workspace. */
  bundled?: { pack: string; name: string };
  /** Not an icon: the tile that shows `count` variants of `of` (PP-247). */
  more?: { head: string; of: string; count: number };
}

/** Where the browser is looking: the left-hand list. */
type Nav =
  | { kind: "home" }
  | { kind: "workspace" }
  | { kind: "recent" }
  | { kind: "pack"; pack: string }
  | { kind: "category"; pack: string; category: string };

interface Section {
  title: string;
  items: Choice[];
}

type Row =
  | { kind: "header"; title: string; top: number }
  | { kind: "tiles"; top: number; first: number; items: Choice[] };

const TILE_WIDTH = 72;
const GAP = 4;
const TILE_ROW = 84;
const HEADER_ROW = 26;
/** Rows drawn beyond the visible ones, so a fast scroll is not blank. */
const OVERSCAN = 3;
/** The left-hand list needs this much room; narrower, it is a dropdown. */
const NAV_MIN_WIDTH = 480;
const RECENT_KEY = "c4studio.recentIcons";
const RECENT_MAX = 16;

function readRecent(): string[] {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function remember(key: string) {
  try {
    const next = [key, ...readRecent().filter((k) => k !== key)].slice(0, RECENT_MAX);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // Storage is a convenience: a private window simply has no history.
  }
}

const navKey = (nav: Nav) =>
  nav.kind === "pack" ? `pack:${nav.pack}` : nav.kind === "category" ? `cat:${nav.pack}:${nav.category}` : nav.kind;

/**
 * Browse and pick an element's icon (PP-233, PP-239, PP-244): the
 * workspace's `icons/` and the packs c4studio ships.
 *
 * It takes the details card over and widens it, rather than opening a
 * pane of its own: the canvas stays where it is, so the live preview on
 * the selected box still shows, and nothing else on screen moves. With
 * room, a list of sections and categories sits on the left; the grid is
 * windowed by hand, so a 5,000-icon pack scrolls whole. Focusing a tile
 * previews it on the canvas and in the strip below; Enter, a double click
 * or Use writes it; Escape goes back to the rows with the canvas as it was.
 */
export function IconPicker({
  request,
  onClose,
}: {
  request: IconPickRequest;
  onClose: () => void;
}) {
  const [library, setLibrary] = useState<IconLibrary | null>(null);
  const [shipped, setShipped] = useState<BundledPack[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [nav, setNav] = useState<Nav>({ kind: "home" });
  const [focused, setFocused] = useState<Choice | null>(null);
  const [active, setActive] = useState(0);
  const [typed, setTyped] = useState("");
  const [copying, setCopying] = useState(false);
  const [recent] = useState(readRecent);
  // Search results whose variants are shown, by the base icon's key.
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [width, setWidth] = useState(0);
  const [view, setView] = useState({ top: 0, height: 400, width: 300 });
  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef(false);

  useEffect(() => {
    let live = true;
    listIcons()
      .then((result) => live && setLibrary(result))
      .catch((err: unknown) => live && setFailed(err instanceof Error ? err.message : "Could not list icons"));
    // Without them the workspace's own icons are still worth showing.
    listBundledIcons()
      .then((result) => live && setShipped(result))
      .catch(() => live && setShipped([]));
    search.current?.focus();
    return () => {
      live = false;
    };
  }, []);

  // The panel's own width decides the layout, not the window's: the card
  // is a sheet on a narrow canvas and a corner panel on a wide one.
  useLayoutEffect(() => {
    const panel = root.current;
    const grid = scroller.current;
    if (!panel || !grid) return;
    const measure = () => {
      setWidth(panel.clientWidth);
      setView((v) => ({ ...v, height: grid.clientHeight, width: grid.clientWidth }));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(panel);
    observer.observe(grid);
    return () => observer.disconnect();
  }, []);

  const own = useMemo<Choice[]>(
    () =>
      (library?.icons ?? []).map((icon) => ({
        key: icon.path,
        name: icon.name,
        tokens: tokenise(`${icon.name} ${icon.path.slice((library?.folder.length ?? 0) + 1)}`),
        tags: [],
        category: icon.pack,
        own: true,
        pack: icon.pack,
        src: iconFileUrl(icon.path),
        used: icon.used,
        // The server's verdict, not the folder's name (PP-246).
        tint: icon.tint,
        path: icon.path,
      })),
    [library],
  );

  // A built-in icon already copied in is listed once, as the copy.
  const copiedAt = (pack: string, name: string) => `${library?.folder ?? "icons"}/${pack}/${name}.svg`;
  const ownByPath = useMemo(() => new Map(own.map((c) => [c.key, c])), [own]);
  const builtIn = useMemo<Choice[]>(
    () =>
      (shipped ?? []).flatMap((p) =>
        p.icons
          .filter((icon) => !ownByPath.has(copiedAt(p.name, icon.name)))
          .map((icon) => ({
            key: `${p.name}:${icon.name}`,
            name: icon.name,
            tokens: tokenise(icon.name),
            tags: tokenise(icon.tags),
            category: icon.category,
            own: false,
            pack: p.name,
            src: bundledIconUrl(p.name, icon.name),
            used: false,
            tint: true,
            bundled: { pack: p.name, name: icon.name },
          })),
      ),
    [shipped, ownByPath],
  );
  const all = useMemo(() => [...own, ...builtIn], [own, builtIn]);
  // Names two tiles share ("Queue" in basic/ and outline/): those tiles say
  // which pack they are from, or they cannot be told apart (PP-248).
  const shared = useMemo(() => {
    const seen = new Set<string>();
    const twice = new Set<string>();
    for (const c of all) {
      const name = c.name.toLowerCase();
      if (seen.has(name)) twice.add(name);
      seen.add(name);
    }
    return twice;
  }, [all]);
  const byKey = useMemo(() => new Map(all.map((c) => [c.key, c])), [all]);
  // A built-in key, or the copy it became.
  const lookup = (key: string): Choice | undefined => {
    const hit = byKey.get(key);
    if (hit) return hit;
    const [pack, name] = key.split(":");
    return name ? ownByPath.get(copiedAt(pack, name)) : undefined;
  };

  const shippedNames = useMemo(() => new Set((shipped ?? []).map((p) => p.name)), [shipped]);
  const inNav = (choice: Choice, where: Nav): boolean => {
    switch (where.kind) {
      case "home":
        return true;
      case "workspace":
        return choice.own;
      case "recent":
        return recent.some((key) => lookup(key)?.key === choice.key);
      case "pack":
        return choice.pack === where.pack;
      case "category":
        return !choice.own && choice.pack === where.pack && choice.category === where.category;
    }
  };

  const words = useMemo(() => queryWords(query), [query]);
  const phrase = query.trim().toLowerCase();
  const ranked = useMemo(() => {
    if (words.length === 0) return null;
    const scored: { item: Choice; score: number }[] = [];
    for (const item of all) {
      const s = score(item, words, phrase);
      if (s !== null) scored.push({ item, score: s });
    }
    scored.sort(
      (a, b) =>
        a.score - b.score ||
        variantRank(a.item) - variantRank(b.item) ||
        a.item.name.length - b.item.name.length ||
        a.item.name.localeCompare(b.item.name),
    );
    return scored;
  }, [all, words, phrase]);
  // Every match, for the counts: folding variants changes what is drawn,
  // not how many icons match.
  const matched = useMemo(() => ranked?.map((r) => r.item) ?? null, [ranked]);

  // A built-in pack's names and variant suffixes, for folding its variants.
  const families = useMemo(
    () =>
      new Map(
        (shipped ?? []).map((p) => {
          const names = new Set(p.icons.map((icon) => icon.name));
          return [p.name, { key: p.name, names, suffixes: variantSuffixes(names) }];
        }),
      ),
    [shipped],
  );

  const sections = useMemo<Section[]>(() => {
    if (ranked !== null) {
      const here = ranked.filter((r) => inNav(r.item, nav));
      const items: Choice[] = [];
      const groups = groupVariants(here, (c) => (c.bundled ? (families.get(c.pack) ?? null) : null));
      for (const { item, variants } of groups) {
        items.push(item);
        if (variants.length === 0) continue;
        if (expanded.has(item.key)) items.push(...variants);
        else items.push(moreTile(item, variants.length));
      }
      return [{ title: `${here.length} ${here.length === 1 ? "match" : "matches"}`, items }];
    }
    switch (nav.kind) {
      case "home": {
        const result: Section[] = [];
        const used = own.filter((c) => c.used);
        if (used.length) result.push({ title: "Used in this workspace", items: used });
        const seen = recent.map(lookup).filter((c): c is Choice => c !== undefined);
        if (seen.length) result.push({ title: "Recently used", items: seen });
        if (shippedNames.has("tabler")) {
          for (const { group, names } of SUGGESTED) {
            const items = names.map((name) => lookup(`tabler:${name}`)).filter((c): c is Choice => c !== undefined);
            if (items.length) result.push({ title: `Suggested · ${group}`, items });
          }
        }
        return result;
      }
      case "workspace": {
        const packs = new Map<string, Choice[]>();
        for (const c of own) packs.set(c.pack, [...(packs.get(c.pack) ?? []), c]);
        return [...packs.entries()].map(([pack, items]) => ({ title: pack || "icons/", items }));
      }
      case "recent":
        return [{ title: "Recently used", items: recent.map(lookup).filter((c): c is Choice => c !== undefined) }];
      case "pack": {
        const items = all.filter((c) => c.pack === nav.pack);
        if (!shippedNames.has(nav.pack)) return [{ title: nav.pack, items }];
        const byCategory = new Map<string, Choice[]>();
        for (const c of items) {
          const title = c.own ? "In this workspace" : c.category || "Other";
          byCategory.set(title, [...(byCategory.get(title) ?? []), c]);
        }
        return [...byCategory.entries()]
          .sort(([a], [b]) => (a === "In this workspace" ? -1 : b === "In this workspace" ? 1 : a.localeCompare(b)))
          .map(([title, list]) => ({ title, items: list }));
      }
      case "category":
        return [{ title: `${nav.pack} · ${nav.category}`, items: all.filter((c) => inNav(c, nav)) }];
    }
  }, [ranked, families, expanded, nav, own, all, recent, shippedNames]);

  // The left-hand list, with counts for what the search leaves.
  const navEntries = useMemo(() => {
    const pool = matched ?? all;
    const count = (where: Nav) => pool.filter((c) => inNav(c, where)).length;
    const entries: { nav: Nav; label: string; count?: number; depth: number }[] = [
      { nav: { kind: "home" }, label: matched ? "Everything" : "Suggested", count: matched?.length, depth: 0 },
    ];
    const ownCount = count({ kind: "workspace" });
    if (ownCount) entries.push({ nav: { kind: "workspace" }, label: "In this workspace", count: ownCount, depth: 0 });
    const recentCount = count({ kind: "recent" });
    if (recentCount) entries.push({ nav: { kind: "recent" }, label: "Recently used", count: recentCount, depth: 0 });
    const packNames = [...new Set(all.map((c) => c.pack))].filter(Boolean).sort((a, b) => {
      // The workspace's packs first, then the built-in ones.
      return Number(shippedNames.has(a)) - Number(shippedNames.has(b)) || a.localeCompare(b);
    });
    for (const pack of packNames) {
      const n = count({ kind: "pack", pack });
      if (matched && n === 0) continue;
      entries.push({
        nav: { kind: "pack", pack },
        label: shippedNames.has(pack) ? `${pack} (built in)` : pack,
        count: n,
        depth: 0,
      });
      if (!shippedNames.has(pack)) continue;
      const open = (nav.kind === "pack" || nav.kind === "category") && nav.pack === pack;
      if (!open && !matched) continue;
      const categories = new Map<string, number>();
      for (const c of pool) {
        if (!c.own && c.pack === pack) categories.set(c.category, (categories.get(c.category) ?? 0) + 1);
      }
      for (const [category, n2] of [...categories.entries()].sort(([a], [b]) => a.localeCompare(b))) {
        entries.push({ nav: { kind: "category", pack, category }, label: category || "Other", count: n2, depth: 1 });
      }
    }
    return entries;
  }, [matched, all, nav, recent, shippedNames]);

  // Sections flattened into rows for the windowed grid.
  const columns = Math.max(1, Math.floor((view.width - 8 + GAP) / (TILE_WIDTH + GAP)));
  const { rows, flat, height } = useMemo(() => {
    const result: Row[] = [];
    const items: Choice[] = [];
    let top = 0;
    for (const section of sections) {
      if (section.items.length === 0) continue;
      result.push({ kind: "header", title: section.title, top });
      top += HEADER_ROW;
      for (let i = 0; i < section.items.length; i += columns) {
        const slice = section.items.slice(i, i + columns);
        result.push({ kind: "tiles", top, first: items.length, items: slice });
        items.push(...slice);
        top += TILE_ROW;
      }
    }
    return { rows: result, flat: items, height: top };
  }, [sections, columns]);

  // A new list starts at its top, with nothing focused: Enter and Use must
  // not write an icon the list no longer shows (PP-245).
  useEffect(() => {
    setActive(0);
    setExpanded(new Set());
    if (focused) {
      setFocused(null);
      request.onPreview(null);
    }
    scroller.current?.scrollTo({ top: 0 });
    // Only a new list lets go; focusing a tile must not.
  }, [query, nav]);

  const visible = rows.filter(
    (row) =>
      row.top + TILE_ROW >= view.top - OVERSCAN * TILE_ROW &&
      row.top <= view.top + view.height + OVERSCAN * TILE_ROW,
  );

  // Moving by keyboard scrolls the tile's row in, then focuses it.
  const rowOf = (index: number) =>
    rows.findIndex((row) => row.kind === "tiles" && index >= row.first && index < row.first + row.items.length);
  const moveTo = (index: number) => {
    const target = Math.max(0, Math.min(index, flat.length - 1));
    const row = rows[rowOf(target)];
    const grid = scroller.current;
    if (row && grid) {
      if (row.top < grid.scrollTop) grid.scrollTop = Math.max(0, row.top - HEADER_ROW);
      else if (row.top + TILE_ROW > grid.scrollTop + grid.clientHeight)
        grid.scrollTop = row.top + TILE_ROW - grid.clientHeight;
    }
    pendingFocus.current = true;
    setActive(target);
  };
  useEffect(() => {
    if (!pendingFocus.current) return;
    const tile = scroller.current?.querySelector<HTMLButtonElement>(`[data-index="${active}"]`);
    if (tile) {
      pendingFocus.current = false;
      tile.focus();
    }
  });

  const cancel = () => {
    request.onPreview(null);
    onClose();
  };
  const use = (choice: Choice | string) => {
    if (typeof choice === "string") {
      request.onUse(choice);
      onClose();
      return;
    }
    if (choice.more) {
      // The variants take the tile's place; focus stays at its index,
      // which is now the first of them.
      const head = choice.more.head;
      setExpanded((was) => new Set(was).add(head));
      pendingFocus.current = true;
      return;
    }
    remember(choice.key);
    if (choice.path !== undefined) {
      request.onUse(choice.path);
      onClose();
      return;
    }
    const { pack, name } = choice.bundled!;
    setCopying(true);
    copyBundledIcon(pack, name)
      .then((copy) => {
        request.onUse(copy.path);
        onClose();
      })
      .catch((err: unknown) => {
        setCopying(false);
        setFailed(err instanceof Error ? err.message : `Could not copy ${name}`);
      });
  };
  const focus = (choice: Choice, index: number) => {
    setActive(index);
    if (choice.more) {
      // Nothing to preview on a "+N" tile.
      if (focused) {
        setFocused(null);
        request.onPreview(null);
      }
      return;
    }
    setFocused(choice);
    request.onPreview(choice.src, choice.tint);
  };

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
      moveTo(0);
    } else if (event.key === "Enter" && flat.length > 0 && !copying) {
      event.preventDefault();
      use(focused ?? flat[0]);
    }
  };

  const onTileKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const r = rowOf(index);
    const row = rows[r];
    const column = row && row.kind === "tiles" ? index - row.first : 0;
    // Up and down keep the column across section headers.
    const tileRow = (from: number, step: number) => {
      for (let i = from + step; i >= 0 && i < rows.length; i += step) {
        const next = rows[i];
        if (next.kind === "tiles") return next.first + Math.min(column, next.items.length - 1);
      }
      return null;
    };
    let next: number | null = null;
    if (event.key === "ArrowRight") next = index + 1;
    else if (event.key === "ArrowLeft") next = index - 1;
    else if (event.key === "ArrowDown") next = tileRow(r, 1) ?? index;
    else if (event.key === "ArrowUp") {
      next = tileRow(r, -1);
      if (next === null) {
        event.preventDefault();
        search.current?.focus();
        return;
      }
    } else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = flat.length - 1;
    else if (event.key === "PageDown") next = index + columns * Math.max(1, Math.floor(view.height / TILE_ROW));
    else if (event.key === "PageUp") next = index - columns * Math.max(1, Math.floor(view.height / TILE_ROW));
    if (next !== null) {
      event.preventDefault();
      if (next < 0) search.current?.focus();
      else moveTo(next);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (!copying) use(flat[index]);
    } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
      // Typing goes back to the search, carrying the key with it.
      event.preventDefault();
      setQuery((current) => current + event.key);
      search.current?.focus();
    }
  };

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
        placeholder="Or a path or an https:// URL"
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
      />
      <button type="submit" disabled={!typed.trim()}>
        Use
      </button>
    </form>
  );

  const loading = library === null && failed === null;
  let note: ReactNode = null;
  if (failed && library === null) {
    note = (
      <div className="icon-picker__empty icon-picker__empty--error">
        <p>{failed}</p>
        {typedForm}
      </div>
    );
  } else if (loading || shipped === null) {
    note = <p className="icon-picker__empty">Reading icons…</p>;
  } else if (flat.length === 0 && matched !== null) {
    const near = [...new Set(builtIn.map((c) => c.category))]
      .filter((category) => words.some((alts) => alts.some((w) => category.toLowerCase().includes(w.slice(0, 3)))))
      .slice(0, 3);
    note = (
      <div className="icon-picker__empty">
        <p>No icons match “{query}”{nav.kind === "home" ? "" : " here"}.</p>
        {near.length ? (
          <p>
            Try a category:{" "}
            {near.map((category) => (
              <button
                key={category}
                className="icon-picker__link"
                onClick={() => {
                  setQuery("");
                  setNav({ kind: "category", pack: "tabler", category });
                }}
              >
                {category}
              </button>
            ))}
          </p>
        ) : null}
      </div>
    );
  } else if (all.length === 0) {
    note = (
      <div className="icon-picker__empty">
        <p>
          No icons. Download a pack (AWS Architecture Icons, Font Awesome Free) into{" "}
          <code>{library?.folder ?? "icons"}/</code> beside the workspace and commit it with the workspace.
        </p>
        {typedForm}
      </div>
    );
  }

  const wide = width >= NAV_MIN_WIDTH;
  const current = navKey(nav);
  const navList = wide ? (
    <nav className="icon-picker__nav" aria-label="Sections">
      {navEntries.map((entry) => (
        <button
          key={navKey(entry.nav)}
          className={`icon-picker__nav-item${entry.depth ? " icon-picker__nav-item--sub" : ""}`}
          aria-current={navKey(entry.nav) === current ? "true" : undefined}
          onClick={() => setNav(entry.nav)}
        >
          <span className="icon-picker__nav-label">
            {entry.nav.kind === "pack" && shippedNames.has(entry.nav.pack) ? (
              // The same dot as the pack's tiles: this is its key.
              <span className="icon-picker__builtin-dot" aria-hidden="true" />
            ) : null}
            {entry.label}
          </span>
          {entry.count !== undefined ? <span className="icon-picker__nav-count">{entry.count}</span> : null}
        </button>
      ))}
    </nav>
  ) : null;

  const strip = focused ? <PreviewStrip choice={focused} box={request.box} folder={library?.folder ?? "icons"} /> : null;

  return (
    <div
      className="icon-picker icon-picker--browsing"
      role="dialog"
      aria-label="Choose an icon"
      onKeyDown={onKeyDown}
      ref={root}
    >
      <div className="icon-picker__head">
        <button
          className="icon-picker__back"
          onClick={cancel}
          aria-label="Back to the style"
          title="Back to the style, where the scope is chosen (Esc)"
        >
          ←
        </button>
        <span className="icon-picker__title">{request.title}</span>
      </div>
      <div className="icon-picker__bar">
        <input
          ref={search}
          className="icon-picker__search"
          type="search"
          aria-label="Search icons"
          placeholder="Search: database, user, queue, db…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onSearchKey}
        />
        {!wide ? (
          <select
            className="icon-picker__show"
            aria-label="Show"
            value={current}
            onChange={(event) => {
              const entry = navEntries.find((e) => navKey(e.nav) === event.target.value);
              if (entry) setNav(entry.nav);
            }}
          >
            {navEntries.map((entry) => (
              <option key={navKey(entry.nav)} value={navKey(entry.nav)}>
                {entry.depth ? `  › ${entry.label}` : entry.label}
                {entry.count !== undefined ? ` (${entry.count})` : ""}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <div className="icon-picker__body">
        {navList}
        <div
          className="icon-picker__scroller"
          ref={scroller}
          onScroll={(event) => {
            const top = event.currentTarget.scrollTop;
            setView((v) => (v.top === top ? v : { ...v, top }));
          }}
        >
          {note}
          {nav.kind === "home" && matched === null && own.length === 0 && !note && library !== null ? (
            <p className="icon-picker__hint">
              Built-in icons are copied into <code>{library.folder}/</code> when used. Packs you download
              there appear here too.
            </p>
          ) : null}
          {flat.length > 0 ? (
            <div className="icon-picker__grid" role="listbox" aria-label="Icons" style={{ height }}>
              {visible.map((row) =>
                row.kind === "header" ? (
                  <div key={`h${row.top}`} className="icon-picker__section" style={{ top: row.top }} role="presentation">
                    {row.title}
                  </div>
                ) : (
                  <div key={`r${row.top}`} className="icon-picker__row" style={{ top: row.top }} role="presentation">
                    {row.items.map((choice, i) => {
                      const index = row.first + i;
                      if (choice.more) {
                        const label = `${choice.more.count} more like ${choice.more.of}`;
                        return (
                          <button
                            key={choice.key}
                            data-index={index}
                            role="option"
                            aria-selected={false}
                            aria-label={label}
                            title={`${label}: show them`}
                            className="icon-picker__tile icon-picker__tile--more"
                            tabIndex={index === active ? 0 : -1}
                            onFocus={() => focus(choice, index)}
                            onClick={() => use(choice)}
                            onKeyDown={(event) => onTileKey(event, index)}
                          >
                            <span className="icon-picker__more-count">+{choice.more.count}</span>
                            <span className="icon-picker__label">variants</span>
                          </button>
                        );
                      }
                      return (
                        <button
                          key={choice.key}
                          data-index={index}
                          role="option"
                          aria-selected={focused?.key === choice.key}
                          aria-label={choice.name}
                          title={choice.bundled ? `${choice.pack}/${choice.name} (built in)` : choice.path}
                          className={`icon-picker__tile${choice.bundled ? " icon-picker__tile--builtin" : ""}`}
                          tabIndex={index === active ? 0 : -1}
                          onFocus={() => focus(choice, index)}
                          onDoubleClick={() => !copying && use(choice)}
                          onKeyDown={(event) => onTileKey(event, index)}
                        >
                          <img src={choice.src} alt="" loading="lazy" />
                          <span className="icon-picker__label">{choice.name}</span>
                          {shared.has(choice.name.toLowerCase()) ? (
                            <span className="icon-picker__sublabel">{choice.pack || "icons/"}</span>
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                ),
              )}
            </div>
          ) : null}
          {nav.kind === "home" && matched === null && own.length === 0 && library !== null ? typedForm : null}
        </div>
      </div>
      {library?.truncated ? (
        <p className="icon-picker__more">The folder holds more images than are listed.</p>
      ) : null}
      {failed && library !== null ? (
        <p className="icon-picker__more icon-picker__empty--error" role="status">
          {failed}
        </p>
      ) : null}
      <div className="icon-picker__foot">
        {strip ?? <span className="icon-picker__caption">Arrows to preview · Enter to use · Esc to go back</span>}
        <button
          className="icon-picker__use"
          disabled={focused === null || copying}
          onClick={() => focused && use(focused)}
        >
          {copying ? "Copying…" : focused?.bundled ? "Copy & use" : "Use"}
        </button>
      </div>
    </div>
  );
}

/** The tile after a base icon that stands for its folded variants. */
function moreTile(head: Choice, count: number): Choice {
  return {
    key: `more:${head.key}`,
    name: `+${count}`,
    tokens: [],
    tags: [],
    category: "",
    own: false,
    pack: head.pack,
    src: "",
    used: false,
    tint: false,
    more: { head: head.key, of: head.name, count },
  };
}

/** The focused icon on the box's own paint, at the size a diagram draws it. */
function PreviewStrip({
  choice,
  box,
  folder,
}: {
  choice: Choice;
  box?: { background?: string; color?: string };
  folder: string;
}) {
  const ink = box?.color ?? "#ffffff";
  const mask = `url("${choice.src.replace(/"/g, "%22")}") center / contain no-repeat`;
  const tinted: CSSProperties = { backgroundColor: ink, mask, WebkitMask: mask };
  return (
    <div className="icon-picker__strip" aria-label="Preview">
      <span className="icon-picker__swatch" style={{ background: box?.background ?? "#1168bd" }}>
        {choice.tint ? (
          <span className="icon-picker__swatch-icon" style={tinted} />
        ) : (
          <img className="icon-picker__swatch-icon" src={choice.src} alt="" />
        )}
      </span>
      <span className="icon-picker__caption" title={choice.path}>
        <strong>{choice.name}</strong>
        <br />
        {choice.bundled
          ? `Built in: Use copies it to ${folder}/${choice.pack}/${choice.name}.svg with its LICENSE`
          : (choice.path ?? "").slice(folder.length + 1)}
      </span>
    </div>
  );
}
