/**
 * Headless SVG rendering.
 *
 * The SPA draws a diagram as HTML in a React Flow canvas; `export.ts`
 * rasterises that live canvas with html-to-image, which needs a browser.
 * This module draws the same diagram as pure SVG markup from the graph
 * payload alone, so `c4 render` works in CI, in a Forge
 * resolver, or anywhere else with no DOM.
 *
 * Layout is the *same* code the SPA runs (`layout.ts`), so node positions
 * are identical rather than merely similar. What is re-implemented here is
 * only the painting: the CSS in `index.css` and the JSX in the node and
 * edge components, expressed as SVG.
 *
 * Deliberately self-contained: no external fonts or stylesheets, and theme
 * icons arrive already embedded as `data:` URIs (the Python side fetches
 * them), so an exported file renders the same wherever it is opened —
 * offline, in a wiki, or attached to a ticket.
 */

import type { Edge, Node } from "reactflow";

import {
  EDGE_COLOUR,
  EDGE_LINE_STYLE,
  EDGE_WIDTH,
} from "./edgeDefaults";
import {
  layoutGraph,
  normalizeStoredPositions,
  type RankDirection,
} from "./layout";
import { applyPerspective, type Perspective } from "./perspective";
import {
  CHAR_RATIO,
  DESC_GAP,
  DESC_MAX_LINES,
  ICON_MARGIN_BOTTOM,
  ICON_MARGIN_TOP,
  ICON_SIZE,
  LABEL_LEADING,
  LABEL_MAX_LINES,
  META_GAP,
  META_MAX_LINES,
  NODE_PAD_TOP,
  NODE_PAD_X,
  NODE_WIDTH,
  LABEL_SIZE,
  PERSON_PAD_TOP,
  SMALL_LEADING,
  SMALL_SIZE,
  isPersonNode,
  metaLine,
  nodeHeight,
  textWidth,
  wrap,
} from "./nodeMetrics";

// ---------------------------------------------------------------------------
// The payload, matching what `webapp/graph.py` serves the SPA.
// ---------------------------------------------------------------------------

export interface GraphPayloadNode {
  id: string;
  parentId?: string;
  position?: { x: number; y: number };
  size?: { width: number; height: number };
  data: {
    label: string;
    kind: string;
    color?: string | null;
    technology?: string;
    description?: string;
    background?: string;
    textColor?: string;
    shape?: string;
    boundaryLabel?: string;
    /** Per-boundary auto-layout override (`c4studio.autolayout`). */
    rankDirection?: string;
    showMetadata?: boolean;
    /** A `data:` URI — the Python side embeds theme icons before render. */
    icon?: string;
    /** Outline properties from the element style: "Solid" | "Dashed" | "Dotted". */
    border?: string;
    stroke?: string;
    strokeWidth?: number;
    /** Percentage, as Structurizr spells it. */
    opacity?: number;
    /** Perspectives the element carries, with any `Perspective:` style
        already resolved by the server. */
    perspectives?: Perspective[];
    /** Set by `applyPerspective`: the value to badge this node with. */
    perspectiveBadge?: string;
  };
}

export interface GraphPayloadEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  waypoints?: [number, number][];
  /** Resolved relationship-style paint; absent fields use the defaults
      (dashed, per upstream Structurizr). */
  color?: string;
  perspectives?: Perspective[];
  lineStyle?: string;
  thickness?: number;
  /** Percentage, as Structurizr spells it (0–100). */
  opacity?: number;
}

export interface LegendEntry {
  /** What the row explains; a relationship row draws a line, not a box. */
  kind?: "element" | "relationship";
  label: string;
  colour?: string;
  /** Element rows only. */
  shape?: string;
  /** "Dashed" | "Dotted" | "Solid" | "" — the swatch must show what the row claims. */
  border?: string;
  /** Relationship rows only; absent fields fall back to the line defaults. */
  lineStyle?: string;
  thickness?: number;
}

export interface GraphPayload {
  nodes: GraphPayloadNode[];
  edges: GraphPayloadEdge[];
  rankDirection?: RankDirection;
  /** Spacing the view declared via `autoLayout`, honoured by the layout. */
  rankSeparation?: number;
  nodeSeparation?: number;
  /** Distinct styles used by this view, derived in the graph layer. */
  legend?: LegendEntry[];
}

