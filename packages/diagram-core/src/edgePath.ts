// The shape of one relationship line, for both renderers (PP-222).
//
// The canvas's edge component and `svg.ts` (the headless renderer behind
// `c4 render`) both draw from `edgeGeometry`, so a line style chosen in the
// Studio is drawn the same everywhere. Before, `c4 render` had no line
// style at all: it drew straight lines, step lines only for re-routed
// edges, and ignored the offset that keeps two lines between the same pair
// of elements apart.
//
// Pure and free of reactflow at runtime, for the same reason as
// `orthogonal.ts`: the Node renderer bundles this module.

import {
  orthogonalPath,
  orthogonalRoute,
  routeLabelPoint,
  type Pins,
  type Pt,
  type Rect,
} from "./orthogonal";

/** The toolbar's line styles, as the layout sidecar stores them. */
export type LineStyle = "bezier" | "straight" | "step" | "smoothstep";

export const LINE_STYLES: readonly LineStyle[] = [
  "bezier",
  "straight",
  "step",
  "smoothstep",
];

/** A stored value as a line style: `"default"` is what browsers kept
    before the style had a name of its own, and meant Bezier. */
export function asLineStyle(raw: unknown): LineStyle | undefined {
  if (raw === "default") return "bezier";
  return LINE_STYLES.find((style) => style === raw);
}

/** Corner radius of a Smooth step route; Step's corners are square. */
const SMOOTH_STEP_RADIUS = 8;

/** Gap between parallel lines joining the same two elements. */
const CURVE_GAP = 48;

/**
 * The perpendicular offset for each edge that shares its two elements with
 * another, keyed by edge id. Sign-normalised to the canonical pair order,
 * so opposite directions bow to opposite sides; the middle edge of an
 * odd-sized group keeps the centre line. An edge alone between its pair
 * has no entry.
 */
export function curveOffsets(
  edges: readonly { id: string; source: string; target: string }[],
): Map<string, number> {
  const pairKey = (e: { source: string; target: string }) =>
    [e.source, e.target].sort().join("|");
  const counts = new Map<string, number>();
  for (const e of edges) counts.set(pairKey(e), (counts.get(pairKey(e)) ?? 0) + 1);
  const seen = new Map<string, number>();
  const offsets = new Map<string, number>();
  for (const e of edges) {
    const key = pairKey(e);
    const total = counts.get(key) ?? 1;
    if (total < 2) continue;
    const index = seen.get(key) ?? 0;
    seen.set(key, index + 1);
    const canonical = e.source <= e.target ? 1 : -1;
    offsets.set(e.id, (index - (total - 1) / 2) * CURVE_GAP * canonical);
  }
  return offsets;
}

const centre = (r: Rect): Pt => ({ x: r.x + r.width / 2, y: r.y + r.height / 2 });

/**
 * Where the line from `r`'s centre towards `aimAt` crosses its border:
 * edges aim at centres (or a curve's control point) while arrowheads still
 * start and stop at the box.
 */
export function borderIntersection(r: Rect, aimAt: Pt): Pt {
  const w = r.width / 2;
  const h = r.height / 2;
  const c = centre(r);
  const dx = (aimAt.x - c.x) / (2 * w) || 0;
  const dy = (aimAt.y - c.y) / (2 * h) || 0;
  const scale = 1 / Math.max(Math.abs(dx), Math.abs(dy)) || 1;
  return { x: c.x + dx * scale * w, y: c.y + dy * scale * h };
}

type Side = "left" | "right" | "top" | "bottom";

function sideOf(r: Rect, p: Pt): Side {
  if (p.x <= r.x + 1) return "left";
  if (p.x >= r.x + r.width - 1) return "right";
  if (p.y <= r.y + 1) return "top";
  return "bottom";
}

// React Flow 11's getBezierPath, copied rather than imported so the Node
// renderer does not bundle reactflow. Same curvature (0.25), same control
// points, same label point, so the canvas and `c4 render` agree.
function controlOffset(distance: number, curvature: number): number {
  return distance >= 0 ? 0.5 * distance : curvature * 25 * Math.sqrt(-distance);
}

function control(side: Side, from: Pt, to: Pt, curvature: number): Pt {
  switch (side) {
    case "left":
      return { x: from.x - controlOffset(from.x - to.x, curvature), y: from.y };
    case "right":
      return { x: from.x + controlOffset(to.x - from.x, curvature), y: from.y };
    case "top":
      return { x: from.x, y: from.y - controlOffset(from.y - to.y, curvature) };
    case "bottom":
      return { x: from.x, y: from.y + controlOffset(to.y - from.y, curvature) };
  }
}

function bezier(s: Pt, sSide: Side, t: Pt, tSide: Side): EdgeGeometry {
  const sc = control(sSide, s, t, 0.25);
  const tc = control(tSide, t, s, 0.25);
  return {
    path: `M${s.x},${s.y} C${sc.x},${sc.y} ${tc.x},${tc.y} ${t.x},${t.y}`,
    labelX: s.x * 0.125 + sc.x * 0.375 + tc.x * 0.375 + t.x * 0.125,
    labelY: s.y * 0.125 + sc.y * 0.375 + tc.y * 0.375 + t.y * 0.125,
    orthogonal: false,
    route: [],
  };
}

