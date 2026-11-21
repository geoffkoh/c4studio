import { useEffect, useRef, useState } from "react";

import { EDGE_COLOUR, EDGE_LINE_STYLE } from "@c4studio/diagram-core";

import type { GEdge, GNode, GraphData, StyleEditRequest, StyleLocation } from "../types";
import type { IconPickRequest } from "./IconPicker";

/** A colour shown on the canvas before it is written (PP-231). */
export interface StylePreview {
  kind: StyleLocation["kind"];
  ids: string[];
  property: string;
  /** `null` puts back what the payload drew: the preview is over. */
  value: string | null;
  /** An icon drawn in `currentColor`, painted in the text colour (PP-239). */
  tint?: boolean;
}

export type StyleTarget =
  | { kind: "element"; node: GNode }
  | { kind: "relationship"; edge: GEdge };

interface StyleEditorProps {
  target: StyleTarget;
  payload: GraphData | null;
  locations: StyleLocation[];
  /** Makes the edit; resolves to what happened, in words. */
  onEdit: (edit: StyleEditRequest) => Promise<string>;
  onPreview: (preview: StylePreview) => void;
  /** Opens the icon picker in place of the card's body (PP-233). */
  onPickIcon?: (request: IconPickRequest) => void;
}

interface Row {
  property: string;
  label: string;
  value: string | null;
  origin: { tag: string; theme: boolean } | null;
}

/** Text on a box when no style sets it: the node CSS's `#fff`. */
const DEFAULT_TEXT = "#ffffff";
const DASHES = ["solid", "dashed", "dotted"] as const;

/** Whether `tag` is one an earlier "only this element" made: the
    element's name, or its name and a number (`style_edit.is_own_tag`). */
export function isOwnTag(tag: string, name: string): boolean {
  if (tag === name) return true;
  return tag.startsWith(`${name} `) && /^\d+$/.test(tag.slice(name.length + 1));
}

/** An icon file named the way a person would say it, as the server's
    `icon_library.friendly_name` does: `Arch_AWS-Lambda_48.svg` is "Lambda". */
export function iconName(path: string): string {
  if (/^(https?|data):/.test(path)) return path.startsWith("data:") ? "embedded image" : path;
  const parts = path.split("/");
  let stem = parts[parts.length - 1].replace(/\.[^.]+$/, "");
  let qualifier = "";
  const shade = /[_-](light|dark)$/i.exec(stem);
  if (shade) {
    qualifier = shade[1].toLowerCase();
    stem = stem.slice(0, shade.index);
  }
  stem = stem
    .replace(/[_-]\d{2,3}$/, "")
    .replace(/^(?:Arch-Category|Arch|Res)_/, "")
    .replace(/^(?:AWS|Amazon)[-_]/, "");
  const name = stem.replace(/[-_\s]+/g, " ").trim() || parts[parts.length - 1];
  const folder = (parts[parts.length - 2] ?? "").toLowerCase();
  if (!qualifier && ["solid", "regular", "brands", "light", "thin", "duotone"].includes(folder)) {
    qualifier = folder;
  }
  return qualifier ? `${name} (${qualifier})` : name;
}

/** What `<input type="color">` accepts: `#rrggbb`, lower case. */
function asHex(value: string | null): string {
  if (!value) return "#000000";
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(value);
  if (short) return `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`.toLowerCase();
  return /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : "#000000";
}

/**
 * Change an element's or a line's colours from the details card (PP-231).
 *
 * Every change is an edit to the DSL `styles` block — never the layout
 * sidecar, which is per-user and gitignored, while a colour is part of
 * what the model says. Dragging in the picker repaints the canvas only;
 * the edit is made once, when the picker closes.
 *
 * Styles are per tag, so the reach of a change is shown before it is
 * made: every element carrying the tag (with the model-wide count), or
 * this element alone, which gives it a tag of its own.
 */
