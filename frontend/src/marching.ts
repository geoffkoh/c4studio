// Marching-ants emphasis for the relationships of a hovered node (PP-195).
//
// Pure, so the selection rule can be exercised without a canvas: which
// edges march is a question about the node tree, not about rendering.

import { EDGE_WIDTH, edgeDashArray } from "@c4studio/diagram-core";

interface TreeNode {
  id: string;
  parentNode?: string;
}

interface Link {
  id: string;
  source: string;
  target: string;
}

/**
 * Ids of the edges that should march while `hovered` is under the pointer:
 * every edge touching the node or anything nested inside it. A boundary
 * (an expanded container, a group, a deployment node) owns its children's
 * relationships, which is the same containment rule the views apply when
 * they lift an edge to the nearest visible ancestor.
 */
export function marchingEdgeIds(
  nodes: readonly TreeNode[],
  edges: readonly Link[],
  hovered: string | null,
): Set<string> {
  const marching = new Set<string>();
  if (hovered === null) return marching;

  const parentOf = new Map(nodes.map((n) => [n.id, n.parentNode]));
  const within = (id: string): boolean => {
    // Bounded by the node count so a malformed cycle cannot hang the UI.
    let current: string | undefined = id;
    for (let depth = 0; current !== undefined && depth <= nodes.length; depth++) {
      if (current === hovered) return true;
      current = parentOf.get(current);
    }
    return false;
  };

  for (const edge of edges) {
    if (within(edge.source) || within(edge.target)) marching.add(edge.id);
  }
  return marching;
}

/**
 * The stroke style a marching edge needs: its own dash pattern, or the
 * default dash for a solid line (a solid line has nothing to march), plus
 * the pattern's length as `--march-period` so the keyframes loop exactly
 * one repeat and the animation never visibly jumps.
 */
export function marchingStyle(
  style: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const width =
    typeof style?.strokeWidth === "number" ? style.strokeWidth : EDGE_WIDTH;
  const dash =
    typeof style?.strokeDasharray === "string" && style.strokeDasharray
      ? style.strokeDasharray
      : (edgeDashArray(width, "dashed") ?? "");
  const period = dash
    .split(/[\s,]+/)
    .map(Number)
    .filter((n) => Number.isFinite(n))
    .reduce((sum, n) => sum + n, 0);
  return {
    ...style,
    strokeDasharray: dash,
    "--march-period": `${period}px`,
    // Constant speed whatever the line weight: a thick line has a longer
    // pattern, so it gets proportionally longer to travel it.
    "--march-duration": `${(period / 32).toFixed(3)}s`,
  };
}