export interface RenderOptions {
  /** Draw the title as a heading above the diagram (default: true). */
  showTitle?: boolean;
  /** Draw the legend below the diagram (default: true when entries exist). */
  showLegend?: boolean;
  /** Show one perspective: fade what lacks it, badge what carries it, and
      rebuild the legend from its values (PP-178). */
  perspective?: string;
  /** Blank margin around the diagram bounds. */
  padding?: number;
  /** Page background; `null` leaves it transparent. */
  background?: string | null;
  /** `<title>` element, for accessibility and image viewers. */
  title?: string;
}

// ---------------------------------------------------------------------------
// Paint, mirroring index.css and the node components.
// ---------------------------------------------------------------------------

const FONT =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

const NODE_RADIUS = 8;
const PERSON_RADIUS = 18;
const PERSON_HEAD = 38;

const NODE_STROKE = "rgba(0,0,0,0.12)";
const FALLBACK_FILL = "#78909c";
const TEXT_COLOUR = "#ffffff";

const BOUNDARY_STROKE = "#90a4ae";
const BOUNDARY_FILL = "rgba(144,164,174,0.07)";
const BOUNDARY_RADIUS = 10;
// `.boundary__label`: bottom-left, the type italicised beside the name.
const BOUNDARY_LABEL_SIZE = 12;
const BOUNDARY_LABEL_COLOUR = "#546e7a";

// Title band and legend. Both sit outside the diagram bounds, so they
// extend the canvas rather than overlapping any element.
const TITLE_SIZE = 18;
const TITLE_COLOUR = "#172b4d";
const TITLE_GAP = 20;
const LEGEND_SWATCH = 14;
const LEGEND_ROW = 22;
const LEGEND_LABEL_SIZE = 11;
const LEGEND_LABEL_COLOUR = "#44546f";
const LEGEND_GAP = 24;
const LEGEND_PAD = 12;
const LEGEND_COLUMN_WIDTH = 220;
const LEGEND_MAX_ROWS = 6;
// The perspective value badge, matching `.node__perspective` in the app.
const BADGE_SIZE = 10;
const BADGE_HEIGHT = 16;
//: A row label is usually a tag and fits one line; a `c4studio.legend`
//: caption is prose and does not, so rows take a second line when any
//: label needs it. Uniform across the grid, so the rows stay aligned.
const LEGEND_MAX_LABEL_LINES = 2;

// From edgeDefaults.ts, which deliberately imports no reactflow so this
// headless path can share it. They used to be separate copies.
const ARROW = 10;
const EDGE_LABEL_SIZE = 10;
const EDGE_LABEL_COLOUR = "#6b7684"; // --muted
const EDGE_LABEL_BG = "rgba(255,255,255,0.92)";
const EDGE_LABEL_BORDER = "#e2e5ea"; // --border

interface Point {
  x: number;
  y: number;
}

interface Placed {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  isBoundary: boolean;
  isPerson: boolean;
  data: GraphPayloadNode["data"];
}

// ---------------------------------------------------------------------------
// Text
// ---------------------------------------------------------------------------

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function textLine(
  content: string,
  x: number,
  y: number,
  size: number,
  colour: string,
  opacity = 1,
  weight = 400,
  anchor = "middle",
): string {
  const fill = opacity === 1 ? colour : `${colour}" opacity="${opacity}`;
  return (
    `<text x="${round(x)}" y="${round(y)}" font-family="${FONT}" ` +
    `font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" ` +
    `fill="${fill}">${escapeXml(content)}</text>`
  );
}

const round = (n: number): number => Math.round(n * 100) / 100;

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------

/** Where the line from a node's centre towards `aimAt` leaves its box. */
function borderIntersection(node: Placed, aimAt: Point): Point {
  const w = node.width / 2;
  const h = node.height / 2;
  const cx = node.x + w;
  const cy = node.y + h;
  const dx = (aimAt.x - cx) / (2 * w) || 0;
  const dy = (aimAt.y - cy) / (2 * h) || 0;
  const scale = 1 / Math.max(Math.abs(dx), Math.abs(dy)) || 1;
  return { x: cx + dx * scale * w, y: cy + dy * scale * h };
}

