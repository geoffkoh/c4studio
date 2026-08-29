import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Panel,
  useEdgesState,
  useNodesState,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeTypes,
  type ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";

import { ApiError, getModelGraph } from "../api";
import {
  BoundaryNode,
  EDGE_PAINT,
  ElementNode,
  FloatingEdge,
  layoutGraph,
} from "@c4studio/diagram-core";
import { crumbLabel } from "../navigation";
import { isTypingTarget } from "../shortcuts";
import type {
  ExplorerLevel,
  ModelElement,
  ModelGraphData,
  ViewInfo,
  Workspace,
} from "../types";

const NODE_TYPES: NodeTypes = { element: ElementNode, boundary: BoundaryNode };
const EDGE_TYPES: EdgeTypes = { floating: FloatingEdge };

const LEVELS: { value: ExplorerLevel; label: string }[] = [
  { value: "systems", label: "Systems" },
  { value: "containers", label: "Containers" },
  { value: "components", label: "Components" },
];

const LEVEL_ORDER: ExplorerLevel[] = ["systems", "containers", "components"];
const LEVEL_STORAGE_KEY = "c4studio.explorerLevel";

/** Human label per element kind, for search results and the details panel. */
const KIND_LABELS: Record<string, string> = {
  person: "Person",
  "person-external": "Person",
  system: "Software System",
  "system-external": "Software System",
  container: "Container",
  component: "Component",
  custom: "Custom Element",
};

function storedLevel(): ExplorerLevel {
  const raw = window.localStorage.getItem(LEVEL_STORAGE_KEY);
  return LEVEL_ORDER.includes(raw as ExplorerLevel)
    ? (raw as ExplorerLevel)
    : "containers";
}

/** Convert the explorer payload into laid-out React Flow nodes/edges. */
async function toFlow(
  data: ModelGraphData,
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  const nodes: Node[] = data.nodes.map((n) => {
    const isBoundary = n.data.kind === "boundary";
    return {
      id: n.id,
      type: isBoundary ? "boundary" : "element",
      ...(isBoundary ? { dragHandle: ".boundary__hit, .boundary__label" } : {}),
      position: { x: 0, y: 0 },
      ...(n.parentId
        ? { parentNode: n.parentId, extent: "parent" as const }
        : {}),
      data: { ...n.data, boundaryType: "Software System" },
    };
  });

  // Edges sharing a node pair fan out as curves (same scheme as the view
  // graph pane) so bidirectional flows stay readable.
  const CURVE_GAP = 48;
  const pairKey = (e: { source: string; target: string }) =>
    [e.source, e.target].sort().join("|");
  const pairCounts = new Map<string, number>();
  for (const e of data.edges) {
    const key = pairKey(e);
    pairCounts.set(key, (pairCounts.get(key) ?? 0) + 1);
  }
  const pairSeen = new Map<string, number>();

  const edges: Edge[] = data.edges.map((e) => {
    const key = pairKey(e);
    const total = pairCounts.get(key) ?? 1;
    let curveOffset: number | undefined;
    if (total > 1) {
      const index = pairSeen.get(key) ?? 0;
      pairSeen.set(key, index + 1);
      const canonical = e.source <= e.target ? 1 : -1;
      curveOffset = (index - (total - 1) / 2) * CURVE_GAP * canonical;
    }
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: "floating",
      data: { label: e.label || undefined, curveOffset },
      ...EDGE_PAINT,
    };
  });

  return { nodes: await layoutGraph(nodes, edges, data.rankDirection), edges };
}

function matchesQuery(element: ModelElement, query: string): boolean {
  const haystacks = [
    element.name,
    element.technology,
    element.description,
    element.parent,
    ...element.tags,
  ];
  return haystacks.some((h) => h.toLowerCase().includes(query));
}

interface ExplorerPaneProps {
  views: ViewInfo[];
  workspace: Workspace | null;
  /** Bumped by the app on live reload so the explorer refetches. */
  reloadTick: number;
  onOpenView: (view: ViewInfo) => void;
  onShowDefinition: (elementId: string) => void;
}

/**
 * Full-model explorer: the entire static model as one interactive graph,
 * with a level selector (systems / containers / components), search over
 * every element regardless of the rendered level, and a details panel
 * showing the selected element's metadata, relationships and the curated
 * views it appears in. Selecting a search hit below the current level
 * automatically deepens the level and centres on the element.
 */
