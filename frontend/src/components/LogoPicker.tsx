import { useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";

import { LOGO_GAP, LOGO_HEIGHT, logoWidth, type WorkspaceLogo } from "@c4studio/diagram-core";

import { copyLogo, iconFileUrl, listLogos, logoAspect } from "../api";
import type { LogoImage, LogoLibrary } from "../types";

/** What the card hands the picker when the workspace's logo is opened. */
export interface LogoPickRequest {
  /** The selection it was opened over: a new selection closes it. */
  ownerId: string | null;
  /** The diagram's title, drawn beside the logo in the preview strip. */
  title: string;
  /** The logo drawn now, to start the strip on. */
  current?: WorkspaceLogo;
  /** Show the logo on the title, or the one drawn before for `null`. */
  onPreview: (logo: WorkspaceLogo | null) => void;
  /** Write it to the `Workspace:Icon` rule: a root-relative path. */
  onUse: (path: string) => void;
}

/** Rows drawn at most; past it the search needs to be narrower. */
const SHOWN = 80;

function fileName(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

function sizeText(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`;
}

/** A picked file's bytes as base64, for the copy route. */
function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result);
      resolve(url.slice(url.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error("Could not read the file"));
    reader.readAsDataURL(file);
  });
}

/** The copy the confirmation names, before anything is written. */
interface PendingCopy {
  name: string;
  content: string;
  target: string;
}

/**
 * Pick the workspace's logo (PP-238): the `Workspace:Icon` style's icon,
 * drawn beside every diagram's title.
 *
 * A list rather than the icon picker's grid. A logo is one file somewhere
 * in the repository, and a wordmark squeezed into a 40px tile is
 * unrecognisable, so each row shows its name and folder. Likely files come
 * first (`brand/`, named like a logo); search reaches every other image.
 * Focusing a row previews it, in the strip here and on the canvas; Enter,
 * a double click or Use writes it. A file from elsewhere on the machine is
 * copied into `brand/` first, after a confirmation naming where.
 */
export function LogoPicker({
  request,
  onClose,
  onCancel,
}: {
  request: LogoPickRequest;
  onClose: () => void;
  /** Closed without a logo written: Esc or the back arrow. */
  onCancel?: () => void;
}) {
  const [library, setLibrary] = useState<LogoLibrary | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState<LogoImage | null>(null);
  const [strip, setStrip] = useState<WorkspaceLogo | undefined>(request.current);
  const [pending, setPending] = useState<PendingCopy | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const chooser = useRef<HTMLInputElement>(null);
  // The latest focus wins: an aspect read for an earlier one is dropped.
  const previewing = useRef<string | null>(null);

  // A file chosen from the machine previews from memory until copied.
  // Not revoked on close: the canvas may still draw it until the reload.
  const blob = useRef<string | null>(null);

  useEffect(() => {
    let live = true;
    listLogos()
      .then((result) => live && setLibrary(result))
      .catch((err: unknown) => live && setFailed(err instanceof Error ? err.message : "Could not list images"));
    search.current?.focus();
    return () => {
      live = false;
      // However the picker closes, an aspect still on its way must not
      // paint its image back on the title (PP-252).
      previewing.current = null;
    };
  }, []);

  const usable = (image: LogoImage) => library !== null && image.size <= library.maxBytes;

  const { shown, more } = useMemo(() => {
    const images = library?.images ?? [];
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    let matches: LogoImage[];
    if (words.length === 0) {
      matches = images.filter((image) => image.suggested || image.path === library?.current);
    } else {
      matches = images.filter((image) => words.every((word) => image.path.toLowerCase().includes(word)));
    }
    // The logo set now leads, then what can be used, in the server's order.
    const limit = library?.maxBytes ?? 0;
    const rank = (image: LogoImage) =>
      image.path === library?.current ? 0 : image.size <= limit ? 1 : 2;
    matches = [...matches].sort((a, b) => rank(a) - rank(b));
    return { shown: matches.slice(0, SHOWN), more: Math.max(0, matches.length - SHOWN) };
  }, [library, query]);

  const cancel = () => {
    request.onPreview(null);
    onClose();
    onCancel?.();
  };
  const use = (path: string) => {
    request.onUse(path);
    onClose();
  };
  const preview = (path: string) => {
    previewing.current = path;
    const src = iconFileUrl(path);
    setStrip({ src });
    request.onPreview({ src });
    // The title draws a logo at its proportions, which the browser cannot
    // read from an SVG with only a viewBox; the server can.
    logoAspect(path)
      .then((aspect) => {
        if (previewing.current !== path || aspect === null) return;
        setStrip({ src, aspect });
        request.onPreview({ src, aspect });
      })
      .catch(() => undefined);
  };
  const focus = (image: LogoImage) => {
    setFocused(image);
    if (usable(image)) preview(image.path);
  };

  const rows = () => [...(list.current?.querySelectorAll<HTMLButtonElement>(".logo-picker__row") ?? [])];

  const onKeyDown = (event: KeyboardEvent) => {
    // The card closes on Escape; here it only steps back.
    if (event.key === "Escape") {
      event.stopPropagation();
      if (pending) setPending(null);
      else cancel();
    }
  };

  const onSearchKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      rows()[0]?.focus();
    } else if (event.key === "Enter") {
      const first = focused ?? shown.find(usable);
      if (first && usable(first)) {
        event.preventDefault();
        use(first.path);
      }
    }
  };

  const onRowKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const all = rows();
    const step: Record<string, number> = { ArrowDown: 1, ArrowUp: -1 };
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
      if (usable(shown[index])) use(shown[index].path);
    } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
      // Typing goes back to the search, carrying the key with it.
      event.preventDefault();
      setQuery((current) => current + event.key);
      search.current?.focus();
    }
  };

  const onChosen = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // The same file chosen twice still fires a change.
    event.target.value = "";
    if (!file || !library) return;
    setNotice(null);
    // Refused here rather than after a 256 KB round trip.
    if (file.size > library.maxBytes) {
      setNotice(
        `${file.name} is ${sizeText(file.size)}: a logo is embedded in every export, so at most ${sizeText(library.maxBytes)}.`,
      );
      return;
    }
    setBusy(true);
    try {
      const content = await readBase64(file);
      const plan = await copyLogo(file.name, content, true);
      if (plan.existing) {
        // Already in the workspace, by content: no copy, no question.
        setNotice(`Already in the workspace as ${plan.path}.`);
        preview(plan.path);
        setFocused(library.images.find((image) => image.path === plan.path) ?? null);
        return;
      }
      setPending({ name: file.name, content, target: plan.path });
      if (blob.current) URL.revokeObjectURL(blob.current);
      const local = URL.createObjectURL(file);
      blob.current = local;
      setStrip({ src: local });
      request.onPreview({ src: local });
    } catch (err: unknown) {
      setNotice(err instanceof Error ? err.message : "Could not read the file");
    } finally {
      setBusy(false);
    }
  };

  const confirmCopy = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const copied = await copyLogo(pending.name, pending.content, false);
      use(copied.path);
    } catch (err: unknown) {
      setNotice(err instanceof Error ? err.message : "Could not copy the file");
      setBusy(false);
    }
  };

  let body;
  if (failed) {
    body = <p className="icon-picker__empty icon-picker__empty--error">{failed}</p>;
  } else if (library === null) {
    body = <p className="icon-picker__empty">Reading images…</p>;
  } else if (shown.length === 0) {
    body = (
      <p className="icon-picker__empty">
        {query
          ? `No images match “${query}”.`
          : library.images.length === 0
            ? "No images in the workspace's folder. Choose a file to copy one in."
            : `Nothing named like a logo. Type to search ${library.images.length} images.`}
      </p>
    );
  } else {
    body = (
      <div className="logo-picker__list" ref={list} role="listbox" aria-label="Images">
        {shown.map((image, index) => {
          const ok = usable(image);
          const folder = image.path.slice(0, image.path.lastIndexOf("/") + 1);
          return (
            <button
              key={image.path}
              role="option"
              aria-selected={focused?.path === image.path}
              aria-disabled={!ok}
              aria-label={fileName(image.path)}
              title={ok ? image.path : `${image.path}: too large to embed`}
              className="logo-picker__row"
              tabIndex={(focused ? focused.path === image.path : index === 0) ? 0 : -1}
              onFocus={() => focus(image)}
              onDoubleClick={() => ok && use(image.path)}
              onKeyDown={(event) => onRowKey(event, index)}
            >
              <span className="logo-picker__thumb">
                <img src={iconFileUrl(image.path)} alt="" loading="lazy" />
              </span>
              <span className="logo-picker__name">
                {fileName(image.path)}
                {image.path === library.current ? <span className="logo-picker__tag"> · current</span> : null}
              </span>
              <span className="logo-picker__where">
                {ok ? folder || "./" : `${sizeText(image.size)}, too large`}
              </span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="icon-picker logo-picker" role="dialog" aria-label="Choose the workspace logo" onKeyDown={onKeyDown}>
      <div className="icon-picker__head">
        <button className="icon-picker__back" onClick={cancel} title="Back (Esc)">
          ←
        </button>
        <span className="icon-picker__title">Workspace logo</span>
      </div>
      <div className="logo-picker__strip" aria-label="Preview">
        {strip ? (
          <img
            src={strip.src}
            alt=""
            style={{ width: logoWidth(strip), height: LOGO_HEIGHT, marginRight: LOGO_GAP }}
          />
        ) : (
          <span className="logo-picker__none" style={{ height: LOGO_HEIGHT, marginRight: LOGO_GAP }}>
            no logo
          </span>
        )}
        <span className="logo-picker__title">{request.title}</span>
      </div>
      <input
        ref={search}
        className="icon-picker__search"
        type="search"
        aria-label="Search images"
        placeholder="Search the workspace's images"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={onSearchKey}
      />
      {!query && library && shown.length > 0 ? <p className="icon-picker__section">Suggested</p> : null}
      {body}
      {more > 0 ? <p className="icon-picker__more">{more} more: narrow the search</p> : null}
      {library?.truncated ? (
        <p className="icon-picker__more">The folder holds more files than are listed.</p>
      ) : null}
      {notice ? (
        <p className="logo-picker__notice" role="status">
          {notice}
        </p>
      ) : null}
      <input
        ref={chooser}
        type="file"
        accept="image/svg+xml,image/png,image/jpeg,image/gif,image/webp"
        hidden
        aria-label="Logo file"
        onChange={(event) => void onChosen(event)}
      />
      {pending ? (
        <div className="icon-picker__foot logo-picker__confirm" role="group" aria-label="Copy into the workspace">
          <span className="icon-picker__caption" title={pending.target}>
            Copy {pending.name} → {pending.target}
          </span>
          <button className="icon-picker__use" disabled={busy} onClick={() => void confirmCopy()}>
            Copy and use
          </button>
          <button
            className="logo-picker__secondary"
            disabled={busy}
            onClick={() => {
              setPending(null);
              setStrip(request.current);
              previewing.current = null;
              request.onPreview(null);
            }}
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="icon-picker__foot">
          <button
            className="logo-picker__secondary"
            disabled={busy || library === null}
            onClick={() => chooser.current?.click()}
          >
            Choose a file…
          </button>
          <span className="icon-picker__caption" title={focused?.path}>
            {focused ? focused.path : "Arrows to preview · Enter to use"}
          </span>
          <button
            className="icon-picker__use"
            disabled={focused === null || !usable(focused)}
            onClick={() => focused && use(focused.path)}
          >
            Use
          </button>
        </div>
      )}
    </div>
  );
}
