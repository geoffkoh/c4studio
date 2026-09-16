// The legend, while a perspective is being shown (PP-176).
//
// A perspective repaints the diagram: what carries it keeps (or takes) a
// colour and a value badge, everything else fades to 0.1. The ordinary
// legend explains element and relationship *styles*, so under a
// perspective it explains colours the diagram is no longer using — it
// says "Datastore" beside purple while the purple box on screen means
// "High". Rather than fade it or leave it lying, the rows are replaced
// with what the diagram now shows.
//
// Upstream is no guide here: its diagram key is a separate modal, built
// once, and does not respond to the perspective filter at all.
//
// Pure, and in `diagram-core` rather than the SPA so the headless
// renderer applies the same rule: `c4 render --perspective` and the
// viewer must not disagree about what a perspective looks like.

import type { GraphPayload, LegendEntry } from "./svg";

/** One perspective on an element or a relationship, with any
    `Perspective:` style the server resolved already applied. */
export interface Perspective {
  name: string;
  description: string;
  value: string;
  /** Element paint. */
  background?: string;
  textColor?: string;
  stroke?: string;
  /** Relationship paint. */
  color?: string;
}

/** Swatch colour for a value that no `Perspective:` style painted. */
const UNSTYLED_COLOUR = "#90a4ae";

/** Swatch colour for the row explaining what faded out. */
const FADED_COLOUR = "#d7dce1";

/** Minimum shape of a node this module reads. */
interface LegendNode {
  type?: string;
  data: { perspectives?: Perspective[]; shape?: string; kind?: string };
}

/** Minimum shape of an edge this module reads. */
interface LegendEdge {
  data?: { perspectives?: Perspective[] };
}

/** Opacity, as a Structurizr percentage, for what lacks the perspective.
    The renderers already fade a node or an edge by this, so the overlay
    needs no separate notion of "faded". */
const FADED_OPACITY = 10;

/** The named perspective on a node's or edge's data, if it carries one. */
function find(
  perspectives: Perspective[] | undefined,
  name: string,
): Perspective | undefined {
  return perspectives?.find((p) => p.name === name);
}

/**
 * A row's wording: the perspective's value, or its name when it has none.
 *
 * A perspective is free to carry only a description (`security "PII
 * encrypted at rest"`), and every such item then lands on one row saying
 * which perspective it is — still the answer to "what is highlighted".
 */
function labelFor(perspective: Perspective, name: string): string {
  return perspective.value || name;
}

/**
 * Legend rows for the perspective being shown, replacing the style rows.
 *
 * One row per distinct value carried by something on the diagram —
 * elements first, then relationships, each in the order they appear so
 * repeated renders stay stable — plus a final row for what faded, when
 * anything did. A value that no `Perspective:` style painted gets a
 * neutral swatch: the items keep their own colours, so no single colour
 * would be telling the truth, and the row is then saying which items
 * carry the value rather than what colour means what.
 *
 * @param nodes Graph nodes, carrying their perspectives.
 * @param edges Graph edges, carrying theirs.
 * @param name The perspective being shown.
 * @returns Rows in the same shape the legend already renders.
 */
export function perspectiveLegendEntries(
  nodes: LegendNode[],
  edges: LegendEdge[],
  name: string,
): LegendEntry[] {
  const entries: LegendEntry[] = [];
  const seen = new Set<string>();
  let anyFaded = false;

  for (const node of nodes) {
    if (node.type !== "element") continue;
    const shown = find(node.data.perspectives, name);
    if (!shown) {
      anyFaded = true;
      continue;
    }
    const label = labelFor(shown, name);
    const colour = shown.background ?? UNSTYLED_COLOUR;
    const key = `element:${label}:${colour}`;
    if (seen.has(key)) continue;
    seen.add(key);
    entries.push({
      kind: "element",
      label,
      colour,
      // The value is the subject, not the element's shape, so every row
      // uses the same swatch rather than repeating one per shape.
      shape: "RoundedBox",
      border: "",
    });
  }

  for (const edge of edges) {
    const shown = find(edge.data?.perspectives, name);
    if (!shown) {
      anyFaded = true;
      continue;
    }
    const label = labelFor(shown, name);
    const key = `relationship:${label}:${shown.color ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    entries.push({
      kind: "relationship",
      label,
      ...(shown.color ? { colour: shown.color } : {}),
    });
  }

  if (anyFaded) {
    entries.push({
      kind: "element",
      label: `Not in ${name}`,
      colour: FADED_COLOUR,
      shape: "RoundedBox",
      border: "",
    });
  }
  return entries;
}

/**
 * A payload repainted for one perspective, as the viewer paints it.
 *
 * Everything that carries the perspective keeps its place and takes the
 * `Perspective:` style's colours (when one matched) plus a badge showing
 * its value; everything else — boundaries included, once anything has
 * faded — drops to `FADED_OPACITY`. The legend is rebuilt from the
 * values, for the reason at the top of this file.
 *
 * Expressed as a transform of the payload rather than as painting rules
 * so the SVG emitter needs no notion of perspectives at all: fading is
 * the `opacity` it already honours, and recolouring is the `background`
 * it already reads.
 *
 * @param payload The graph payload as the server built it.
 * @param name The perspective to show.
 * @returns A new payload; the original is not modified.
 */
export function applyPerspective(
  payload: GraphPayload,
  name: string,
): GraphPayload {
  const entries = perspectiveLegendEntries(
    payload.nodes.map((node) => ({
      type: node.data.kind === "boundary" ? "boundary" : "element",
      data: node.data,
    })),
    payload.edges.map((edge) => ({ data: { perspectives: edge.perspectives } })),
    name,
  );

  let anyFaded = false;
  const nodes = payload.nodes.map((node) => {
    if (node.data.kind === "boundary") return node;
    const shown = node.data.perspectives?.find((p) => p.name === name);
    if (!shown) {
      anyFaded = true;
      return { ...node, data: { ...node.data, opacity: FADED_OPACITY } };
    }
    return {
      ...node,
      data: {
        ...node.data,
        ...(shown.background ? { background: shown.background } : {}),
        ...(shown.textColor ? { textColor: shown.textColor } : {}),
        ...(shown.stroke ? { stroke: shown.stroke } : {}),
        perspectiveBadge: shown.value || name,
      },
    };
  });

  const edges = payload.edges.map((edge) => {
    const shown = edge.perspectives?.find((p) => p.name === name);
    if (!shown) {
      anyFaded = true;
      return { ...edge, opacity: FADED_OPACITY };
    }
    return { ...edge, ...(shown.color ? { color: shown.color } : {}) };
  });

  return {
    ...payload,
    nodes: anyFaded
      ? nodes.map((node) =>
          node.data.kind === "boundary"
            ? { ...node, data: { ...node.data, opacity: FADED_OPACITY } }
            : node,
        )
      : nodes,
    edges,
    legend: entries,
  };
}
