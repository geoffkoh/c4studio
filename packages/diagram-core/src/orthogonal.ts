// Orthogonal relationship routing, and re-routing by dragging a segment
// (PP-196).
//
// The model is the one a whiteboard elbow connector uses: a route is a
// polyline of axis-aligned segments, and dragging a segment slides it
// perpendicular to itself while its neighbours stretch. What is stored is
// the route's *interior* points — the existing `waypoints` — and the two
// ends are recomputed against the nodes on every render, so moving a node
// slides the attachment along its side instead of leaving a diagonal.
//
// Treating stored points as points the route must pass through matches
// upstream, whose JointJS `orthogonal` router does the same with a
// relationship's vertices.
//
// Pure and free of reactflow: `svg.ts` (the headless renderer) and the
// live edge component draw from this one implementation, which is what
// keeps `c4 render` matching the canvas.

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Pt {
  x: number;
  y: number;
}

/** A side of a node a route can be pinned to (PP-201). */
export type Side = "top" | "right" | "bottom" | "left";

/** Pinned sides of a route's two ends; an absent end floats. */
export interface Pins {
  source?: Side;
  target?: Side;
}

export const SIDES: readonly Side[] = ["top", "right", "bottom", "left"];

/** A maximal run of collinear segments: what one drag handle moves. */
export interface Run {
  /** Index of the run's first point in the route. */
  start: number;
  /** Index of the run's last point in the route. */
  end: number;
  /** `h`: the run is horizontal, so it drags vertically. */
  axis: "h" | "v";
}

const centre = (r: Rect): Pt => ({
  x: r.x + r.width / 2,
  y: r.y + r.height / 2,
});

const within = (value: number, from: number, to: number) =>
  value >= from && value <= to;

/** Midpoint of the gap between two non-overlapping spans. */
function gapMid(aFrom: number, aTo: number, bFrom: number, bTo: number): number {
  return aTo <= bFrom ? (aTo + bFrom) / 2 : (bTo + aFrom) / 2;
}

/**
 * The points from `r`'s border to (not including) `c`, every segment
 * axis-aligned. Beside the node, the route leaves the facing side at
 * `c`'s height; above or below, at `c`'s x; diagonally away, it leaves
 * from the side's centre and turns once.
 */
function connect(r: Rect, c: Pt): Pt[] {
  const right = r.x + r.width;
  const bottom = r.y + r.height;
  const besideX = !within(c.x, r.x, right);
  const besideY = !within(c.y, r.y, bottom);
  if (besideX && !besideY) return [{ x: c.x < r.x ? r.x : right, y: c.y }];
  if (besideY && !besideX) return [{ x: c.x, y: c.y < r.y ? r.y : bottom }];
  if (!besideX && !besideY) return [centre(r)];
  const mid = centre(r);
  return [
    { x: c.x < r.x ? r.x : right, y: mid.y },
    { x: c.x, y: mid.y },
  ];
}

/**
 * The route an unarranged relationship takes: a straight run where the
 * nodes face each other, otherwise a Z through the middle of the gap,
 * horizontal first when the nodes are further apart across than down.
 * `offset` fans out relationships that share a node pair, the job
 * `curveOffset` does for curves.
 */
function autoCorners(s: Rect, t: Rect, offset: number): Pt[] {
  const sc = centre(s);
  const tc = centre(t);
  const overlapX = Math.max(s.x, t.x) < Math.min(s.x + s.width, t.x + t.width);
  const overlapY =
    Math.max(s.y, t.y) < Math.min(s.y + s.height, t.y + t.height);
  if (overlapX && overlapY) return [];
  if (overlapY) {
    const y =
      (Math.max(s.y, t.y) + Math.min(s.y + s.height, t.y + t.height)) / 2;
    return [
      { x: gapMid(s.x, s.x + s.width, t.x, t.x + t.width), y: y + offset },
    ];
  }
  if (overlapX) {
    const x = (Math.max(s.x, t.x) + Math.min(s.x + s.width, t.x + t.width)) / 2;
    return [
      { x: x + offset, y: gapMid(s.y, s.y + s.height, t.y, t.y + t.height) },
    ];
  }
  if (Math.abs(tc.x - sc.x) >= Math.abs(tc.y - sc.y)) {
    const x = gapMid(s.x, s.x + s.width, t.x, t.x + t.width) + offset;
    return [
      { x, y: sc.y },
      { x, y: tc.y },
    ];
  }
  const y = gapMid(s.y, s.y + s.height, t.y, t.y + t.height) + offset;
  return [
    { x: sc.x, y },
    { x: tc.x, y },
  ];
}

