/**
 * Alignment, distribution and nudging for a multi-selection.
 *
 * Deliberately pure: these take plain boxes and return the positions that
 * changed, with no React Flow types, no DOM and no persistence. That keeps
 * the geometry unit-testable the moment this package gains a test runner,
 * and keeps `GraphPane` to wiring.
 *
 * Everything works in **absolute** coordinates. Nodes nested inside a
 * boundary carry positions relative to their parent, so aligning them on
 * their raw `position` would line them up inside their own parents while
 * leaving them visually scattered. Callers convert in and out.
 */

export type AlignMode =
  | "left"
  | "center"
  | "right"
  | "top"
  | "middle"
  | "bottom";

export type DistributeMode = "horizontal" | "vertical";

export interface Box {
  id: string;
  /** Absolute position of the box's top-left corner. */
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Absolute positions that changed, keyed by node id. */
export type Moves = Record<string, { x: number; y: number }>;

const round = (n: number): number => Math.round(n);

/**
 * Align boxes to the outermost edge (or the centre) of the selection.
 *
 * Edges align to the extreme of the whole selection rather than to the
 * first-selected box: that matches every drawing tool, and it means the
 * result does not depend on click order.
 */
export function align(boxes: Box[], mode: AlignMode): Moves {
  if (boxes.length < 2) return {};
  const moves: Moves = {};

  const left = Math.min(...boxes.map((b) => b.x));
  const right = Math.max(...boxes.map((b) => b.x + b.width));
  const top = Math.min(...boxes.map((b) => b.y));
  const bottom = Math.max(...boxes.map((b) => b.y + b.height));
  const centerX = (left + right) / 2;
  const centerY = (top + bottom) / 2;

  for (const box of boxes) {
    let { x, y } = box;
    switch (mode) {
      case "left":
        x = left;
        break;
      case "right":
        x = right - box.width;
        break;
      case "center":
        x = centerX - box.width / 2;
        break;
      case "top":
        y = top;
        break;
      case "bottom":
        y = bottom - box.height;
        break;
      case "middle":
        y = centerY - box.height / 2;
        break;
    }
    if (round(x) !== round(box.x) || round(y) !== round(box.y)) {
      moves[box.id] = { x: round(x), y: round(y) };
    }
  }
  return moves;
}

/**
 * Space boxes evenly, keeping the two outermost where they are.
 *
 * Gaps are equalised rather than centres, so boxes of different sizes end
 * up with even whitespace between them — which is what looks right on a
 * diagram where a person node is taller than a container.
 */
export function distribute(boxes: Box[], mode: DistributeMode): Moves {
  if (boxes.length < 3) return {};
  const horizontal = mode === "horizontal";
  const sorted = [...boxes].sort((a, b) =>
    horizontal ? a.x - b.x : a.y - b.y,
  );

  const start = horizontal ? sorted[0].x : sorted[0].y;
  const last = sorted[sorted.length - 1];
  const end = horizontal ? last.x + last.width : last.y + last.height;
  const totalSize = sorted.reduce(
    (sum, b) => sum + (horizontal ? b.width : b.height),
    0,
  );
  const gap = (end - start - totalSize) / (sorted.length - 1);

  const moves: Moves = {};
  let cursor = start;
  for (const box of sorted) {
    const target = round(cursor);
    const current = horizontal ? box.x : box.y;
    if (round(current) !== target) {
      moves[box.id] = horizontal
        ? { x: target, y: round(box.y) }
        : { x: round(box.x), y: target };
    }
    cursor += (horizontal ? box.width : box.height) + gap;
  }
  return moves;
}

/** Shift every box by the same delta — the arrow-key nudge. */
export function nudge(boxes: Box[], dx: number, dy: number): Moves {
  const moves: Moves = {};
  for (const box of boxes) {
    moves[box.id] = { x: round(box.x + dx), y: round(box.y + dy) };
  }
  return moves;
}
