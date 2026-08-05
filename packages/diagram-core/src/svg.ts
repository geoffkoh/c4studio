/**
 * Headless SVG rendering.
 *
 * The SPA draws a diagram as HTML in a React Flow canvas; `export.ts`
 * rasterises that live canvas with html-to-image, which needs a browser.
 * This module draws the same diagram as pure SVG markup from the graph
 * payload alone, so `pystructurizr render` works in CI, in a Forge
 * resolver, or anywhere else with no DOM.
 *
 * Layout is the *same* code the SPA runs (`layout.ts`), so node positions
 * are identical rather than merely similar. What is re-implemented here is
 * only the painting: the CSS in `index.css` and the JSX in the node and
 * edge components, expressed as SVG.
 *
 * Deliberately self-contained: no external fonts, stylesheets or images,
 * so an exported file renders the same wherever it is opened.
 */

import type { Edge, Node } from "reactflow";

import { layoutGraph, normalizeStoredPositions, type RankDirection } from "./layout";

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
    showMetadata?: boolean;
  };
}

export interface GraphPayloadEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  waypoints?: [number, number][];
}

export interface GraphPayload {
  nodes: GraphPayloadNode[];
  edges: GraphPayloadEdge[];
  rankDirection?: RankDirection;
}

export interface RenderOptions {
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
const NODE_PAD_X = 12;
const NODE_PAD_TOP = 10;
const PERSON_PAD_TOP = 20;
const PERSON_HEAD = 38;

const LABEL_SIZE = 13;
const LABEL_LEADING = 16;
const SMALL_SIZE = 10;
const SMALL_LEADING = 13;
const META_GAP = 3;
const DESC_GAP = 5;
const DESC_MAX_LINES = 3;
const LABEL_MAX_LINES = 3;

const NODE_STROKE = "rgba(0,0,0,0.12)";
const FALLBACK_FILL = "#78909c";
const TEXT_COLOUR = "#ffffff";

const BOUNDARY_STROKE = "#90a4ae";
const BOUNDARY_FILL = "rgba(144,164,174,0.07)";
const BOUNDARY_RADIUS = 10;
// `.boundary__label`: bottom-left, the type italicised beside the name.
const BOUNDARY_LABEL_SIZE = 12;
const BOUNDARY_LABEL_COLOUR = "#546e7a";

const EDGE_COLOUR = "#b1b1b7";
const EDGE_WIDTH = 1;
const ARROW = 10;
const EDGE_LABEL_SIZE = 10;
const EDGE_LABEL_COLOUR = "#6b7684"; // --muted
const EDGE_LABEL_BG = "rgba(255,255,255,0.92)";
const EDGE_LABEL_BORDER = "#e2e5ea"; // --border

/**
 * Character width as a fraction of font size, for wrapping without a DOM.
 * Measured against the SPA's font stack; erring high keeps text inside the
 * box rather than overflowing it.
 */
const CHAR_RATIO = 0.55;
const BOLD_CHAR_RATIO = 0.58;

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

/** Greedy word wrap to a pixel width, using the estimated character width. */
function wrap(
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
  // A clipped final line ends in an ellipsis, as the CSS line clamp does.
  const consumed = lines.join(" ").replace(/…$/, "");
  if (consumed.length < text.replace(/\s+/g, " ").trim().length && lines.length) {
    const last = lines[lines.length - 1];
    if (!last.endsWith("…")) {
      lines[lines.length - 1] = `${last.slice(0, Math.max(0, limit - 1))}…`;
    }
  }
  return lines;
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
    const isPerson =
      !isBoundary &&
      (data.shape === "Person" ||
        data.shape === "Robot" ||
        (data.shape === undefined && (data.kind ?? "").startsWith("person")));
    placed.set(node.id, {
      id: node.id,
      x,
      y,
      width: Number(node.style?.width ?? 200),
      height: Number(node.style?.height ?? (isPerson ? 150 : 110)),
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

/** The box outline, honouring the Structurizr shape where SVG can. */
function shapeMarkup(node: Placed, fill: string): string {
  const { x, y, width, height } = node;
  const stroke = ` fill="${fill}" stroke="${NODE_STROKE}" stroke-width="1"`;
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

/** `[Kind: Technology]`, unless an element style suppressed it. */
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
};

function metaLine(data: GraphPayloadNode["data"]): string | null {
  if (data.showMetadata === false) return null;
  const kind = KIND_LABELS[data.kind ?? ""] ?? data.kind ?? "";
  if (!kind) return null;
  return data.technology ? `[${kind}: ${data.technology}]` : `[${kind}]`;
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
        `r="${PERSON_HEAD / 2}" fill="${fill}" stroke="${NODE_STROKE}" stroke-width="1"/>`,
    );
  }
  parts.push(shapeMarkup(body, fill));

  const centreX = node.x + node.width / 2;
  const innerWidth = node.width - 2 * NODE_PAD_X;
  let cursor =
    body.y + (node.isPerson ? PERSON_PAD_TOP : NODE_PAD_TOP) + LABEL_SIZE;

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
    const [line] = wrap(meta, innerWidth, SMALL_SIZE, 1);
    if (line) {
      parts.push(textLine(line, centreX, cursor, SMALL_SIZE, colour, 0.85));
      cursor += SMALL_LEADING;
    }
  }

  if (node.data.description) {
    cursor += DESC_GAP - SMALL_LEADING + SMALL_SIZE;
    const room = Math.max(
      0,
      Math.floor((body.y + body.height - 6 - cursor) / SMALL_LEADING) + 1,
    );
    for (const line of wrap(
      node.data.description,
      innerWidth,
      SMALL_SIZE,
      Math.min(DESC_MAX_LINES, room),
    )) {
      parts.push(textLine(line, centreX, cursor, SMALL_SIZE, colour, 0.8));
      cursor += SMALL_LEADING;
    }
  }

  return parts.join("");
}

function paintBoundary(node: Placed): string {
  const label = escapeXml(node.data.label ?? "");
  const meta = node.data.boundaryLabel;
  const type = meta
    ? `<tspan font-weight="400" font-style="italic" opacity="0.85"> [${escapeXml(meta)}]</tspan>`
    : "";
  return (
    `<rect x="${round(node.x)}" y="${round(node.y)}" width="${round(node.width)}" ` +
    `height="${round(node.height)}" rx="${BOUNDARY_RADIUS}" ry="${BOUNDARY_RADIUS}" ` +
    `fill="${BOUNDARY_FILL}" stroke="${BOUNDARY_STROKE}" stroke-width="2" ` +
    `stroke-dasharray="6 4"/>` +
    `<text x="${round(node.x + 12)}" y="${round(node.y + node.height - 9)}" ` +
    `font-family="${FONT}" font-size="${BOUNDARY_LABEL_SIZE}" font-weight="600" ` +
    `fill="${BOUNDARY_LABEL_COLOUR}">${label}${type}</text>`
  );
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

  const path =
    `<path d="${d}" fill="none" stroke="${EDGE_COLOUR}" ` +
    `stroke-width="${EDGE_WIDTH}" marker-end="url(#arrow)"/>`;

  if (!edge.label) return path;

  // Label sits at the middle of the routed line, in a small plate.
  const mid = points[Math.floor((points.length - 1) / 2)];
  const next = points[Math.floor((points.length - 1) / 2) + 1] ?? mid;
  const cx = (mid.x + next.x) / 2;
  const cy = (mid.y + next.y) / 2;
  const [line] = wrap(edge.label, 220, EDGE_LABEL_SIZE, 1);
  const width = line.length * EDGE_LABEL_SIZE * CHAR_RATIO + 10;
  return (
    path +
    `<rect x="${round(cx - width / 2)}" y="${round(cy - 8)}" width="${round(width)}" ` +
    `height="16" rx="4" ry="4" fill="${EDGE_LABEL_BG}" stroke="${EDGE_LABEL_BORDER}"/>` +
    textLine(line, cx, cy + 3.5, EDGE_LABEL_SIZE, EDGE_LABEL_COLOUR)
  );
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
  const { nodes, edges } = toFlow(payload);

  const anyMissing = payload.nodes.some((n) => !n.position);
  const positioned = anyMissing
    ? await layoutGraph(nodes, edges, payload.rankDirection ?? "TB")
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
  const width = round(maxX - minX + 2 * padding);
  const height = round(maxY - minY + 2 * padding);
  const shift = `translate(${round(padding - minX)},${round(padding - minY)})`;

  // Boundaries first so they sit behind their children, then edges, then
  // the leaf nodes — the SPA's stacking order.
  const boundaries = boxes.filter((b) => b.isBoundary);
  const leaves = boxes.filter((b) => !b.isBoundary);

  const body = [
    ...boundaries.map(paintBoundary),
    ...payload.edges.map((edge) => paintEdge(edge, placed)),
    ...leaves.map(paintNode),
  ].join("");

  const background =
    options.background === null
      ? ""
      : `<rect width="100%" height="100%" fill="${options.background ?? "#ffffff"}"/>`;
  const title = options.title
    ? `<title>${escapeXml(options.title)}</title>`
    : "";

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" ` +
    `viewBox="0 0 ${width} ${height}" font-family="${FONT}">` +
    title +
    `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" ` +
    `markerWidth="${ARROW}" markerHeight="${ARROW}" markerUnits="userSpaceOnUse" ` +
    `orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="${EDGE_COLOUR}"/>` +
    `</marker></defs>` +
    background +
    `<g transform="${shift}">${body}</g>` +
    `</svg>\n`
  );
}