/** Absolute positions: React Flow nests children inside their parent. */
function place(nodes: Node[]): Map<string, Placed> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const placed = new Map<string, Placed>();

  const absolute = (node: Node): Point => {
    let x = node.position.x;
    let y = node.position.y;
    let parent = node.parentNode ? byId.get(node.parentNode) : undefined;
    while (parent) {
      x += parent.position.x;
      y += parent.position.y;
      parent = parent.parentNode ? byId.get(parent.parentNode) : undefined;
    }
    return { x, y };
  };

  for (const node of nodes) {
    const { x, y } = absolute(node);
    const data = (node.data ?? {}) as GraphPayloadNode["data"];
    const isBoundary = node.type === "boundary";
    const isPerson = !isBoundary && isPersonNode(data);
    placed.set(node.id, {
      id: node.id,
      x,
      y,
      width: Number(node.style?.width ?? NODE_WIDTH),
      // Same measurement dagre reserved space with, so the drawn box is
      // the box the layout planned for.
      height: Number(node.style?.height ?? nodeHeight(data)),
      isBoundary,
      isPerson,
      data,
    });
  }
  return placed;
}

// ---------------------------------------------------------------------------
// Painting
// ---------------------------------------------------------------------------

function fillOf(data: GraphPayloadNode["data"]): string {
  return data.background || data.color || FALLBACK_FILL;
}

/**
 * Dash pattern for a Structurizr `border`, scaled to the stroke width so a
 * thick dashed outline does not read as solid.
 */
function dashArray(border: string | undefined, width: number): string {
  switch (border) {
    case "Dashed":
      return ` stroke-dasharray="${round(width * 5)} ${round(width * 3)}"`;
    case "Dotted":
      return ` stroke-dasharray="${round(width)} ${round(width * 2.5)}"`;
    default:
      return "";
  }
}

/** Fill and outline attributes for a node, honouring its element style. */
function outlineOf(data: GraphPayloadNode["data"], fill: string): string {
  const width = data.strokeWidth ?? 1;
  const colour = data.stroke || NODE_STROKE;
  return (
    ` fill="${fill}" stroke="${colour}" stroke-width="${width}"` +
    dashArray(data.border, width)
  );
}

/** The box outline, honouring the Structurizr shape where SVG can. */
function shapeMarkup(node: Placed, fill: string): string {
  const { x, y, width, height } = node;
  const stroke = outlineOf(node.data, fill);
  switch (node.data.shape) {
    case "Circle":
    case "Ellipse":
      return (
        `<ellipse cx="${round(x + width / 2)}" cy="${round(y + height / 2)}" ` +
        `rx="${round(width / 2)}" ry="${round(height / 2)}"${stroke}/>`
      );
    case "Hexagon": {
      const inset = width * 0.12;
      const points = [
        [x + inset, y],
        [x + width - inset, y],
        [x + width, y + height / 2],
        [x + width - inset, y + height],
        [x + inset, y + height],
        [x, y + height / 2],
      ]
        .map(([px, py]) => `${round(px)},${round(py)}`)
        .join(" ");
      return `<polygon points="${points}"${stroke}/>`;
    }
    case "Diamond": {
      const points = [
        [x + width / 2, y],
        [x + width, y + height / 2],
        [x + width / 2, y + height],
        [x, y + height / 2],
      ]
        .map(([px, py]) => `${round(px)},${round(py)}`)
        .join(" ");
      return `<polygon points="${points}"${stroke}/>`;
    }
    case "Cylinder":
    case "Bucket":
    case "Pipe": {
      // Body plus the elliptical cap the CSS draws with a pseudo-element.
      const ry = 10;
      return (
        `<path d="M ${round(x)} ${round(y + ry)} L ${round(x)} ${round(y + height - ry)} ` +
        `A ${round(width / 2)} ${ry} 0 0 0 ${round(x + width)} ${round(y + height - ry)} ` +
        `L ${round(x + width)} ${round(y + ry)} Z"${stroke}/>` +
        `<ellipse cx="${round(x + width / 2)}" cy="${round(y + ry)}" ` +
        `rx="${round(width / 2)}" ry="${ry}"${stroke}/>`
      );
    }
    case "Box":
      return `<rect x="${round(x)}" y="${round(y)}" width="${round(width)}" height="${round(height)}"${stroke}/>`;
    default: {
      const radius = node.isPerson ? PERSON_RADIUS : NODE_RADIUS;
      return (
        `<rect x="${round(x)}" y="${round(y)}" width="${round(width)}" ` +
        `height="${round(height)}" rx="${radius}" ry="${radius}"${stroke}/>`
      );
    }
  }
}