export interface EdgeGeometryInput {
  source: Rect;
  target: Rect;
  lineStyle?: LineStyle;
  /** Saved bend points; with a route, its corners. */
  waypoints?: readonly (readonly [number, number])[];
  /** From `curveOffsets`, for a line sharing its pair. */
  curveOffset?: number;
  /** Re-routed by dragging (PP-196), from the sidecar. */
  routing?: string;
  /** A relationship style's `routing Orthogonal` (PP-209). */
  styleRouting?: string;
  /** Ends pinned to a side (PP-201). */
  sides?: Pins;
}

export interface EdgeGeometry {
  /** SVG path data. */
  path: string;
  /** Where the label is centred, before any dragged offset. */
  labelX: number;
  labelY: number;
  /** Drawn as an orthogonal route, whose runs the canvas lets you drag. */
  orthogonal: boolean;
  /** The orthogonal route's points; empty otherwise. */
  route: Pt[];
}

/**
 * The line between two boxes, as the chosen style draws it.
 *
 * A Step or Smooth step style, a re-routed edge and a `routing Orthogonal`
 * style all draw an orthogonal route. Otherwise saved bend points give
 * straight runs through them, a parallel line bows through an offset
 * control point, and the rest is a Bezier or a straight line.
 */
export function edgeGeometry(input: EdgeGeometryInput): EdgeGeometry {
  const { source, target } = input;
  const lineStyle = input.lineStyle ?? "bezier";
  const bends = input.waypoints ?? [];
  const curveOffset = input.curveOffset ?? 0;

  const orthogonal =
    input.routing === "orthogonal" ||
    input.styleRouting === "orthogonal" ||
    lineStyle === "step" ||
    lineStyle === "smoothstep";
  if (orthogonal) {
    const route = orthogonalRoute(source, target, bends, curveOffset, input.sides ?? {});
    const at = routeLabelPoint(route);
    return {
      path: orthogonalPath(route, lineStyle === "smoothstep" ? SMOOTH_STEP_RADIUS : 0),
      labelX: at.x,
      labelY: at.y,
      orthogonal: true,
      route,
    };
  }

  if (bends.length > 0) {
    // Straight runs through every bend, clipped to the boxes at each end.
    const first = { x: bends[0][0], y: bends[0][1] };
    const last = { x: bends[bends.length - 1][0], y: bends[bends.length - 1][1] };
    const points = [
      borderIntersection(source, first),
      ...bends.map(([x, y]) => ({ x, y })),
      borderIntersection(target, last),
    ];
    // The label at the middle of the longest run: never on a bend, and
    // where there is most room for the text.
    let longest = 0;
    let longestLength = -1;
    for (let i = 0; i < points.length - 1; i += 1) {
      const length = Math.hypot(points[i + 1].x - points[i].x, points[i + 1].y - points[i].y);
      if (length > longestLength) {
        longestLength = length;
        longest = i;
      }
    }
    return {
      path: points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x},${p.y}`).join(" "),
      labelX: (points[longest].x + points[longest + 1].x) / 2,
      labelY: (points[longest].y + points[longest + 1].y) / 2,
      orthogonal: false,
      route: [],
    };
  }

  const sourceCentre = centre(source);
  const targetCentre = centre(target);
  if (curveOffset !== 0) {
    // Aim both ends at a control point perpendicular to the centre line,
    // and draw the quadratic through it; the label sits on its apex,
    // Q(0.5) = 0.25·S + 0.5·C + 0.25·T.
    const dx = targetCentre.x - sourceCentre.x;
    const dy = targetCentre.y - sourceCentre.y;
    const length = Math.hypot(dx, dy) || 1;
    const c = {
      x: (sourceCentre.x + targetCentre.x) / 2 + (-dy / length) * curveOffset,
      y: (sourceCentre.y + targetCentre.y) / 2 + (dx / length) * curveOffset,
    };
    const s = borderIntersection(source, c);
    const t = borderIntersection(target, c);
    return {
      path: `M ${s.x},${s.y} Q ${c.x},${c.y} ${t.x},${t.y}`,
      labelX: 0.25 * s.x + 0.5 * c.x + 0.25 * t.x,
      labelY: 0.25 * s.y + 0.5 * c.y + 0.25 * t.y,
      orthogonal: false,
      route: [],
    };
  }

  const s = borderIntersection(source, targetCentre);
  const t = borderIntersection(target, sourceCentre);
  if (lineStyle === "straight") {
    return {
      path: `M ${s.x},${s.y}L ${t.x},${t.y}`,
      labelX: (s.x + t.x) / 2,
      labelY: (s.y + t.y) / 2,
      orthogonal: false,
      route: [],
    };
  }
  return bezier(s, sideOf(source, s), t, sideOf(target, t));
}