export function StyleEditor({
  target,
  payload,
  locations,
  onEdit,
  onPreview,
  onPickIcon,
}: StyleEditorProps) {
  const [scope, setScope] = useState<"tag" | "element">("tag");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; error: boolean } | null>(null);

  const kind = target.kind;
  const written = new Set(locations.filter((rule) => rule.kind === kind).map((rule) => rule.tag));
  const counts = payload?.styleTagCounts?.[kind] ?? {};
  const generic = kind === "element" ? "Element" : "Relationship";
  const matched = (kind === "element" ? target.node.data.matchedStyles : target.edge.matchedStyles) ?? [];
  // "All": the most specific rule that matched, else every one of its kind.
  const specific = [...matched].reverse().find((tag) => tag !== generic);
  const allTag =
    specific ?? (kind === "element" ? (target.node.data.kindTag ?? generic) : generic);

  const name = kind === "element" ? target.node.data.label : "";
  const ownTag =
    kind === "element"
      ? target.node.data.tags.find(
          (tag) => isOwnTag(tag, name) && written.has(tag) && counts[tag] === 1,
        )
      : undefined;
  const editingTag = scope === "tag" ? allTag : ownTag;

  let rows: Row[];
  if (kind === "element") {
    const { data } = target.node;
    const origins = data.styleOrigins ?? {};
    rows = [
      {
        property: "background",
        label: "Background",
        value: data.background ?? data.color ?? null,
        origin: origins.background ?? null,
      },
      { property: "color", label: "Text", value: data.textColor ?? DEFAULT_TEXT, origin: origins.color ?? null },
      { property: "stroke", label: "Border", value: data.stroke ?? null, origin: origins.stroke ?? null },
      {
        property: "icon",
        label: "Icon",
        // A theme's icon has no path of its own: its origin names it.
        value: data.iconSource ?? null,
        origin: origins.icon ?? null,
      },
    ];
  } else {
    const { edge } = target;
    const origin = (tag?: string) => (tag ? { tag, theme: !written.has(tag) } : null);
    rows = [
      { property: "color", label: "Colour", value: edge.color ?? EDGE_COLOUR, origin: origin(edge.styleOrigins?.color) },
      {
        property: "style",
        label: "Dash",
        value: edge.lineStyle ?? EDGE_LINE_STYLE,
        origin: origin(edge.styleOrigins?.style),
      },
    ];
  }

  const setHere = (row: Row) =>
    row.origin !== null && !row.origin.theme && row.origin.tag === editingTag;

  /** The boxes or lines a change would reach on this view, to preview. */
  const reach = (): string[] => {
    if (kind === "element") {
      if (scope === "element") return [target.node.id];
      return (payload?.nodes ?? [])
        .filter(
          (n) =>
            n.id === target.node.id ||
            (n.data.matchedStyles ?? []).includes(allTag) ||
            n.data.kindTag === allTag ||
            allTag === generic,
        )
        .map((n) => n.id);
    }
    return (payload?.edges ?? [])
      .filter(
        (e) => e.id === target.edge.id || allTag === generic || (e.matchedStyles ?? []).includes(allTag),
      )
      .map((e) => e.id);
  };

  const commit = (property: string, value: string | null) => {
    const edit: StyleEditRequest =
      scope === "element" && kind === "element"
        ? { kind, property, value, element: target.node.id }
        : { kind, property, value, tag: allTag };
    setBusy(true);
    setStatus(null);
    onEdit(edit)
      .then((text) => setStatus({ text, error: false }))
      .catch((err: unknown) =>
        setStatus({ text: err instanceof Error ? err.message : "Could not change the style", error: true }),
      )
      .finally(() => setBusy(false));
  };

  const preview = (property: string, value: string | null, tint?: boolean) =>
    onPreview({ kind, ids: reach(), property, value, tint });

  const count = counts[allTag];
  const what = kind === "element" ? "" : " lines";
  const scopeLabel =
    scope === "element" ? "Only this" : `All “${allTag}”${count !== undefined ? ` (${count})` : ""}`;

  const pickIcon = () => {
    if (kind !== "element" || !onPickIcon) return;
    onPickIcon({
      ownerId: target.node.id,
      title: `Icon · ${scopeLabel}`,
      current: target.node.data.iconSource,
      onPreview: (url, tint) => preview("icon", url, tint),
      onUse: (value) => {
        preview("icon", null);
        commit("icon", value);
      },
    });
  };

  let note: string;
  if (scope === "element") {
    note = ownTag
      ? `Edits “${ownTag}”, this element's own style`
      : `Adds the tag “${name}” to this element, and a style for it`;
  } else {
    note = written.has(allTag) ? `Edits the “${allTag}” style` : `Adds a “${allTag}” style`;
  }

  return (
    <div className="style-editor" aria-label="Edit style">
      {kind === "element" ? (
        <div className="style-editor__scope" role="radiogroup" aria-label="Which elements change">
          <button
            role="radio"
            aria-checked={scope === "tag"}
            className="style-editor__scope-option"
            onClick={() => setScope("tag")}
          >
            All “{allTag}”{count !== undefined ? ` (${count})` : ""}
          </button>
          <button
            role="radio"
            aria-checked={scope === "element"}
            className="style-editor__scope-option"
            onClick={() => setScope("element")}
          >
            Only this
          </button>
        </div>
      ) : (
        <div className="style-editor__scope-fixed">
          All “{allTag}”{what}
          {count !== undefined ? ` (${count})` : ""}
        </div>
      )}
      <p className="style-editor__note">{note}</p>

      <div className="style-editor__rows">
        {rows.map((row) => {
          const here = setHere(row);
          const source = row.origin
            ? row.origin.theme
              ? `theme · ${row.origin.tag}`
              : here
                ? "set here"
                : `from ${row.origin.tag}`
            : "default";
          return (
            <div className="style-editor__row" key={row.property}>
              <span className="style-editor__label">{row.label}</span>
              {row.property === "icon" ? (
                <button
                  className={
                    "style-editor__icon" + (kind === "element" && target.node.data.icon ? "" : " style-editor__icon--none")
                  }
                  aria-label="Icon"
                  title="Choose an icon"
                  disabled={busy || !onPickIcon}
                  onClick={pickIcon}
                >
                  {kind === "element" && target.node.data.icon ? (
                    <img src={target.node.data.icon} alt="" />
                  ) : null}
                </button>
              ) : row.property === "style" ? (
                <select
                  aria-label={row.label}
                  className="style-editor__dash"
                  value={(row.value ?? EDGE_LINE_STYLE).toLowerCase()}
                  disabled={busy}
                  onChange={(event) => {
                    preview(row.property, event.target.value);
                    commit(row.property, event.target.value);
                  }}
                >
                  {DASHES.map((dash) => (
                    <option key={dash} value={dash}>
                      {dash[0].toUpperCase() + dash.slice(1)}
                    </option>
                  ))}
                </select>
              ) : (
                <ColourInput
                  key={asHex(row.value)}
                  label={row.label}
                  value={row.value}
                  disabled={busy}
                  onPreview={(value) => preview(row.property, value)}
                  onCommit={(value) => commit(row.property, value)}
                />
              )}
              <span
                className={"style-editor__origin" + (here ? " style-editor__origin--here" : "")}
                title={row.property === "icon" ? (row.value ?? undefined) : undefined}
              >
                {row.property === "style"
                  ? source
                  : row.property === "icon"
                    ? row.value
                      ? `${iconName(row.value)} · ${source}`
                      : row.origin?.theme
                        ? source
                        : `none · ${source}`
                    : `${row.value ?? "none"} · ${source}`}
              </span>
              {here ? (
                <button
                  className="style-editor__reset"
                  title={`Remove ${row.label.toLowerCase()} from the “${editingTag}” style`}
                  aria-label={`Reset ${row.label.toLowerCase()}`}
                  disabled={busy}
                  onClick={() => commit(row.property, null)}
                >
                  ×
                </button>
              ) : (
                <span />
              )}
            </div>
          );
        })}
      </div>

      {status ? (
        <p
          className={"style-editor__status" + (status.error ? " style-editor__status--error" : "")}
          role="status"
        >
          {status.text}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The native colour input, uncontrolled: React's `onChange` on it fires on
 * every move of the picker, so it previews; the DOM's own `change` fires
 * once, when the picker closes, and that is the edit. Its caller keys it
 * on the value, so a reload that changes the colour remounts it.
 */
function ColourInput({
  label,
  value,
  disabled,
  onPreview,
  onCommit,
}: {
  label: string;
  value: string | null;
  disabled: boolean;
  onPreview: (value: string) => void;
  onCommit: (value: string) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const commit = useRef(onCommit);
  commit.current = onCommit;
  useEffect(() => {
    const input = ref.current;
    if (!input) return;
    const handle = () => commit.current(input.value);
    input.addEventListener("change", handle);
    return () => input.removeEventListener("change", handle);
  }, []);
  return (
    <input
      ref={ref}
      type="color"
      className="style-editor__swatch"
      aria-label={label}
      defaultValue={asHex(value)}
      disabled={disabled}
      onChange={(event) => onPreview(event.target.value)}
    />
  );
}