function paintNode(node: Placed): string {
  const fill = fillOf(node.data);
  const colour = node.data.textColor || TEXT_COLOUR;
  const parts: string[] = [];

  // The person silhouette: a head circle overlapping the box, as in
  // `.person__head` (38px, pulled 16px into the box).
  const bodyTop = node.isPerson ? node.y + PERSON_HEAD - 16 : node.y;
  const body: Placed = node.isPerson
    ? { ...node, y: bodyTop, height: node.height - (PERSON_HEAD - 16) }
    : node;
  if (node.isPerson) {
    parts.push(
      `<circle cx="${round(node.x + node.width / 2)}" cy="${round(node.y + PERSON_HEAD / 2)}" ` +
        `r="${PERSON_HEAD / 2}"${outlineOf(node.data, fill)}/>`,
    );
  }
  parts.push(shapeMarkup(body, fill));

  const centreX = node.x + node.width / 2;
  const innerWidth =
    node.width === NODE_WIDTH ? textWidth(node.data) : node.width - 2 * NODE_PAD_X;
  let cursor = body.y + (node.isPerson ? PERSON_PAD_TOP : NODE_PAD_TOP);

  // Only `data:` URIs are drawn: a remote href would make the exported
  // file depend on the network, which is the point of embedding them.
  const icon = node.data.icon;
  if (icon && icon.startsWith("data:")) {
    parts.push(
      `<image x="${round(centreX - ICON_SIZE / 2)}" y="${round(cursor + ICON_MARGIN_TOP)}" ` +
        `width="${ICON_SIZE}" height="${ICON_SIZE}" preserveAspectRatio="xMidYMid meet" ` +
        `href="${escapeXml(icon)}"/>`,
    );
    cursor += ICON_MARGIN_TOP + ICON_SIZE + ICON_MARGIN_BOTTOM;
  }
  cursor += LABEL_SIZE;

  for (const line of wrap(
    node.data.label ?? "",
    innerWidth,
    LABEL_SIZE,
    LABEL_MAX_LINES,
    true,
  )) {
    parts.push(textLine(line, centreX, cursor, LABEL_SIZE, colour, 1, 600));
    cursor += LABEL_LEADING;
  }

  const meta = metaLine(node.data);
  if (meta) {
    cursor += META_GAP;
    for (const line of wrap(meta, innerWidth, SMALL_SIZE, META_MAX_LINES)) {
      parts.push(textLine(line, centreX, cursor, SMALL_SIZE, colour, 0.85));
      cursor += SMALL_LEADING;
    }
  }

  if (node.data.description) {
    cursor += DESC_GAP - SMALL_LEADING + SMALL_SIZE;
    // The box was measured to fit these lines, so the description gets its
    // full allowance. It used to be handed whatever vertical room a long
    // name had left over, which is how a three-line name silently cost the
    // description two of its own.
    for (const line of wrap(
      node.data.description,
      innerWidth,
      SMALL_SIZE,
      DESC_MAX_LINES,
    )) {
      parts.push(textLine(line, centreX, cursor, SMALL_SIZE, colour, 0.8));
      cursor += SMALL_LEADING;
    }
  }

  // The perspective value, on the top border — the same place the viewer
  // puts it, and outside the measured box, so a badge never costs the
  // node's own text a line.
  const badge = node.data.perspectiveBadge;
  if (badge) {
    const text = escapeXml(badge);
    const badgeWidth = text.length * BADGE_SIZE * CHAR_RATIO + 10;
    const badgeX = node.x + 8;
    const badgeY = node.y - BADGE_HEIGHT / 2;
    parts.push(
      `<rect x="${round(badgeX)}" y="${round(badgeY)}" width="${round(badgeWidth)}" ` +
        `height="${BADGE_HEIGHT}" rx="7" ry="7" fill="${EDGE_LABEL_BG}" ` +
        `stroke="${EDGE_LABEL_BORDER}"/>` +
        textLine(
          text,
          badgeX + badgeWidth / 2,
          badgeY + BADGE_HEIGHT - 4,
          BADGE_SIZE,
          EDGE_LABEL_COLOUR,
          1,
          600,
        ),
    );
  }

  // Structurizr's opacity is a percentage over the whole element, so it
  // wraps the finished node — the label must fade with its box, not stay
  // crisp on top of a washed-out shape.
  const opacity = node.data.opacity;
  if (opacity !== undefined && opacity < 100) {
    return `<g opacity="${round(Math.max(0, opacity) / 100)}">${parts.join("")}</g>`;
  }
  return parts.join("");
}