/**
 * How far a route runs straight out of a pinned side before it may turn,
 * so the arrowhead (or the line's start) meets the side square-on.
 */
export const PIN_STUB = 20;

const vertical = (side: Side) => side === "top" || side === "bottom";

/** Whether `p` lies further out from the node than `from`, past `side`. */
function ahead(side: Side, from: Pt, p: Pt): boolean {
  switch (side) {
    case "top":
      return p.y < from.y;
    case "bottom":
      return p.y > from.y;
    case "left":
      return p.x < from.x;
    case "right":
      return p.x > from.x;
  }
}

/**
 * Where a route pinned to `side` of `r` meets it, and the end of its stub.
 * Along the side the attachment follows the route — it sits level with
 * `toward`, the next point the route visits — clamped clear of the
 * corners, so pinning a side never fixes the point on it.
 */
function pin(r: Rect, side: Side, toward: Pt): [Pt, Pt] {
  const clamp = (v: number, from: number, length: number) => {
    const margin = Math.min(12, length / 4);
    return Math.min(Math.max(v, from + margin), from + length - margin);
  };
  switch (side) {
    case "top": {
      const x = clamp(toward.x, r.x, r.width);
      return [
        { x, y: r.y },
        { x, y: r.y - PIN_STUB },
      ];
    }
    case "bottom": {
      const x = clamp(toward.x, r.x, r.width);
      return [
        { x, y: r.y + r.height },
        { x, y: r.y + r.height + PIN_STUB },
      ];
    }
    case "left": {
      const y = clamp(toward.y, r.y, r.height);
      return [
        { x: r.x, y },
        { x: r.x - PIN_STUB, y },
      ];
    }
    case "right": {
      const y = clamp(toward.y, r.y, r.height);
      return [
        { x: r.x + r.width, y },
        { x: r.x + r.width + PIN_STUB, y },
      ];
    }
  }
}

/**
 * The points between a pinned side's stub and `next`, every segment
 * axis-aligned. Ahead of the side, the route carries straight on and
 * turns once. Behind it, it goes round the node rather than through it:
 * sideways past the nearer corner, then on. Only a detour the node is
 * actually in the way of is taken.
 */
function leave(r: Rect, side: Side, stub: Pt, next: Pt): Pt[] {
  if (ahead(side, stub, next)) {
    if (vertical(side) ? stub.x === next.x : stub.y === next.y) return [];
    return vertical(side) ? [{ x: stub.x, y: next.y }] : [{ x: next.x, y: stub.y }];
  }
  if (vertical(side)) {
    const left = r.x - PIN_STUB;
    const right = r.x + r.width + PIN_STUB;
    if (next.x <= left || next.x >= right) return [{ x: next.x, y: stub.y }];
    const x = next.x < r.x + r.width / 2 ? left : right;
    return [
      { x, y: stub.y },
      { x, y: next.y },
    ];
  }
  const top = r.y - PIN_STUB;
  const bottom = r.y + r.height + PIN_STUB;
  if (next.y <= top || next.y >= bottom) return [{ x: stub.x, y: next.y }];
  const y = next.y < r.y + r.height / 2 ? top : bottom;
  return [
    { x: stub.x, y },
    { x: next.x, y },
  ];
}

function dedupe(points: Pt[]): Pt[] {
  return points.filter(
    (p, i) => i === 0 || p.x !== points[i - 1].x || p.y !== points[i - 1].y,
  );
}

/**
 * The full route from `source`'s border to `target`'s, through `bends`
 * (or an automatic route when there are none). Bends that do not share
 * an axis — free bend points placed in a curved style — get an elbow
 * between them, horizontal first, so the result is always orthogonal.
 */
