// How tall a node needs to be for its own text.
//
// Three places have to agree on this: dagre (which reserves the space),
// the SVG emitter (which draws the box) and the web app's CSS (which grows
// the box around its content). They disagreed before — dagre reserved a
// flat 110px while `.node` grew freely — so a long name pushed its box
// into the rank below, and the SVG emitter compensated by starving the
// description of lines until it fitted. Both failure modes come from the
// same missing number, so it is computed once, here.
//
// The constants mirror `.node` and its children in the web app's
// index.css. Change one side and this file has to follow, or nodes will
// be measured as something other than what they render as.

export const NODE_WIDTH = 200;

// Floors, not fixed sizes: a node with little to say still gets a box big
// enough to read as one, and a Person's silhouette needs the extra room.
export const NODE_MIN_HEIGHT = 110;
export const PERSON_MIN_HEIGHT = 150;

export const NODE_PAD_TOP = 10;
export const NODE_PAD_BOTTOM = 10;
export const NODE_PAD_X = 12;
export const PERSON_PAD_TOP = 20;

// `.node__icon`: 30px square above the label, with 2px/4px margins.
export const ICON_SIZE = 30;
export const ICON_MARGIN_TOP = 2;
export const ICON_MARGIN_BOTTOM = 4;
/** Total vertical room an icon adds. */
export const ICON_ALLOWANCE = ICON_SIZE + ICON_MARGIN_TOP + ICON_MARGIN_BOTTOM;

export const LABEL_SIZE = 13;
export const LABEL_LEADING = 16;
export const SMALL_SIZE = 10;
export const SMALL_LEADING = 13;
export const META_GAP = 3;
export const DESC_GAP = 5;

// Line caps per field. The web app's CSS clamps to exactly these, so the
// rendered box can never grow past what was measured for it. They are
// generous rather than tight: clipping a name is worse than a tall box,
// and the description no longer has to give up its lines to a long name.
export const LABEL_MAX_LINES = 4;
export const META_MAX_LINES = 2;
export const DESC_MAX_LINES = 4;

/**
 * Character width as a fraction of font size, for wrapping without a DOM.
 * Measured against the SPA's font stack; erring high keeps text inside the
 * box rather than overflowing it.
 */
export const CHAR_RATIO = 0.55;
export const BOLD_CHAR_RATIO = 0.58;

/**
 * Slack added to every measured height.
 *
 * The leading constants above are whole pixels while the CSS line-heights
 * are fractional (13px × 1.25 = 16.25 against a 16px leading, 10px × 1.35
 * = 13.5 against 13), so a fully-wrapped box renders a couple of pixels
 * taller than the arithmetic here suggests. Being under is the dangerous
 * direction — that is an overlap — so the difference is paid back with
 * interest and rounded up.
 */
const HEIGHT_SLACK = 10;

/** Extra vertical padding some shapes add on top of `.node`'s own. */
const SHAPE_EXTRA_HEIGHT: Record<string, number> = {
  // `.node--circle`: padding 18px rather than 10px, top and bottom.
  Circle: 16,
  Ellipse: 16,
  // `.node--cylinder`: 12px margin plus a 16px top padding for the cap.
  Cylinder: 18,
  Bucket: 18,
  // `.node--folder` / `.node--browser`: room for the tab and chrome bar.
  Folder: 12,
  WebBrowser: 14,
  Window: 14,
  // `.node--mobile-*`: 14px padding, top and bottom.
  MobileDevicePortrait: 8,
  MobileDeviceLandscape: 8,
};

/** Horizontal padding some shapes add, which narrows the text column. */
const SHAPE_EXTRA_PAD_X: Record<string, number> = {
  Circle: 8,
  Ellipse: 8,
  Pipe: 12,
  Hexagon: 22,
};

/** The subset of node data that affects how much room the text needs. */
export interface NodeTextData {
  label?: string;
  kind?: string;
  technology?: string;
  description?: string;
  shape?: string;
  icon?: string;
  showMetadata?: boolean;
}

/** C4 metadata label per element kind, shown as `[Container: Java]`. */
const KIND_LABELS: Record<string, string> = {
  person: "Person",
  "person-external": "Person",
  system: "Software System",
  "system-external": "Software System",
  container: "Container",
  component: "Component",
  infrastructure: "Infrastructure Node",
  "container-instance": "Container",
  "system-instance": "Software System",
  group: "Group",
};

/**
 * The `[Kind: technology]` line, or null when an element style declares
 * `metadata false`. The backend blanks the technology in that case but the
 * kind is composed here, so the whole line has to be dropped explicitly.
 */