function paintBoundary(node: Placed): string {
  const label = escapeXml(node.data.label ?? "");
  const opacity = node.data.opacity;
  const fade =
    opacity !== undefined && opacity < 100
      ? ` opacity="${round(Math.max(0, opacity) / 100)}"`
      : "";
  const meta = node.data.boundaryLabel;
  const type = meta
    ? `<tspan font-weight="400" font-style="italic" opacity="0.85"> [${escapeXml(meta)}]</tspan>`
    : "";
  const markup =
    `<rect x="${round(node.x)}" y="${round(node.y)}" width="${round(node.width)}" ` +
    `height="${round(node.height)}" rx="${BOUNDARY_RADIUS}" ry="${BOUNDARY_RADIUS}" ` +
    `fill="${BOUNDARY_FILL}" stroke="${BOUNDARY_STROKE}" stroke-width="2" ` +
    `stroke-dasharray="6 4"/>` +
    `<text x="${round(node.x + 12)}" y="${round(node.y + node.height - 9)}" ` +
    `font-family="${FONT}" font-size="${BOUNDARY_LABEL_SIZE}" font-weight="600" ` +
    `fill="${BOUNDARY_LABEL_COLOUR}">${label}${type}</text>`;
  return fade ? `<g${fade}>${markup}</g>` : markup;
}

/** One arrowhead marker per line colour, so heads match their lines. */
function arrowMarkerId(colour: string): string {
  return `arrow-${colour.replace(/[^A-Za-z0-9]/g, "")}`;
}

function arrowMarkerDefs(edges: GraphPayloadEdge[]): string {
  const colours = new Set<string>([EDGE_COLOUR]);
  for (const edge of edges) {
    if (edge.color) colours.add(edge.color);
  }
  return [...colours]
    .map(
      (colour) =>
        `<marker id="${arrowMarkerId(colour)}" viewBox="0 0 10 10" refX="9" refY="5" ` +
        `markerWidth="${ARROW}" markerHeight="${ARROW}" markerUnits="userSpaceOnUse" ` +
        `orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="${colour}"/>` +
        `</marker>`,
    )
    .join("");
}

