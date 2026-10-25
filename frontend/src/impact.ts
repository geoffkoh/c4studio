// The impact overlay (PP-193): what else is involved when one element
// changes, painted onto the view on screen.
//
// It is expressed as a perspective. Every node the change reaches gets an
// `IMPACT` perspective saying how — the element itself and its family,
// what depends on it, what it depends on — and everything else fades, so
// the overlay reuses the perspective machinery whole: the fading, the
// badges, and a legend rebuilt from what the diagram shows (PP-176). Two
// overlays that faded things by different rules would be two notions of
// "faded" for a reader to learn.
//
// Pure, so it can be reasoned about apart from GraphPane's state.

import type { Edge, Node } from "reactflow";

import type { GPerspective, ImpactResult } from "./types";

/** The overlay's perspective name. Not a word a model is likely to use
    for a perspective of its own, which would otherwise be found first. */
export const IMPACT = "Change impact";

/** The faded row, in words that say what fading means here. */
export const IMPACT_FADED = "Not involved";

/** How a node takes part, with its paint. White text reads on each. */
const ROLES = {
  changed: { value: "Changed", background: "#c2255c" },
  dependent: { value: "Depends on it", background: "#d9480f" },
  dependency: { value: "It depends on", background: "#1864ab" },
  both: { value: "Both ways", background: "#5f3dc4" },
} as const;

type Role = keyof typeof ROLES;

/** Each involved element's perspective, by id. */
export function impactPerspectives(result: ImpactResult): Map<string, GPerspective> {
  const names = new Map<string, string>();
  for (const hop of [...result.dependents, ...result.dependencies]) {
    names.set(hop.id, hop.name);
  }
  names.set(result.element.id, result.element.name);
  const nameOf = (id: string) => names.get(id) ?? id;

  const roles = new Map<string, { role: Role; description: string }>();
  roles.set(result.element.id, { role: "changed", description: "The element asked about" });
  for (const id of result.family) {
    roles.set(id, {
      role: "changed",
      description: `Contains or is inside ${result.element.name}`,
    });
  }
  const reach = (hops: ImpactResult["dependents"], role: "dependent" | "dependency") => {
    for (const hop of hops) {
      const known = roles.get(hop.id);
      if (known?.role === "changed") continue;
      const distance = hop.depth === 1 ? "Directly" : `${hop.depth} steps away`;
      const description = `${distance}, via ${nameOf(hop.via)}`;
      roles.set(hop.id, {
        role: known && known.role !== role ? "both" : role,
        description: known ? `${known.description}; ${description}` : description,
      });
    }
  };
  reach(result.dependents, "dependent");
  reach(result.dependencies, "dependency");

  const out = new Map<string, GPerspective>();
  for (const [id, { role, description }] of roles) {
    out.set(id, {
      name: IMPACT,
      value: ROLES[role].value,
      description,
      background: ROLES[role].background,
      textColor: "#ffffff",
      stroke: ROLES[role].background,
    });
  }
  return out;
}

/** A relationship is involved when both of its ends are. */
const INVOLVED_EDGE: GPerspective = {
  name: IMPACT,
  value: "Between involved elements",
  description: "",
};

/**
 * Nodes and edges with the impact perspective added where it applies.
 *
 * Added beside the model's own perspectives rather than replacing them,
 * so clearing the overlay needs nothing undone: the perspective picker
 * simply goes back to looking up its own name.
 */
export function withImpact(
  nodes: Node[],
  edges: Edge[],
  perspectives: Map<string, GPerspective>,
): { nodes: Node[]; edges: Edge[] } {
  const add = <T extends { data?: { perspectives?: GPerspective[] } }>(
    item: T,
    perspective: GPerspective,
  ): T => ({
    ...item,
    data: {
      ...item.data,
      perspectives: [...(item.data?.perspectives ?? []), perspective],
    },
  });
  return {
    nodes: nodes.map((node) => {
      const perspective = perspectives.get(node.id);
      return perspective ? add(node, perspective) : node;
    }),
    edges: edges.map((edge) =>
      perspectives.has(edge.source) && perspectives.has(edge.target)
        ? add(edge, INVOLVED_EDGE)
        : edge,
    ),
  };
}
