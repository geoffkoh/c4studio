// Auto-layout for graphs whose nodes arrive without stored positions.
//
// Boundary (group) nodes make this a compound layout, which plain dagre does
// not support. It is computed recursively, bottom-up: each group lays out its
// children (sizing itself to their bounding box plus padding and label
// space), then participates in its own parent's layout as a single large
// node. Edges crossing group borders are lifted to the ancestor that lives
// at the level being laid out. Groups nest to any depth (deployment views,
// expanded containers).

import dagre from "dagre";
import type { Edge, Node } from "reactflow";

const NODE_WIDTH = 200;
const NODE_HEIGHT = 110;
const PERSON_HEIGHT = 150;

// Space between a boundary edge and its children; the bottom pad leaves
// room for the boundary label.
const BOUNDARY_PAD_X = 28;
const BOUNDARY_PAD_TOP = 28;
const BOUNDARY_PAD_BOTTOM = 56;

interface Size {
  width: number;
  height: number;
}

interface Point {
  x: number;
  y: number;
}

function nodeSize(node: Node): Size {
  const kind = (node.data as { kind?: string } | undefined)?.kind ?? "";
  if (kind.startsWith("person")) {
    return { width: NODE_WIDTH, height: PERSON_HEIGHT };
  }
  return { width: NODE_WIDTH, height: NODE_HEIGHT };
}

/**
 * Run dagre over one level of the graph and return top-left positions.
 *
 * dagre positions nodes by their centre; React Flow positions by the
 * top-left corner, so we offset by half of each node's size.
 */
export type RankDirection = "TB" | "BT" | "LR" | "RL";

function dagreLevel(
  items: { id: string; size: Size }[],
  edges: { source: string; target: string }[],
  direction: RankDirection,
): Map<string, Point> {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 90 });

  for (const item of items) {
    g.setNode(item.id, { ...item.size });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const positions = new Map<string, Point>();
  for (const item of items) {
    const pos = g.node(item.id);
    positions.set(item.id, {
      x: pos.x - item.size.width / 2,
      y: pos.y - item.size.height / 2,
    });
  }
  return positions;
}

/** Parent/child indices over the node list. */
function buildHierarchy(nodes: Node[]) {
  const parentOf = new Map<string, string>();
  const childrenOf = new Map<string | undefined, Node[]>();
  for (const node of nodes) {
    if (node.parentNode) parentOf.set(node.id, node.parentNode);
    const key = node.parentNode ?? undefined;
    const siblings = childrenOf.get(key) ?? [];
    siblings.push(node);
    childrenOf.set(key, siblings);
  }
  return { parentOf, childrenOf };
}

/**
 * The ancestor of `id` that is a direct child of `parentId`, or undefined
 * when `id` does not live under `parentId` at all.
 */
function ancestorAtLevel(
  id: string,
  parentId: string | undefined,
  parentOf: Map<string, string>,
): string | undefined {
  let current: string | undefined = id;
  while (current !== undefined) {
    const parent = parentOf.get(current);
    if (parent === parentId || (parent === undefined && parentId === undefined)) {
      return current;
    }
    current = parent;
  }
  return undefined;
}

/**
 * Assign positions to all nodes, sizing boundary group nodes (at any
 * nesting depth) to fit their children. Child positions are relative to
 * their parent, as React Flow expects for nested nodes.
 *
 * **Async by contract, synchronous by implementation.** dagre computes
 * this inline, but every caller awaits, so an engine with an asynchronous
 * API (elkjs) can replace this without touching a single call site — see
 * the layout-engine decision in `docs/roadmap.md`.
 *
 * Still on `dagre@0.8.5` deliberately. The maintained `@dagrejs/dagre`
 * fork is not coordinate-compatible: it breaks cycles differently, which
 * re-ranks nodes on cyclic graphs (PP-92 measured a Person moving from the
 * top to the bottom of a context diagram). Changing engine is a layout
 * decision to take on its own merits, not a side effect of a dependency
 * upgrade.
 */