function paintEdge(
  edge: GraphPayloadEdge,
  placed: Map<string, Placed>,
): string {
  const source = placed.get(edge.source);
  const target = placed.get(edge.target);
  if (!source || !target) return "";

  const waypoints = (edge.waypoints ?? []).map(([x, y]) => ({ x, y }));
  const firstAim = waypoints[0] ?? {
    x: target.x + target.width / 2,
    y: target.y + target.height / 2,
  };
  const lastAim = waypoints[waypoints.length - 1] ?? {
    x: source.x + source.width / 2,
    y: source.y + source.height / 2,
  };
  const start = borderIntersection(source, firstAim);
  const end = borderIntersection(target, lastAim);
  const points = [start, ...waypoints, end];
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${round(p.x)} ${round(p.y)}`)
    .join(" ");

  const colour = edge.color || EDGE_COLOUR;
  const strokeWidth = edge.thickness ?? EDGE_WIDTH;
  const lineStyle =
    edge.lineStyle === "solid" ||
    edge.lineStyle === "dashed" ||
    edge.lineStyle === "dotted"
      ? edge.lineStyle
      : EDGE_LINE_STYLE;
  // Same width-scaled ratios as element borders, so dashes look alike
  // everywhere (and match edgePaint.ts's edgeDashArray).
  const dash =
    lineStyle === "dashed"
      ? ` stroke-dasharray="${round(strokeWidth * 5)} ${round(strokeWidth * 3)}"`
      : lineStyle === "dotted"
        ? ` stroke-dasharray="${round(strokeWidth)} ${round(strokeWidth * 2.5)}"`
        : "";
  const opacity =
    edge.opacity !== undefined ? ` opacity="${edge.opacity / 100}"` : "";
  const path =
    `<path d="${d}" fill="none" stroke="${colour}" ` +
    `stroke-width="${strokeWidth}"${dash}${opacity} ` +
    `marker-end="url(#${arrowMarkerId(colour)})"/>`;

  if (!edge.label) return path;

  // Label sits at the middle of the routed line, in a small plate.
  const mid = points[Math.floor((points.length - 1) / 2)];
  const next = points[Math.floor((points.length - 1) / 2) + 1] ?? mid;
  const cx = (mid.x + next.x) / 2;
  const cy = (mid.y + next.y) / 2;
  const [line] = wrap(edge.label, 220, EDGE_LABEL_SIZE, 1);
  const width = line.length * EDGE_LABEL_SIZE * CHAR_RATIO + 10;
  // The plate fades with its line: a crisp label over a faded
  // relationship reads as the label belonging to something else, which is
  // exactly what a perspective is trying to say it does not.
  const label =
    `<rect x="${round(cx - width / 2)}" y="${round(cy - 8)}" width="${round(width)}" ` +
    `height="16" rx="4" ry="4" fill="${EDGE_LABEL_BG}" stroke="${EDGE_LABEL_BORDER}"/>` +
    textLine(line, cx, cy + 3.5, EDGE_LABEL_SIZE, EDGE_LABEL_COLOUR);
  return path + (opacity ? `<g${opacity}>${label}</g>` : label);
}

/** Widest line a 14px swatch can show and still read as a line. */
const LEGEND_LINE_MAX_WIDTH = 3;

/** Dash patterns at swatch scale, keyed by line style. */
const LEGEND_LINE_DASH: Record<string, string> = {
  dashed: ' stroke-dasharray="3 2"',
  dotted: ' stroke-dasharray="1 2"',
  solid: "",
};

/**
 * A miniature relationship: the line as styled, with an arrowhead.
 *
 * Drawn as an explicit triangle rather than through `marker-end`, so the
 * row does not depend on a marker def existing for this colour.
 */
function legendLineSwatch(entry: LegendEntry, x: number, y: number): string {
  const size = LEGEND_SWATCH;
  const colour = entry.colour || EDGE_COLOUR;
  const width = Math.min(entry.thickness ?? EDGE_WIDTH, LEGEND_LINE_MAX_WIDTH);
  const lineStyle =
    entry.lineStyle === "solid" ||
    entry.lineStyle === "dashed" ||
    entry.lineStyle === "dotted"
      ? entry.lineStyle
      : EDGE_LINE_STYLE;
  // Swatch-scale dashes, not the edge's width-scaled ones: an 18px line
  // at the real ratios fits a single dash and reads as solid, which is
  // the one thing the row exists to distinguish. Same patterns the
  // element border swatch uses.
  const dash = LEGEND_LINE_DASH[lineStyle];
  const mid = y + size / 2;
  const head = x + size + 4;
  return (
    `<path d="M${round(x)} ${round(mid)} H${round(head - 6)}" fill="none" ` +
    `stroke="${colour}" stroke-width="${width}"${dash}/>` +
    `<path d="M${round(head - 7)} ${round(mid - 3.5)} L${round(head)} ${round(mid)} ` +
    `L${round(head - 7)} ${round(mid + 3.5)} Z" fill="${colour}"/>`
  );
}