export function ExplorerPane({
  views,
  workspace,
  reloadTick,
  onOpenView,
  onShowDefinition,
}: ExplorerPaneProps) {
  const [level, setLevel] = useState<ExplorerLevel>(storedLevel);
  const [data, setData] = useState<ModelGraphData | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [status, setStatus] = useState<"loading" | "error" | "ready">(
    "loading",
  );
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Element to select once data at a deeper level has loaded.
  const pendingFocusRef = useRef<string | null>(null);
  const [rf, setRf] = useState<ReactFlowInstance | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const handleLevel = useCallback((next: ExplorerLevel) => {
    setLevel(next);
    window.localStorage.setItem(LEVEL_STORAGE_KEY, next);
  }, []);

  // "/" focuses the search box, Escape clears search and selection.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "/" && !isTypingTarget(event.target)) {
        searchRef.current?.focus();
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setError(null);
    getModelGraph(level)
      .then(async (payload) => {
        if (cancelled) return;
        const flow = await toFlow(payload);
        if (cancelled) return;
        setData(payload);
        setNodes(flow.nodes);
        setEdges(flow.edges);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.message : "Failed to load the model",
        );
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [level, reloadTick, setNodes, setEdges]);

  const elementsById = useMemo(() => {
    const map = new Map<string, ModelElement>();
    for (const element of data?.elements ?? []) map.set(element.id, element);
    return map;
  }, [data]);

  const nodeIds = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);

  /** Centre the viewport on a node once React Flow has measured it. */
  const centerOn = useCallback(
    (id: string) => {
      window.requestAnimationFrame(() => {
        const node = rf?.getNode(id);
        if (!node?.positionAbsolute) return;
        rf?.setCenter(
          node.positionAbsolute.x + (node.width ?? 0) / 2,
          node.positionAbsolute.y + (node.height ?? 0) / 2,
          { zoom: Math.max(rf.getZoom(), 0.8), duration: 500 },
        );
      });
    },
    [rf],
  );

  /** Select an element, deepening the level first when it has no node yet. */
  const select = useCallback(
    (element: ModelElement) => {
      setQuery("");
      const needed = LEVEL_ORDER.indexOf(element.level);
      if (LEVEL_ORDER.indexOf(level) < needed) {
        pendingFocusRef.current = element.id;
        handleLevel(LEVEL_ORDER[needed]);
        return;
      }
      setSelectedId(element.id);
      centerOn(element.id);
    },
    [level, handleLevel, centerOn],
  );

  // Apply a pending selection once the deeper graph is on screen.
  useEffect(() => {
    const pending = pendingFocusRef.current;
    if (status !== "ready" || !pending || !nodeIds.has(pending)) return;
    pendingFocusRef.current = null;
    setSelectedId(pending);
    centerOn(pending);
  }, [status, nodeIds, centerOn]);

  const trimmed = query.trim().toLowerCase();
  const searchHits = useMemo(() => {
    if (!trimmed || !data) return [];
    return data.elements.filter((e) => matchesQuery(e, trimmed)).slice(0, 30);
  }, [data, trimmed]);

  // While searching, matching nodes stay lit and the rest dim; matches
  // below the current level light up their visible ancestor boundary.
  const matchedNodeIds = useMemo(() => {
    if (!trimmed || !data) return null;
    const matched = new Set<string>();
    for (const element of data.elements) {
      if (matchesQuery(element, trimmed)) matched.add(element.id);
    }
    return matched;
  }, [data, trimmed]);

  const styledNodes = useMemo(
    () =>
      nodes.map((node) => {
        const classes: string[] = [];
        if (node.id === selectedId) classes.push("explorer-focus");
        if (matchedNodeIds && !matchedNodeIds.has(node.id)) {
          classes.push("explorer-dim");
        }
        return classes.length
          ? { ...node, className: classes.join(" ") }
          : node;
      }),
    [nodes, selectedId, matchedNodeIds],
  );

  const selected = selectedId ? elementsById.get(selectedId) : undefined;
  const selectedRelationships = useMemo(() => {
    if (!selectedId || !data) return [];
    return data.relationships.filter(
      (rel) =>
        rel.source_id === selectedId || rel.destination_id === selectedId,
    );
  }, [data, selectedId]);
  const selectedViews = useMemo(() => {
    if (!selectedId || !data) return [];
    const keys = data.views_by_element[selectedId] ?? [];
    return keys
      .map((key) => views.find((v) => v.key === key))
      .filter((v): v is ViewInfo => v !== undefined && v.supported);
  }, [data, selectedId, views]);

  if (status === "error") {
    return (
      <div className="notice">
        <div className="notice__title">Could not load the model</div>
        <p>{error}</p>
      </div>
    );
  }

  if (status === "ready" && nodes.length === 0) {
    return (
      <div className="notice">
        <div className="notice__title">Nothing to explore</div>
        <p>The loaded workspace has no model elements.</p>
      </div>
    );
  }

  return (
    <div className="explorer">
      <div className="explorer__canvas">
        <ReactFlow
          nodes={styledNodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={setRf}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onNodeDoubleClick={(_, node) => onShowDefinition(node.id)}
          onPaneClick={() => setSelectedId(null)}
          fitView
          minZoom={0.05}
          proOptions={{ hideAttribution: true }}
        >
          <Panel position="top-left" className="explorer-search">
            <input
              ref={searchRef}
              className="explorer-search__input"
              placeholder="Search elements…  ( / )"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setQuery("");
                  event.currentTarget.blur();
                } else if (event.key === "Enter" && searchHits.length > 0) {
                  select(searchHits[0]);
                }
              }}
            />
            {trimmed && (
              <div className="explorer-search__results">
                {searchHits.length === 0 ? (
                  <div className="explorer-search__empty">No matches</div>
                ) : (
                  searchHits.map((hit) => (
                    <button
                      key={hit.id}
                      className="explorer-search__hit"
                      onClick={() => select(hit)}
                    >
                      <span className="explorer-search__name">{hit.name}</span>
                      <span className="explorer-search__meta">
                        {KIND_LABELS[hit.kind] ?? hit.kind}
                        {hit.parent ? ` — ${hit.parent}` : ""}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </Panel>
          <Panel position="top-right" className="edge-style">
            <span className="edge-style__title">Level</span>
            {LEVELS.map((entry) => (
              <button
                key={entry.value}
                className={
                  "edge-style__option" +
                  (entry.value === level ? " edge-style__option--active" : "")
                }
                onClick={() => handleLevel(entry.value)}
              >
                {entry.label}
              </button>
            ))}
          </Panel>
          <Background gap={16} />
          <Controls />
          <MiniMap
            pannable
            zoomable
            nodeColor={(n) => {
              const nodeData = n.data as { kind?: string; color?: string };
              if (nodeData.kind === "boundary")
                return "rgba(144, 164, 174, 0.25)";
              return nodeData.color ?? "#78909c";
            }}
          />
        </ReactFlow>
      </div>
      {selected ? (
        <aside className="explorer-details">
          <button
            className="explorer-details__close"
            title="Close"
            onClick={() => setSelectedId(null)}
          >
            ×
          </button>
          <h3 className="explorer-details__name">{selected.name}</h3>
          <div className="explorer-details__kind">
            [{KIND_LABELS[selected.kind] ?? selected.kind}
            {selected.technology ? `: ${selected.technology}` : ""}]
          </div>
          {selected.parent ? (
            <div className="explorer-details__parent">{selected.parent}</div>
          ) : null}
          {selected.description ? (
            <p className="explorer-details__desc">{selected.description}</p>
          ) : null}
          {selected.tags.length > 0 ? (
            <div className="explorer-details__tags">
              {selected.tags.map((tag) => (
                <span key={tag} className="explorer-details__tag">
                  {tag}
                </span>
              ))}
            </div>
          ) : null}

          {selectedRelationships.length > 0 ? (
            <>
              <h4 className="explorer-details__heading">Relationships</h4>
              <ul className="explorer-details__rels">
                {selectedRelationships.map((rel, index) => {
                  const outgoing = rel.source_id === selectedId;
                  const otherId = outgoing
                    ? rel.destination_id
                    : rel.source_id;
                  const other = elementsById.get(otherId);
                  return (
                    <li key={rel.id || index}>
                      <span className="explorer-details__arrow">
                        {outgoing ? "→" : "←"}
                      </span>
                      {other ? (
                        <button
                          className="explorer-details__link"
                          onClick={() => select(other)}
                        >
                          {other.name}
                        </button>
                      ) : (
                        <span>{otherId}</span>
                      )}
                      {rel.description ? <em> — {rel.description}</em> : null}
                    </li>
                  );
                })}
              </ul>
            </>
          ) : null}

          {selectedViews.length > 0 ? (
            <>
              <h4 className="explorer-details__heading">Appears in</h4>
              <ul className="explorer-details__views">
                {selectedViews.map((view) => (
                  <li key={view.key}>
                    <button
                      className="explorer-details__link"
                      onClick={() => onOpenView(view)}
                    >
                      {crumbLabel(view, workspace)}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          <button
            className="explorer-details__definition"
            onClick={() => onShowDefinition(selected.id)}
          >
            Show definition
          </button>
        </aside>
      ) : null}
    </div>
  );
}
