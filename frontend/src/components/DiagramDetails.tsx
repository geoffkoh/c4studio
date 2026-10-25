import { useMemo, type KeyboardEvent } from "react";
import type { Edge, Node } from "reactflow";

import type { GraphData } from "../types";
import { ElementDetails, KIND_LABELS } from "./ElementDetails";

interface DiagramDetailsProps {
  /** React Flow's nodes and edges: what is selected lives on these. */
  nodes: Node[];
  edges: Edge[];
  /** The payload they were built from: what the server knows about each. */
  payload: GraphData | null;
  onSelectNode: (id: string) => void;
  onShowDefinition?: (elementId: string) => void;
  onClose: () => void;
}

/**
 * The Diagrams page's details card (PP-205): whatever is selected, shown
 * through the same `ElementDetails` as the Explorer's panel.
 *
 * It follows the selection rather than opening on it — selecting is also
 * how a drag starts, and arranging is what this page is mostly for — so
 * with nothing (or several things) selected it stays open and says so,
 * instead of flickering shut between clicks.
 */
export function DiagramDetails({
  nodes,
  edges,
  payload,
  onSelectNode,
  onShowDefinition,
  onClose,
}: DiagramDetailsProps) {
  // Elements only: boundaries and the title/legend chrome are layout,
  // not things with details of their own.
  const selectedNodes = nodes.filter((n) => n.selected && n.type === "element");
  const selectedEdges = edges.filter((e) => e.selected);
  const count = selectedNodes.length + selectedEdges.length;

  const byId = useMemo(
    () => new Map((payload?.nodes ?? []).map((n) => [n.id, n])),
    [payload],
  );
  const edgeById = useMemo(
    () => new Map((payload?.edges ?? []).map((e) => [e.id, e])),
    [payload],
  );
  const label = (id: string) => byId.get(id)?.data.label ?? id;

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") onClose();
  };

  let body;
  if (count === 1 && selectedNodes.length === 1) {
    const node = byId.get(selectedNodes[0].id);
    const id = selectedNodes[0].id;
    body = node ? (
      <ElementDetails
        name={node.data.label}
        kind={KIND_LABELS[node.data.kind] ?? node.data.kind}
        technology={node.data.technology}
        description={node.data.description}
        tags={node.data.tags}
        properties={node.data.properties}
        relationships={(payload?.edges ?? [])
          .filter((e) => e.source === id || e.target === id)
          .map((e) => {
            const outgoing = e.source === id;
            const peer = outgoing ? e.target : e.source;
            return {
              key: e.id,
              outgoing,
              peer: label(peer),
              onPeer: () => onSelectNode(peer),
              description: e.relationship?.description ?? e.label,
              properties: e.relationship?.properties,
            };
          })}
        onShowDefinition={onShowDefinition ? () => onShowDefinition(id) : undefined}
        onClose={onClose}
      />
    ) : null;
  } else if (count === 1) {
    const edge = edgeById.get(selectedEdges[0].id);
    const rel = edge?.relationship;
    body = edge ? (
      <ElementDetails
        name={`${label(edge.source)} → ${label(edge.target)}`}
        kind="Relationship"
        technology={rel?.technology}
        description={rel ? rel.description : edge.label}
        properties={rel?.properties}
        onClose={onClose}
      >
        {rel ? null : (
          <p className="details__note">
            Drawn for relationships between elements inside these two, so it
            has no details of its own.
          </p>
        )}
      </ElementDetails>
    ) : null;
  }

  return (
    <aside
      className="diagram-details"
      aria-label="Details"
      onKeyDown={onKeyDown}
      // Its own scrolling and clicks must not reach the canvas.
      onWheel={(event) => event.stopPropagation()}
    >
      {body ?? (
        <>
          <button className="details__close" title="Close" onClick={onClose}>
            ×
          </button>
          <p className="details__note">
            {count > 1
              ? `${count} selected. Select one element or relationship to see its details.`
              : "Select an element or a relationship to see its details."}
          </p>
        </>
      )}
    </aside>
  );
}