/** A miniature of the node shape, so the swatch reads as what it explains. */
function legendSwatch(entry: LegendEntry, x: number, y: number): string {
  if (entry.kind === "relationship") return legendLineSwatch(entry, x, y);
  const size = LEGEND_SWATCH;
  const half = size / 2;
  const fill = entry.colour || FALLBACK_FILL;
  // A patterned outline has to be visible at 14px to say anything, and the
  // default node stroke (12% black) is not. Darken it only when there is a
  // pattern to show, so solid swatches keep their light edge.
  const stroke =
    entry.border === "Dashed" || entry.border === "Dotted"
      ? ` stroke="${LEGEND_LABEL_COLOUR}" stroke-width="1.25"` +
        (entry.border === "Dashed"
          ? ' stroke-dasharray="3 2"'
          : ' stroke-dasharray="1 2"')
      : ` stroke="${NODE_STROKE}" stroke-width="1"`;
  switch (entry.shape) {
    case "Boundary":
      // The one entry that explains an outline rather than a fill.
      return (
        `<rect x="${round(x)}" y="${round(y)}" width="${size}" height="${size}" ` +
        `rx="3" fill="none" stroke="${BOUNDARY_STROKE}" stroke-width="1.5" ` +
        `stroke-dasharray="3 2"/>`
      );
    case "Person":
    case "Robot":
      return (
        `<circle cx="${round(x + half)}" cy="${round(y + 4)}" r="3.5" fill="${fill}"${stroke}/>` +
        `<rect x="${round(x)}" y="${round(y + 6)}" width="${size}" height="${size - 6}" ` +
        `rx="3" fill="${fill}"${stroke}/>`
      );
    case "Cylinder":
    case "Bucket":
    case "Pipe":
      return (
        `<rect x="${round(x)}" y="${round(y + 3)}" width="${size}" height="${size - 6}" fill="${fill}"${stroke}/>` +
        `<ellipse cx="${round(x + half)}" cy="${round(y + 3)}" rx="${half}" ry="3" fill="${fill}"${stroke}/>`
      );
    case "Circle":
    case "Ellipse":
      return `<circle cx="${round(x + half)}" cy="${round(y + half)}" r="${half}" fill="${fill}"${stroke}/>`;
    case "Hexagon": {
      const points = [
        [x + 3, y], [x + size - 3, y], [x + size, y + half],
        [x + size - 3, y + size], [x + 3, y + size], [x, y + half],
      ].map(([px, py]) => `${round(px)},${round(py)}`).join(" ");
      return `<polygon points="${points}" fill="${fill}"${stroke}/>`;
    }
    case "Box":
      return `<rect x="${round(x)}" y="${round(y)}" width="${size}" height="${size}" fill="${fill}"${stroke}/>`;
    default:
      return (
        `<rect x="${round(x)}" y="${round(y)}" width="${size}" height="${size}" ` +
        `rx="3" fill="${fill}"${stroke}/>`
      );
  }
}

/**
 * Lay the legend out in columns of at most LEGEND_MAX_ROWS, so a themed
 * deployment view with a dozen service styles grows sideways instead of
 * doubling the height of the image.
 */
function paintLegend(
  entries: LegendEntry[],
  x: number,
  y: number,
): { markup: string; width: number; height: number } {
  const labelWidth = LEGEND_COLUMN_WIDTH - LEGEND_SWATCH - 20;
  const labels = entries.map((entry) =>
    wrap(entry.label, labelWidth, LEGEND_LABEL_SIZE, LEGEND_MAX_LABEL_LINES),
  );
  const rows = Math.min(entries.length, LEGEND_MAX_ROWS);
  const columns = Math.ceil(entries.length / LEGEND_MAX_ROWS);
  const rowHeight = labels.some((lines) => lines.length > 1)
    ? LEGEND_ROW + LEGEND_LABEL_SIZE + 2
    : LEGEND_ROW;
  const width = columns * LEGEND_COLUMN_WIDTH + 2 * LEGEND_PAD;
  const height = rows * rowHeight + 2 * LEGEND_PAD;

  const parts = [
    `<rect x="${round(x)}" y="${round(y)}" width="${round(width)}" height="${round(height)}" ` +
      `rx="6" fill="#ffffff" stroke="${EDGE_LABEL_BORDER}"/>`,
  ];
  entries.forEach((entry, index) => {
    const column = Math.floor(index / LEGEND_MAX_ROWS);
    const row = index % LEGEND_MAX_ROWS;
    const cellX = x + LEGEND_PAD + column * LEGEND_COLUMN_WIDTH;
    const cellY = y + LEGEND_PAD + row * rowHeight;
    parts.push(legendSwatch(entry, cellX, cellY + 3));
    labels[index].forEach((line, lineIndex) => {
      parts.push(
        textLine(
          line,
          cellX + LEGEND_SWATCH + 8,
          cellY + LEGEND_SWATCH - 2 + lineIndex * (LEGEND_LABEL_SIZE + 2),
          LEGEND_LABEL_SIZE,
          LEGEND_LABEL_COLOUR,
          1,
          400,
          "start",
        ),
      );
    });
  });
  return { markup: parts.join(""), width, height };
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/** Build the React Flow nodes/edges the layout expects, as the SPA does. */
function toFlow(payload: GraphPayload): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = payload.nodes.map((n) => ({
    id: n.id,
    type: n.data.kind === "boundary" ? "boundary" : "element",
    position: n.position ?? { x: 0, y: 0 },
    data: n.data,
    ...(n.parentId ? { parentNode: n.parentId } : {}),
    ...(n.size ? { style: { width: n.size.width, height: n.size.height } } : {}),
  }));
  const edges: Edge[] = payload.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
  }));
  return { nodes, edges };
}