export function metaLine(data: NodeTextData): string | null {
  if (data.showMetadata === false) return null;
  const kindLabel = KIND_LABELS[data.kind ?? ""] ?? data.kind ?? "";
  if (!kindLabel) return null;
  return data.technology ? `[${kindLabel}: ${data.technology}]` : `[${kindLabel}]`;
}

/**
 * Split `text` into at most `maxLines` lines that fit `maxWidth`, marking
 * a clipped final line with an ellipsis as the CSS line clamp does.
 */
export function wrap(
  text: string,
  maxWidth: number,
  fontSize: number,
  maxLines: number,
  bold = false,
): string[] {
  const perChar = fontSize * (bold ? BOLD_CHAR_RATIO : CHAR_RATIO);
  const limit = Math.max(1, Math.floor(maxWidth / perChar));
  const lines: string[] = [];
  let current = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= limit) {
      current = candidate;
      continue;
    }
    if (current) lines.push(current);
    current = word.length > limit ? `${word.slice(0, limit - 1)}…` : word;
    if (lines.length === maxLines) break;
  }
  if (current && lines.length < maxLines) lines.push(current);
  if (lines.length > maxLines) lines.length = maxLines;
  const consumed = lines.join(" ").replace(/…$/, "");
  if (consumed.length < text.replace(/\s+/g, " ").trim().length && lines.length) {
    const last = lines[lines.length - 1];
    if (!last.endsWith("…")) {
      lines[lines.length - 1] = `${last.slice(0, Math.max(0, limit - 1))}…`;
    }
  }
  return lines;
}

/** Whether a node renders as the C4 person silhouette. */
export function isPersonNode(data: NodeTextData): boolean {
  return (
    data.shape === "Person" ||
    data.shape === "Robot" ||
    (data.shape === undefined && (data.kind ?? "").startsWith("person"))
  );
}

/** Width of the text column inside a node of the given shape. */
export function textWidth(data: NodeTextData): number {
  const extra = SHAPE_EXTRA_PAD_X[data.shape ?? ""] ?? 0;
  return NODE_WIDTH - 2 * (NODE_PAD_X + extra);
}

/** The wrapped lines a node will show, each already capped and ellipsised. */
export function nodeTextLines(data: NodeTextData): {
  label: string[];
  meta: string[];
  description: string[];
} {
  const inner = textWidth(data);
  const meta = metaLine(data);
  return {
    label: wrap(data.label ?? "", inner, LABEL_SIZE, LABEL_MAX_LINES, true),
    meta: meta ? wrap(meta, inner, SMALL_SIZE, META_MAX_LINES) : [],
    description: data.description
      ? wrap(data.description, inner, SMALL_SIZE, DESC_MAX_LINES)
      : [],
  };
}

/**
 * How tall a node must be to show its text without clipping it.
 *
 * Never smaller than the kind's floor, so short-labelled nodes keep the
 * proportions the diagram is used to; taller whenever the content needs
 * it, which is the whole point.
 */
export function nodeHeight(data: NodeTextData): number {
  const lines = nodeTextLines(data);
  const person = isPersonNode(data);

  let height = (person ? PERSON_PAD_TOP : NODE_PAD_TOP) + NODE_PAD_BOTTOM;
  if (data.icon) height += ICON_ALLOWANCE;
  height += lines.label.length * LABEL_LEADING;
  if (lines.meta.length) {
    height += META_GAP + lines.meta.length * SMALL_LEADING;
  }
  if (lines.description.length) {
    height += DESC_GAP + lines.description.length * SMALL_LEADING;
  }
  height += SHAPE_EXTRA_HEIGHT[data.shape ?? ""] ?? 0;
  height += HEIGHT_SLACK;

  const floor =
    (person ? PERSON_MIN_HEIGHT : NODE_MIN_HEIGHT) +
    (data.icon ? ICON_ALLOWANCE : 0);
  return Math.max(floor, Math.ceil(height));
}

/** The full box a node occupies in the layout. */
export function nodeBox(data: NodeTextData): { width: number; height: number } {
  return { width: NODE_WIDTH, height: nodeHeight(data) };
}

/**
 * The node's text in full, but only when the box could not show all of it.
 *
 * Boxes grow to fit, so this is now the exception rather than the rule —
 * a description longer than four lines, or a name longer than four. What
 * is left is genuinely long prose, and a diagram is the wrong place to
 * read it; being able to hover and see it is enough.
 */
export function nodeTooltip(data: NodeTextData): string | null {
  const lines = nodeTextLines(data);
  const meta = metaLine(data);
  const clipped =
    lines.label.some((line) => line.endsWith("…")) ||
    lines.meta.some((line) => line.endsWith("…")) ||
    lines.description.some((line) => line.endsWith("…"));
  if (!clipped) return null;
  return [data.label, meta, data.description].filter(Boolean).join("\n");
}