export function orthogonalRoute(
  source: Rect,
  target: Rect,
  bends: readonly (readonly [number, number])[] = [],
  offset = 0,
  pins: Pins = {},
): Pt[] {
  const pinned = Boolean(pins.source || pins.target);
  const corners: Pt[] =
    bends.length > 0
      ? bends.map(([x, y]) => ({ x, y }))
      : pinned
        ? []
        : autoCorners(source, target, offset);
  if (pinned) return pinnedRoute(source, target, corners, pins);
  if (corners.length === 0) return [centre(source), centre(target)];

  const interior: Pt[] = [corners[0]];
  for (const c of corners.slice(1)) {
    const prev = interior[interior.length - 1];
    if (prev.x !== c.x && prev.y !== c.y) interior.push({ x: c.x, y: prev.y });
    interior.push(c);
  }
  const head = connect(source, interior[0]);
  const tail = connect(target, interior[interior.length - 1]).reverse();
  return dedupe([...head, ...interior, ...tail]);
}

/**
 * A route with one or both ends pinned to a side (PP-201): out of each
 * pinned side along its stub, through the corners, into the other end.
 * An unpinned end attaches as it always has, so pinning one end leaves
 * the other free.
 */
function pinnedRoute(source: Rect, target: Rect, corners: Pt[], pins: Pins): Pt[] {
  const chain: Pt[] = [];
  const push = (p: Pt) => {
    const prev = chain[chain.length - 1];
    if (prev && prev.x !== p.x && prev.y !== p.y) chain.push({ x: p.x, y: prev.y });
    chain.push(p);
  };
  const last = corners[corners.length - 1];
  const sourcePin = pins.source
    ? pin(source, pins.source, corners[0] ?? centre(target))
    : null;
  const targetPin = pins.target
    ? pin(target, pins.target, last ?? centre(source))
    : null;

  if (sourcePin && pins.source) {
    const toward = corners[0] ?? targetPin?.[1] ?? centre(target);
    chain.push(sourcePin[1], ...leave(source, pins.source, sourcePin[1], toward));
  }
  corners.forEach(push);
  if (targetPin && pins.target) {
    const from = chain[chain.length - 1] ?? centre(source);
    leave(target, pins.target, targetPin[1], from).reverse().forEach(push);
    push(targetPin[1]);
  }

  const head = sourcePin ? [sourcePin[0]] : connect(source, chain[0]);
  const tail = targetPin
    ? [targetPin[0]]
    : connect(target, chain[chain.length - 1]).reverse();
  return dedupe([...head, ...chain, ...tail]);
}

/**
 * The bends to store for a route: its interior points, less a pinned
 * end's stub (recomputed from the side, like the end itself), with any
 * point that no longer turns dropped. The first and last stored points
 * stay, because the ends are computed from them.
 */
export function routeBends(points: readonly Pt[], pins: Pins = {}): [number, number][] {
  const last = points.length - 1;
  const from = 1 + (pins.source ? 1 : 0);
  const to = last - (pins.target ? 1 : 0);
  const interior = dedupe(points.slice(from, Math.max(from, to)).map((p) => ({ ...p })));
  const kept = interior.filter((p, i) => {
    if (i === 0 || i === interior.length - 1) return true;
    const a = interior[i - 1];
    const b = interior[i + 1];
    return !((a.x === p.x && p.x === b.x) || (a.y === p.y && p.y === b.y));
  });
  return kept.map((p) => [Math.round(p.x), Math.round(p.y)]);
}

/**
 * Whether dragging `run` can change anything: it must hold a point that
 * is stored. A run made only of a node's attachment and a pinned stub
 * has none — both are recomputed — so it gets no handle.
 */
export function runIsDraggable(points: readonly Pt[], run: Run, pins: Pins = {}): boolean {
  const from = 1 + (pins.source ? 1 : 0);
  const to = points.length - 2 - (pins.target ? 1 : 0);
  return run.start <= to && run.end >= from;
}

/** Index (into `segmentRuns`) of the run nearest `p`, or -1. */
export function nearestRun(points: readonly Pt[], p: Pt): number {
  let best = -1;
  let bestDistance = Infinity;
  segmentRuns(points).forEach((run, index) => {
    const distance = segmentDistance(points[run.start], points[run.end], p);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });
  return best;
}