export async function layoutGraph(
  nodes: Node[],
  edges: Edge[],
  direction: RankDirection = "TB",
): Promise<Node[]> {
  const { parentOf, childrenOf } = buildHierarchy(nodes);
  const positions = new Map<string, Point>();
  const groupSizes = new Map<string, Size>();

  const sizeOf = (node: Node): Size => groupSizes.get(node.id) ?? nodeSize(node);

  function edgesAtLevel(
    parentId: string | undefined,
  ): { source: string; target: string }[] {
    const seen = new Set<string>();
    const lifted: { source: string; target: string }[] = [];
    for (const edge of edges) {
      const source = ancestorAtLevel(edge.source, parentId, parentOf);
      const target = ancestorAtLevel(edge.target, parentId, parentOf);
      if (!source || !target || source === target) continue;
      const key = `${source}->${target}`;
      if (seen.has(key)) continue;
      seen.add(key);
      lifted.push({ source, target });
    }
    return lifted;
  }

  /** Lay out the children of `parentId`; returns the resulting group size. */
  function layoutLevel(parentId: string | undefined): Size {
    const children = childrenOf.get(parentId) ?? [];
    // Bottom-up: size nested groups before laying out this level.
    for (const child of children) {
      if (childrenOf.has(child.id)) {
        groupSizes.set(child.id, layoutLevel(child.id));
      }
    }

    const laidOut = dagreLevel(
      children.map((c) => ({ id: c.id, size: sizeOf(c) })),
      edgesAtLevel(parentId),
      direction,
    );

    let maxX = 0;
    let maxY = 0;
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    for (const child of children) {
      const pos = laidOut.get(child.id)!;
      const size = sizeOf(child);
      minX = Math.min(minX, pos.x);
      minY = Math.min(minY, pos.y);
      maxX = Math.max(maxX, pos.x + size.width);
      maxY = Math.max(maxY, pos.y + size.height);
    }
    if (children.length === 0) {
      minX = minY = maxX = maxY = 0;
    }

    // Top level keeps dagre's coordinates; nested levels shift into the
    // parent's padded interior.
    const offsetX = parentId === undefined ? 0 : BOUNDARY_PAD_X - minX;
    const offsetY = parentId === undefined ? 0 : BOUNDARY_PAD_TOP - minY;
    for (const child of children) {
      const pos = laidOut.get(child.id)!;
      positions.set(child.id, { x: pos.x + offsetX, y: pos.y + offsetY });
    }

    return {
      width: maxX - minX + 2 * BOUNDARY_PAD_X,
      height: maxY - minY + BOUNDARY_PAD_TOP + BOUNDARY_PAD_BOTTOM,
    };
  }

  layoutLevel(undefined);

  return nodes.map((node) => {
    const size = groupSizes.get(node.id);
    return {
      ...node,
      position: positions.get(node.id) ?? { x: 0, y: 0 },
      ...(size ? { style: { ...node.style, ...size } } : {}),
    };
  });
}

/**
 * Adapt stored (absolute) positions to React Flow's nested-node model.
 *
 * Stored layouts predate boundaries and are absolute; children of a
 * boundary must be positioned relative to it. Groups are re-derived from
 * their children's bounding boxes. Multi-level nesting (deployment views)
 * has no stored layouts in practice, so only one level is handled; deeper
 * graphs fall back to a fresh auto-layout — which is why this is async
 * too, despite doing no asynchronous work of its own.
 */
export async function normalizeStoredPositions(
  nodes: Node[],
  edges: Edge[],
): Promise<Node[]> {
  const { parentOf, childrenOf } = buildHierarchy(nodes);
  const multiLevel = nodes.some((n) => {
    const parent = n.parentNode;
    return parent !== undefined && parentOf.has(parent);
  });
  if (multiLevel) return await layoutGraph(nodes, edges);

  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const groups = new Map<string, { position: Point; size: Size }>();
  for (const [parentId, children] of childrenOf) {
    if (parentId === undefined) continue;
    // A user-resized boundary carries its stored geometry; honour it and
    // only fall back to the children's bounding box otherwise.
    const group = nodesById.get(parentId);
    const storedWidth = Number(group?.style?.width);
    const storedHeight = Number(group?.style?.height);
    if (group && storedWidth > 0 && storedHeight > 0) {
      groups.set(parentId, {
        position: group.position,
        size: { width: storedWidth, height: storedHeight },
      });
      continue;
    }
    let maxX = 0;
    let maxY = 0;
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    for (const child of children) {
      const size = nodeSize(child);
      minX = Math.min(minX, child.position.x);
      minY = Math.min(minY, child.position.y);
      maxX = Math.max(maxX, child.position.x + size.width);
      maxY = Math.max(maxY, child.position.y + size.height);
    }
    groups.set(parentId, {
      position: { x: minX - BOUNDARY_PAD_X, y: minY - BOUNDARY_PAD_TOP },
      size: {
        width: maxX - minX + 2 * BOUNDARY_PAD_X,
        height: maxY - minY + BOUNDARY_PAD_TOP + BOUNDARY_PAD_BOTTOM,
      },
    });
  }
  if (groups.size === 0) return nodes;

  return nodes.map((node) => {
    const asGroup = groups.get(node.id);
    if (asGroup) {
      return {
        ...node,
        position: asGroup.position,
        style: { ...node.style, ...asGroup.size },
      };
    }
    if (node.parentNode) {
      const parent = groups.get(node.parentNode);
      if (parent) {
        return {
          ...node,
          position: {
            x: node.position.x - parent.position.x,
            y: node.position.y - parent.position.y,
          },
        };
      }
    }
    return node;
  });
}

export { NODE_WIDTH, NODE_HEIGHT };