/**
 * Render a view's graph payload as a standalone SVG document.
 *
 * Positions come from the stored layout when the payload carries one and
 * from a fresh auto-layout otherwise — the same rule the SPA applies, via
 * the same code.
 */
export async function renderSvg(
  payload: GraphPayload,
  options: RenderOptions = {},
): Promise<string> {
  const padding = options.padding ?? 24;
  if (options.perspective) {
    payload = applyPerspective(payload, options.perspective);
  }
  const { nodes, edges } = toFlow(payload);

  const anyMissing = payload.nodes.some((n) => !n.position);
  const positioned = anyMissing
    ? await layoutGraph(nodes, edges, payload.rankDirection ?? "TB", {
        rankSeparation: payload.rankSeparation,
        nodeSeparation: payload.nodeSeparation,
      })
    : await normalizeStoredPositions(nodes, edges);

  const placed = place(positioned);
  const boxes = [...placed.values()];
  if (boxes.length === 0) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0"/>`;
  }

  const minX = Math.min(...boxes.map((b) => b.x));
  const minY = Math.min(...boxes.map((b) => b.y));
  const maxX = Math.max(...boxes.map((b) => b.x + b.width));
  const maxY = Math.max(...boxes.map((b) => b.y + b.height));
  const diagramWidth = maxX - minX;
  const diagramHeight = maxY - minY;

  // Title and legend sit outside the diagram bounds and extend the canvas,
  // so neither can overlap an element however dense the graph is.
  const title = options.title ?? "";
  const drawTitle = title !== "" && options.showTitle !== false;
  const titleHeight = drawTitle ? TITLE_SIZE + TITLE_GAP : 0;

  const entries = payload.legend ?? [];
  const drawLegend = entries.length > 0 && options.showLegend !== false;
  const legend = drawLegend
    ? paintLegend(entries, padding, padding + titleHeight + diagramHeight + LEGEND_GAP)
    : null;

  const width = round(
    Math.max(diagramWidth, legend ? legend.width : 0) + 2 * padding,
  );
  const height = round(
    titleHeight +
      diagramHeight +
      (legend ? LEGEND_GAP + legend.height : 0) +
      2 * padding,
  );
  const shift = `translate(${round(padding - minX)},${round(padding + titleHeight - minY)})`;

  // Boundaries first so they sit behind their children, then edges, then
  // the leaf nodes — the SPA's stacking order.
  const boundaries = boxes.filter((b) => b.isBoundary);
  const leaves = boxes.filter((b) => !b.isBoundary);

  const body = [
    ...boundaries.map(paintBoundary),
    ...payload.edges.map((edge) => paintEdge(edge, placed)),
    ...leaves.map(paintNode),
  ].join("");

  const heading = drawTitle
    ? textLine(
        title,
        padding,
        padding + TITLE_SIZE,
        TITLE_SIZE,
        TITLE_COLOUR,
        1,
        600,
        "start",
      )
    : "";

  const background =
    options.background === null
      ? ""
      : `<rect width="100%" height="100%" fill="${options.background ?? "#ffffff"}"/>`;
  const titleTag = title ? `<title>${escapeXml(title)}</title>` : "";

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" ` +
    `viewBox="0 0 ${width} ${height}" font-family="${FONT}">` +
    titleTag +
    `<defs>${arrowMarkerDefs(payload.edges)}</defs>` +
    background +
    heading +
    `<g transform="${shift}">${body}</g>` +
    (legend ? legend.markup : "") +
    `</svg>\n`
  );
}