function segmentDistance(a: Pt, b: Pt, p: Pt): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = dx * dx + dy * dy;
  const t = length === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** How far a new step offsets the rest of its run, before it is dragged. */
export const STEP_SIZE = 24;

/**
 * Split `run` at `at` (an x for a horizontal run, a y for a vertical one)
 * into a step: the run up to `at`, a short jog, and the rest of the run
 * offset by `size`. Returns the bends to store, or `null` where a step
 * cannot go. The jog's two corners give the step two handles of its own,
 * and dragging it flat again removes it, because a corner that no longer
 * turns is not stored.
 *
 * A pinned end's stub is recomputed from its side, so a step is never put
 * on it: `at` is kept to the part of the run beyond the stub.
 */
export function insertStep(
  points: readonly Pt[],
  run: Run,
  at: number,
  pins: Pins = {},
  size = STEP_SIZE,
): [number, number][] | null {
  const horizontal = run.axis === "h";
  const along = (p: Pt) => (horizontal ? p.x : p.y);
  // Segments i (points[i] -> points[i + 1]) a step may split.
  const first = Math.max(run.start, pins.source ? 1 : 0);
  const last = Math.min(run.end - 1, points.length - 2 - (pins.target ? 1 : 0));
  if (first > last) return null;
  const ends = [along(points[first]), along(points[last + 1])];
  const value = Math.min(Math.max(at, Math.min(...ends)), Math.max(...ends));
  let split = first;
  for (let i = first; i <= last; i++) {
    const a = along(points[i]);
    const b = along(points[i + 1]);
    if (value >= Math.min(a, b) && value <= Math.max(a, b)) {
      split = i;
      break;
    }
  }
  const fixed = horizontal ? points[run.start].y : points[run.start].x;
  const shift = (p: Pt): Pt =>
    horizontal ? { x: p.x, y: p.y + size } : { x: p.x + size, y: p.y };
  const jog: Pt[] = horizontal
    ? [
        { x: value, y: fixed },
        { x: value, y: fixed + size },
      ]
    : [
        { x: fixed, y: value },
        { x: fixed + size, y: value },
      ];
  const moved = [
    ...points.slice(0, split + 1),
    ...jog,
    ...points.slice(split + 1).map((p, k) => (split + 1 + k <= run.end ? shift(p) : p)),
  ];
  return routeBends(moved, pins);
}

/** The side of `r` nearest `p`: where a dragged end snaps to. */
export function nearestSide(r: Rect, p: Pt): Side {
  const right = r.x + r.width;
  const bottom = r.y + r.height;
  const distances: Record<Side, number> = {
    top: segmentDistance({ x: r.x, y: r.y }, { x: right, y: r.y }, p),
    right: segmentDistance({ x: right, y: r.y }, { x: right, y: bottom }, p),
    bottom: segmentDistance({ x: r.x, y: bottom }, { x: right, y: bottom }, p),
    left: segmentDistance({ x: r.x, y: r.y }, { x: r.x, y: bottom }, p),
  };
  return SIDES.reduce((best, side) => (distances[side] < distances[best] ? side : best));
}

/** Group the route's segments into collinear runs, one handle each. */
export function segmentRuns(points: readonly Pt[]): Run[] {
  const runs: Run[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const axis = a.y === b.y ? "h" : a.x === b.x ? "v" : null;
    if (axis === null) continue;
    const last = runs[runs.length - 1];
    if (last && last.axis === axis && last.end === i) last.end = i + 1;
    else runs.push({ start: i, end: i + 1, axis });
  }
  return runs;
}

/**
 * Slide `run` to `value` (a y for a horizontal run, an x for a vertical
 * one) and return the bends to store. The route's two end points are
 * never stored — they are recomputed against the nodes — so a run that
 * touches a node moves only its interior points, and the attachment
 * follows along the node's side.
 *
 * A point that ends up collinear with both interior neighbours carries no
 * information, so it is dropped rather than left to accumulate over many
 * drags; the first and last interior points stay, because the ends are
 * computed from them.
 */
export function dragRun(
  points: readonly Pt[],
  run: Run,
  value: number,
  pins: Pins = {},
): [number, number][] {
  const moved = points.map((p) => ({ ...p }));
  const last = moved.length - 1;
  for (let i = run.start; i <= run.end; i++) {
    if (i === 0 || i === last) continue;
    if (run.axis === "h") moved[i].y = value;
    else moved[i].x = value;
  }
  return routeBends(moved, pins);
}

/**
 * SVG path data for a route; `radius` > 0 rounds each corner (the
 * Smooth step look), clamped so a short segment is never overshot.
 */
export function orthogonalPath(points: readonly Pt[], radius = 0): string {
  if (points.length === 0) return "";
  const parts = [`M ${points[0].x},${points[0].y}`];
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    const next = points[i + 1];
    const into = Math.hypot(cur.x - prev.x, cur.y - prev.y);
    const out = Math.hypot(next.x - cur.x, next.y - cur.y);
    const r = Math.min(radius, into / 2, out / 2);
    const straight =
      (prev.x === cur.x && cur.x === next.x) ||
      (prev.y === cur.y && cur.y === next.y);
    if (r <= 0 || straight) {
      parts.push(`L ${cur.x},${cur.y}`);
      continue;
    }
    const a = {
      x: cur.x - ((cur.x - prev.x) / into) * r,
      y: cur.y - ((cur.y - prev.y) / into) * r,
    };
    const b = {
      x: cur.x + ((next.x - cur.x) / out) * r,
      y: cur.y + ((next.y - cur.y) / out) * r,
    };
    parts.push(`L ${a.x},${a.y} Q ${cur.x},${cur.y} ${b.x},${b.y}`);
  }
  const end = points[points.length - 1];
  parts.push(`L ${end.x},${end.y}`);
  return parts.join(" ");
}

/** Index (into `segmentRuns`) of the longest run: where the label goes. */
export function labelRunIndex(points: readonly Pt[]): number {
  let best = -1;
  let bestLength = -1;
  segmentRuns(points).forEach((run, index) => {
    const a = points[run.start];
    const b = points[run.end];
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    if (length > bestLength) {
      bestLength = length;
      best = index;
    }
  });
  return best;
}

/** A label's box on the canvas, centred on (`x`, `y`). */
export interface LabelBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Clearance kept between a handle and a label, and a run's ends. */
const HANDLE_CLEARANCE = 8;

/**
 * Where a run's drag handle goes: its middle, unless a label covers that
 * — the label layer sits above the edges, so a covered handle could never
 * be grabbed. Then it moves just clear of the label, to whichever side is
 * nearer the middle and still on the run; with no room on either side it
 * stays in the middle, and the label can be dragged off the line.
 */
export function handlePoint(a: Pt, b: Pt, run: Run, label?: LabelBox): Pt {
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  if (!label) return mid;
  const horizontal = run.axis === "h";
  // Distance from the run's line to the label's centre, across the run.
  const across = horizontal ? Math.abs(label.y - a.y) : Math.abs(label.x - a.x);
  const halfAcross = (horizontal ? label.height : label.width) / 2;
  if (across > halfAcross + HANDLE_CLEARANCE) return mid;

  const along = horizontal ? label.x : label.y;
  const half = (horizontal ? label.width : label.height) / 2 + HANDLE_CLEARANCE;
  const from = Math.min(horizontal ? a.x : a.y, horizontal ? b.x : b.y);
  const to = Math.max(horizontal ? a.x : a.y, horizontal ? b.x : b.y);
  const centre = horizontal ? mid.x : mid.y;
  if (centre < along - half || centre > along + half) return mid;

  const candidates = [along - half, along + half]
    .filter((v) => v >= from + HANDLE_CLEARANCE && v <= to - HANDLE_CLEARANCE)
    .sort((p, q) => Math.abs(p - centre) - Math.abs(q - centre));
  if (candidates.length === 0) return mid;
  return horizontal ? { x: candidates[0], y: a.y } : { x: a.x, y: candidates[0] };
}

/** Where a label sits: the middle of the route's longest run. */
export function routeLabelPoint(points: readonly Pt[]): Pt {
  const run = segmentRuns(points)[labelRunIndex(points)];
  if (!run) return points[0] ?? { x: 0, y: 0 };
  const a = points[run.start];
  const b = points[run.end];
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}
