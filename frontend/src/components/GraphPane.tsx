import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Panel,
  SelectionMode,
  useEdgesState,
  useNodesState,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeTypes,
  type ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";

import {
  align,
  distribute,
  nudge,
  type AlignMode,
  type Box,
  type DistributeMode,
  type Moves,
  BoundaryNode,
  ChromeNode,
  CHROME_PREFIX,
  chromePlacement,
  isChromeNode,
  EDGE_PAINT,
  ElementNode,
  ExportButtons,
  FloatingEdge,
  insertionIndex,
  layoutGraph,
  normalizeStoredPositions,
  type ElementNodeData,
  type FloatingEdgeData,
} from "@pystructurizr/diagram-core";
import { buildTrail, crumbLabel, drillTarget } from "../navigation";
import { isTypingTarget } from "../shortcuts";
import type { GraphData, ViewInfo, Workspace } from "../types";
import {
  EdgeContextMenu,
  type EdgeMenuState,
  type MenuAction,
} from "./EdgeContextMenu";
import { KeyboardShortcuts } from "./KeyboardShortcuts";
import { SelectionTools } from "./SelectionTools";

const NODE_TYPES: NodeTypes = {
  element: ElementNode,
  boundary: BoundaryNode,
  chrome: ChromeNode,
};
const EDGE_TYPES: EdgeTypes = { floating: FloatingEdge };

/** Relationship line routing, rendered by the floating edge. */
type EdgeStyle = "default" | "straight" | "step" | "smoothstep";

const EDGE_STYLES: { value: EdgeStyle; label: string }[] = [
  { value: "default", label: "Bezier" },
  { value: "straight", label: "Straight" },
  { value: "step", label: "Step" },
  { value: "smoothstep", label: "Smooth step" },
];

const EDGE_STYLE_STORAGE_KEY = "pystructurizr.edgeStyle";
const HOVER_EMPHASIS_STORAGE_KEY = "pystructurizr.hoverEmphasis";
const SNAP_TO_GRID_STORAGE_KEY = "pystructurizr.snapToGrid";
const INTERACTION_STORAGE_KEY = "pystructurizr.interaction";

// Drag snapping step. Matches the Background dot spacing so the dots read
// as the grid being snapped to rather than as unrelated decoration.
const SNAP_GRID: [number, number] = [16, 16];

/**
 * What a left-drag on empty canvas does. Modal rather than a modifier so
 * neither gesture is hidden: in `pan` the diagram behaves as it always
 * has (drag pans, scroll zooms) and Shift+drag still selects; in `select`
 * a drag draws a selection box and panning moves to two-finger scroll and
 * the middle/right button.
 */
type Interaction = "pan" | "select";

const INTERACTIONS: { value: Interaction; label: string }[] = [
  { value: "pan", label: "Pan" },
  { value: "select", label: "Select" },
];

// Mouse buttons that pan while in select mode. Middle only: the right
// button opens the relationship context menu.
const PAN_BUTTONS = [1];

function storedEdgeStyle(): EdgeStyle {
  const raw = window.localStorage.getItem(EDGE_STYLE_STORAGE_KEY);
  return EDGE_STYLES.some((s) => s.value === raw)
    ? (raw as EdgeStyle)
    : "default";
}

function storedHoverEmphasis(): boolean {
  return window.localStorage.getItem(HOVER_EMPHASIS_STORAGE_KEY) !== "off";
}

/** Off unless explicitly enabled: free positioning stays the default. */
function storedSnapToGrid(): boolean {
  return window.localStorage.getItem(SNAP_TO_GRID_STORAGE_KEY) === "on";
}

/** Pan unless explicitly switched: a viewer pans on drag by convention. */
function storedInteraction(): Interaction {
  return window.localStorage.getItem(INTERACTION_STORAGE_KEY) === "select"
    ? "select"
    : "pan";
}

interface GraphPaneProps {
  view: ViewInfo | null;
  views: ViewInfo[];
  workspace: Workspace | null;
  onNavigate: (view: ViewInfo) => void;
  /**
   * How to reach the backend. Injected rather than imported so the pane
   * can be embedded where there is no pystructurizr API to call — a
   * Confluence macro reading Forge storage, or github.dev talking to the
   * Pyodide bridge.
   */
  loadGraph: (key: string, expand: string[]) => Promise<GraphData>;
  saveLayout: (
    key: string,
    positions: Record<string, [number, number]>,
    sizes: Record<string, [number, number]>,
    waypoints: Record<string, [number, number][]>,
    labels: Record<string, [number, number]>,
  ) => Promise<unknown>;
  resetLayout: (key: string) => Promise<unknown>;
}

/** Convert the API graph payload into React Flow nodes/edges. */
async function toFlow(
  data: GraphData,
  view: ViewInfo,
  views: ViewInfo[],
  workspace: Workspace | null,
  onToggleExpand: (id: string, expand: boolean) => void,
  onGeometryChange: () => void,
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  const anyMissingPosition = data.nodes.some((n) => n.position === undefined);
  const trail = buildTrail(view, views, workspace);
  const parentView = trail.length > 1 ? trail[trail.length - 2] : undefined;
  const boundaryType =
    view.type === "component" ? "Container" : "Software System";

  const nodes: Node[] = data.nodes.map((n) => {
    const isBoundary = n.data.kind === "boundary";
    // Only the view's own (root) boundary drills out to the parent view;
    // nested boundaries (expanded containers, deployment nodes) do not.
    const isRootBoundary = isBoundary && !n.parentId;
    const target =
      isRootBoundary && !n.data.expanded
        ? parentView
        : drillTarget(n, views, view);
    return {
      id: n.id,
      type: isBoundary ? "boundary" : "element",
      // The boundary's interior is pointer-transparent so edges behind it
      // stay hoverable; its label is the drag handle.
      ...(isBoundary ? { dragHandle: ".boundary__hit, .boundary__label" } : {}),
      position: n.position ?? { x: 0, y: 0 },
      ...(n.parentId
        ? { parentNode: n.parentId, extent: "parent" as const }
        : {}),
      ...(n.size ? { style: { ...n.size } } : {}),
      data: {
        ...n.data,
        boundaryType,
        drillKey: target?.key,
        drillLabel: target ? crumbLabel(target, workspace) : undefined,
        onToggleExpand,
        onGeometryChange,
      },
    };
  });

  // Edges sharing a node pair (either direction) fan out as curves so
  // bidirectional flows and parallel relationships stay readable: each
  // gets a perpendicular offset, sign-normalised to the canonical pair
  // order so opposite directions bow to opposite sides.
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
      // The middle edge of an odd-sized group keeps the straight centre
      // line (offset 0); the rest fan out around it.
      curveOffset = (index - (total - 1) / 2) * CURVE_GAP * canonical;
    }
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: "floating",
      data: {
        label: e.label || undefined,
        order: e.order,
        curveOffset,
        waypoints: e.waypoints,
        labelOffset: e.labelOffset,
      },
      ...EDGE_PAINT,
    };
  });

  // If any node lacks a stored position, run a fresh auto-layout; otherwise
  // adapt the stored absolute positions to the nested-node model.
  const positioned = anyMissingPosition
    ? await layoutGraph(nodes, edges, data.rankDirection, {
        rankSeparation: data.rankSeparation,
        nodeSeparation: data.nodeSeparation,
      })
    : await normalizeStoredPositions(nodes, edges);

  // The diagram's own title and legend. Added after layout and excluded
  // from saved layouts (see absolutePositions): they describe the diagram
  // rather than belonging to it. They live inside the viewport, not in a
  // Panel, so PNG/SVG export captures them.
  const placement = chromePlacement(positioned);
  const chrome: Node[] = [];
  const title = view.title || view.key;
  if (title) {
    chrome.push({
      id: `${CHROME_PREFIX}title`,
      type: "chrome",
      position: placement.title,
      data: { kind: "title", title },
      draggable: false,
      selectable: false,
      deletable: false,
    });
  }
  if (data.legend && data.legend.length > 0) {
    chrome.push({
      id: `${CHROME_PREFIX}legend`,
      type: "chrome",
      position: placement.legend,
      data: { kind: "legend", entries: data.legend },
      draggable: false,
      selectable: false,
      deletable: false,
    });
  }
  return { nodes: [...positioned, ...chrome], edges };
}

// Expand/collapse and re-layout transitions tween between the old and new
// layouts instead of jumping.
const TWEEN_MS = 320;

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

interface Tween {
  from: { x: number; y: number };
  to: { x: number; y: number };
  fromWidth?: number;
  fromHeight?: number;
  toWidth?: number;
  toHeight?: number;
}

/**
 * Absolute top-left positions for every node, resolving nested (parent-
 * relative) coordinates by walking the parent chain. This is the format
 * the layout sidecar stores, independent of the current nesting.
 */
function absolutePositions(nodes: Node[]): Record<string, [number, number]> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const positions: Record<string, [number, number]> = {};
  for (const node of nodes) {
    // The title and legend are not model elements; persisting them would
    // put junk ids in the user's layout sidecar.
    if (isChromeNode(node.id)) continue;
    let x = node.position.x;
    let y = node.position.y;
    let parent = node.parentNode ? byId.get(node.parentNode) : undefined;
    while (parent) {
      x += parent.position.x;
      y += parent.position.y;
      parent = parent.parentNode ? byId.get(parent.parentNode) : undefined;
    }
    positions[node.id] = [Math.round(x), Math.round(y)];
  }
  return positions;
}

/**
 * Renders the selected view's graph with React Flow: nested C4 boundaries
 * (to any depth — deployment nodes, expanded containers), centre-anchored
 * floating edges, draggable nodes, zoom/pan, a breadcrumb for drill in/out
 * navigation, controls and a minimap. Falls back to friendly notices for
 * unsupported/empty views and load errors.
 */
export function GraphPane({
  view,
  views,
  workspace,
  onNavigate,
  loadGraph,
  saveLayout,
  resetLayout,
}: GraphPaneProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "ready">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [edgeStyle, setEdgeStyle] = useState<EdgeStyle>(storedEdgeStyle);
  // Hover emphasis: highlight the hovered relationship, dim the rest.
  const [hoverEmphasis, setHoverEmphasis] = useState<boolean>(storedHoverEmphasis);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [snapToGrid, setSnapToGrid] = useState<boolean>(storedSnapToGrid);
  const [interaction, setInteraction] =
    useState<Interaction>(storedInteraction);
  const [edgeMenu, setEdgeMenu] = useState<EdgeMenuState | null>(null);
  const [layoutState, setLayoutState] = useState<"idle" | "saved" | "failed">(
    "idle",
  );
  // Bumped by "reset layout" to force a refetch of the current view.
  const [layoutEpoch, setLayoutEpoch] = useState(0);
  // Expanded container ids, scoped to the view they were expanded in so a
  // view switch implicitly resets the expansion.
  const [expansion, setExpansion] = useState<{ key: string; ids: string[] }>({
    key: "",
    ids: [],
  });
  const expandedIds = useMemo(
    () => (view && expansion.key === view.key ? expansion.ids : []),
    [view, expansion],
  );

  // Dynamic-view animation: null shows every step; otherwise steps beyond
  // the current one are dimmed and the current one is highlighted.
  const [animStep, setAnimStep] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    setAnimStep(null);
    setPlaying(false);
  }, [view?.key]);

  const isDynamic = view?.type === "dynamic";
  const maxStep = useMemo(
    () =>
      edges.reduce((max, edge) => {
        const order = (edge.data as { order?: number } | undefined)?.order;
        return order !== undefined && order > max ? order : max;
      }, 0),
    [edges],
  );

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setAnimStep((step) => {
        const next = (step ?? 0) + 1;
        if (next >= maxStep) setPlaying(false);
        return Math.min(next, maxStep);
      });
    }, 1400);
    return () => window.clearInterval(timer);
  }, [playing, maxStep]);

  const handleEdgeStyle = useCallback((style: EdgeStyle) => {
    setEdgeStyle(style);
    window.localStorage.setItem(EDGE_STYLE_STORAGE_KEY, style);
  }, []);

  const handleHoverToggle = useCallback(() => {
    setHoverEmphasis((enabled) => {
      const next = !enabled;
      window.localStorage.setItem(
        HOVER_EMPHASIS_STORAGE_KEY,
        next ? "on" : "off",
      );
      if (!next) setHoveredEdgeId(null);
      return next;
    });
  }, []);

  const handleSnapToggle = useCallback(() => {
    setSnapToGrid((enabled) => {
      const next = !enabled;
      window.localStorage.setItem(SNAP_TO_GRID_STORAGE_KEY, next ? "on" : "off");
      return next;
    });
  }, []);

  const handleInteraction = useCallback((mode: Interaction) => {
    setInteraction(mode);
    window.localStorage.setItem(INTERACTION_STORAGE_KEY, mode);
  }, []);

  /** `v` flips between the two modes without leaving the diagram. */
  const handleInteractionToggle = useCallback(() => {
    setInteraction((mode) => {
      const next = mode === "pan" ? "select" : "pan";
      window.localStorage.setItem(INTERACTION_STORAGE_KEY, next);
      return next;
    });
  }, []);

  const handleToggleExpand = useCallback(
    (id: string, expand: boolean) => {
      if (!view) return;
      setExpansion((prev) => {
        const ids = prev.key === view.key ? prev.ids : [];
        const next = expand ? [...ids, id] : ids.filter((x) => x !== id);
        return { key: view.key, ids: next };
      });
    },
    [view],
  );

  // Autosave the whole layout when a drag or resize finishes. Positions
  // are stored absolute so they survive changes in nesting; boundary
  // dimensions are stored alongside. The ref keeps the resize callback
  // (captured in node data) reading fresh state.
  const nodesRef = useRef<Node[]>(nodes);
  nodesRef.current = nodes;
  const edgesRef = useRef<Edge[]>(edges);
  edgesRef.current = edges;
  const rfRef = useRef<ReactFlowInstance | null>(null);
  const animationRef = useRef(0);
  // Which view the nodes currently on screen belong to; same-view updates
  // (expand/collapse, live reload) animate, view switches jump.
  const shownViewRef = useRef<string | null>(null);

  useEffect(() => () => cancelAnimationFrame(animationRef.current), []);

  /**
   * Replace the graph with `next`, tweening nodes that survive the change
   * from their old geometry to the new one. Entering nodes (and nodes
   * whose parent changed, where relative coordinates are incomparable)
   * fade in instead. Boundary width/height interpolate alongside, so an
   * expansion visibly grows out of the collapsed element.
   */
  const animateToNodes = useCallback(
    (next: Node[]) => {
      cancelAnimationFrame(animationRef.current);
      const prevById = new Map(nodesRef.current.map((n) => [n.id, n]));
      const tweens = new Map<string, Tween>();

      const prepared = next.map((n) => {
        const before = prevById.get(n.id);
        const sameParent =
          before !== undefined &&
          (before.parentNode ?? null) === (n.parentNode ?? null);
        if (!before || !sameParent) {
          const entering = ["node-enter", n.className]
            .filter(Boolean)
            .join(" ");
          return { ...n, className: entering };
        }
        const toWidth = Number(n.style?.width) || undefined;
        const toHeight = Number(n.style?.height) || undefined;
        const fromWidth =
          before.width ?? (Number(before.style?.width) || undefined);
        const fromHeight =
          before.height ?? (Number(before.style?.height) || undefined);
        tweens.set(n.id, {
          from: before.position,
          to: n.position,
          fromWidth,
          fromHeight,
          toWidth,
          toHeight,
        });
        return n;
      });

      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / TWEEN_MS);
        const k = easeInOutCubic(t);
        setNodes(
          prepared.map((n) => {
            const tween = tweens.get(n.id);
            if (!tween) return n;
            const frame: Node = {
              ...n,
              position: {
                x: tween.from.x + (tween.to.x - tween.from.x) * k,
                y: tween.from.y + (tween.to.y - tween.from.y) * k,
              },
            };
            if (
              tween.toWidth !== undefined &&
              tween.toHeight !== undefined &&
              tween.fromWidth !== undefined &&
              tween.fromHeight !== undefined
            ) {
              frame.style = {
                ...n.style,
                width:
                  tween.fromWidth + (tween.toWidth - tween.fromWidth) * k,
                height:
                  tween.fromHeight + (tween.toHeight - tween.fromHeight) * k,
              };
            }
            return frame;
          }),
        );
        if (t < 1) {
          animationRef.current = requestAnimationFrame(step);
        }
      };
      animationRef.current = requestAnimationFrame(step);
    },
    [setNodes],
  );

  /** Current bend points for every edge that has any, keyed by edge id. */
  const collectWaypoints = useCallback(
    (source: Edge[]): Record<string, [number, number][]> => {
      const out: Record<string, [number, number][]> = {};
      for (const edge of source) {
        const points = (edge.data as FloatingEdgeData | undefined)?.waypoints;
        if (points && points.length > 0) out[edge.id] = points;
      }
      return out;
    },
    [],
  );

  /** Dragged label offsets, keyed by edge id, for the layout sidecar. */
  const collectLabelOffsets = useCallback(
    (edges: Edge[]): Record<string, [number, number]> => {
      const offsets: Record<string, [number, number]> = {};
      for (const edge of edges) {
        const offset = (edge.data as FloatingEdgeData | undefined)?.labelOffset;
        if (offset && (offset[0] || offset[1])) {
          offsets[edge.id] = [Math.round(offset[0]), Math.round(offset[1])];
        }
      }
      return offsets;
    },
    [],
  );

  const saveCurrentLayout = useCallback(
    (edgeOverride?: Edge[]) => {
    if (!view) return;
    const current = nodesRef.current;
    const sizes: Record<string, [number, number]> = {};
    for (const node of current) {
      if (node.type !== "boundary") continue;
      const width = node.width ?? Number(node.style?.width);
      const height = node.height ?? Number(node.style?.height);
      if (width > 0 && height > 0) {
        sizes[node.id] = [Math.round(width), Math.round(height)];
      }
    }
    saveLayout(
      view.key,
      absolutePositions(current),
      sizes,
      collectWaypoints(edgeOverride ?? edgesRef.current),
      collectLabelOffsets(edgeOverride ?? edgesRef.current),
    )
      .then(() => {
        setLayoutState("saved");
        window.setTimeout(() => setLayoutState("idle"), 1500);
      })
      .catch(() => setLayoutState("failed"));
    },
    [view, collectWaypoints, collectLabelOffsets, saveLayout],
  );

  /**
   * Apply absolute-coordinate moves back onto the nodes.
   *
   * Nodes inside a boundary are positioned relative to their parent, so a
   * move computed in absolute space has to have the parent's absolute
   * origin subtracted again — the same conversion absolutePositions does
   * in the other direction. Getting this wrong lines elements up inside
   * their own boundaries while leaving them visually scattered.
   */
  const applyMoves = useCallback(
    (moves: Moves) => {
      if (Object.keys(moves).length === 0) return;
      const current = nodesRef.current;
      const byId = new Map(current.map((n) => [n.id, n]));
      const originOf = (node: Node): { x: number; y: number } => {
        let x = 0;
        let y = 0;
        let parent = node.parentNode ? byId.get(node.parentNode) : undefined;
        while (parent) {
          x += parent.position.x;
          y += parent.position.y;
          parent = parent.parentNode ? byId.get(parent.parentNode) : undefined;
        }
        return { x, y };
      };
      const updated = current.map((node) => {
        const move = moves[node.id];
        if (!move) return node;
        const origin = originOf(node);
        return {
          ...node,
          position: { x: move.x - origin.x, y: move.y - origin.y },
        };
      });
      nodesRef.current = updated;
      setNodes(updated);
      saveCurrentLayout();
    },
    [setNodes, saveCurrentLayout],
  );

  /** Selected nodes as absolute boxes, which is what the geometry wants. */
  const selectedBoxes = useCallback((): Box[] => {
    const current = nodesRef.current;
    const byId = new Map(current.map((n) => [n.id, n]));
    const absolute = (node: Node): { x: number; y: number } => {
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
    return current
      .filter((node) => node.selected)
      .map((node) => {
        const { x, y } = absolute(node);
        return {
          id: node.id,
          x,
          y,
          width: node.width ?? Number(node.style?.width ?? 200),
          height: node.height ?? Number(node.style?.height ?? 110),
        };
      });
  }, []);

  const handleAlign = useCallback(
    (mode: AlignMode) => applyMoves(align(selectedBoxes(), mode)),
    [applyMoves, selectedBoxes],
  );

  const handleDistribute = useCallback(
    (mode: DistributeMode) => applyMoves(distribute(selectedBoxes(), mode)),
    [applyMoves, selectedBoxes],
  );

  // Arrow keys nudge the selection: 1px for placement, 10px with Shift to
  // cover ground. Modifier-free arrows would otherwise do nothing at all,
  // so there is no gesture to conflict with.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const deltas: Record<string, [number, number]> = {
        ArrowLeft: [-1, 0],
        ArrowRight: [1, 0],
        ArrowUp: [0, -1],
        ArrowDown: [0, 1],
      };
      const delta = deltas[event.key];
      if (!delta || event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const boxes = selectedBoxes();
      if (boxes.length === 0) return;
      event.preventDefault();
      const step = event.shiftKey ? 10 : 1;
      applyMoves(nudge(boxes, delta[0] * step, delta[1] * step));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedBoxes, applyMoves]);


  /** Move one edge's label, then persist on drag end. */
  const handleLabelDrag = useCallback(
    (edgeId: string, dx: number, dy: number) => {
      const updated = edgesRef.current.map((edge) =>
        edge.id === edgeId
          ? { ...edge, data: { ...edge.data, labelOffset: [dx, dy] } }
          : edge,
      );
      edgesRef.current = updated;
      setEdges(updated);
    },
    [setEdges],
  );

  const handleLabelDragEnd = useCallback(() => {
    saveCurrentLayout(edgesRef.current);
  }, [saveCurrentLayout]);

  /** Replace one edge's bend points, then persist the whole layout. */
  const updateWaypoints = useCallback(
    (edgeId: string, next: [number, number][]) => {
      const updated = edgesRef.current.map((edge) =>
        edge.id === edgeId
          ? { ...edge, data: { ...edge.data, waypoints: next } }
          : edge,
      );
      edgesRef.current = updated;
      setEdges(updated);
      saveCurrentLayout(updated);
    },
    [setEdges, saveCurrentLayout],
  );

  const handleWaypointDrag = useCallback(
    (edgeId: string, index: number, x: number, y: number) => {
      setEdges((current) =>
        current.map((edge) => {
          if (edge.id !== edgeId) return edge;
          const points = [
            ...(((edge.data as FloatingEdgeData).waypoints ?? []) as [
              number,
              number,
            ][]),
          ];
          points[index] = [x, y];
          return { ...edge, data: { ...edge.data, waypoints: points } };
        }),
      );
    },
    [setEdges],
  );

  /** Right-click on a relationship, or on one of its bend points. */
  const handleEdgeContextMenu = useCallback(
    (event: ReactMouseEvent, edge: Edge) => {
      event.preventDefault();
      const target = event.target as HTMLElement;
      const handle = target.closest<HTMLElement>(".edge-waypoint");
      const flow = rfRef.current?.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      }) ?? { x: 0, y: 0 };
      setEdgeMenu({
        x: event.clientX,
        y: event.clientY,
        edgeId: edge.id,
        waypointIndex: handle
          ? Number(handle.dataset.waypointIndex)
          : undefined,
        flowX: Math.round(flow.x),
        flowY: Math.round(flow.y),
      });
    },
    [],
  );

  /**
   * Menu entries for the open menu. A new bend point is inserted at the
   * segment nearest the click rather than appended, so bends stay in the
   * order the line visits them.
   */
  const edgeMenuActions = useMemo((): MenuAction[] => {
    if (!edgeMenu) return [];
    const edge = edgesRef.current.find((e) => e.id === edgeMenu.edgeId);
    const points = ((edge?.data as FloatingEdgeData | undefined)?.waypoints ??
      []) as [number, number][];
    const actions: MenuAction[] = [];

    if (edgeMenu.waypointIndex === undefined) {
      actions.push({
        label: "Add bend point here",
        onSelect: () => {
          const next: [number, number][] = [...points];
          // Endpoints are needed to tell "before the bend" from "after"
          // it, so the insertion is measured against the real segments.
          const absolute = absolutePositions(nodesRef.current);
          const byId = new Map(nodesRef.current.map((n) => [n.id, n]));
          const centreOf = (id: string): [number, number] => {
            const at = absolute[id] ?? [0, 0];
            const node = byId.get(id);
            return [
              at[0] + (node?.width ?? 0) / 2,
              at[1] + (node?.height ?? 0) / 2,
            ];
          };
          next.splice(
            insertionIndex(
              centreOf(edge?.source ?? ""),
              centreOf(edge?.target ?? ""),
              points,
              edgeMenu.flowX,
              edgeMenu.flowY,
            ),
            0,
            [edgeMenu.flowX, edgeMenu.flowY],
          );
          updateWaypoints(edgeMenu.edgeId, next);
        },
      });
    } else {
      actions.push({
        label: "Remove bend point",
        destructive: true,
        onSelect: () =>
          updateWaypoints(
            edgeMenu.edgeId,
            points.filter((_, i) => i !== edgeMenu.waypointIndex),
          ),
      });
    }
    if (points.length > 0) {
      actions.push({
        label: "Straighten relationship",
        destructive: true,
        onSelect: () => updateWaypoints(edgeMenu.edgeId, []),
      });
    }
    return actions;
  }, [edgeMenu, updateWaypoints]);

  const handleWaypointMenu = useCallback(
    (edgeId: string, index: number, clientX: number, clientY: number) => {
      setEdgeMenu({
        x: clientX,
        y: clientY,
        edgeId,
        waypointIndex: index,
        flowX: 0,
        flowY: 0,
      });
    },
    [],
  );

  const handleWaypointDragEnd = useCallback(() => {
    saveCurrentLayout(edgesRef.current);
  }, [saveCurrentLayout]);

  const handleResetLayout = useCallback(() => {
    if (!view) return;
    resetLayout(view.key)
      .then(() => {
        setLayoutState("idle");
        setLayoutEpoch((epoch) => epoch + 1);
      })
      .catch(() => setLayoutState("failed"));
  }, [view, resetLayout]);

  // Routing is presentation-only, so it is applied on the way into React
  // Flow rather than baked into the edge state.
  const styledEdges = useMemo(() => {
    const activeHover = hoverEmphasis ? hoveredEdgeId : null;
    return edges.map((edge) => {
      const order = (edge.data as { order?: number } | undefined)?.order;
      const animState =
        isDynamic && animStep !== null && order !== undefined
          ? order === animStep
            ? ("active" as const)
            : order < animStep
              ? ("past" as const)
              : ("future" as const)
          : undefined;
      const hovered = edge.id === activeHover;
      return {
        ...edge,
        ...(hovered ? { zIndex: 1000 } : {}),
        data: {
          ...edge.data,
          pathStyle: edgeStyle,
          animState,
          hoverState: hovered ? ("hovered" as const) : undefined,
          onHoverChange: hoverEmphasis ? setHoveredEdgeId : undefined,
          onWaypointDrag: handleWaypointDrag,
          onLabelDrag: handleLabelDrag,
          onLabelDragEnd: handleLabelDragEnd,
          onWaypointDragEnd: handleWaypointDragEnd,
          onWaypointMenu: handleWaypointMenu,
        },
      };
    });
  }, [
    edges,
    edgeStyle,
    isDynamic,
    animStep,
    hoverEmphasis,
    hoveredEdgeId,
    handleWaypointDrag,
    handleWaypointDragEnd,
    handleWaypointMenu,
  ]);

  // A node joins the animation at its earliest step; before that it dims.
  const firstStepByNode = useMemo(() => {
    const first = new Map<string, number>();
    for (const edge of edges) {
      const order = (edge.data as { order?: number } | undefined)?.order;
      if (order === undefined) continue;
      for (const id of [edge.source, edge.target]) {
        const known = first.get(id);
        if (known === undefined || order < known) first.set(id, order);
      }
    }
    return first;
  }, [edges]);

  const styledNodes = useMemo(() => {
    if (!isDynamic || animStep === null) return nodes;
    return nodes.map((node) => {
      const firstStep = firstStepByNode.get(node.id);
      const future = firstStep !== undefined && firstStep > animStep;
      return { ...node, className: future ? "anim-future" : undefined };
    });
  }, [nodes, isDynamic, animStep, firstStepByNode]);

  useEffect(() => {
    if (!view || !view.supported) {
      setNodes([]);
      setEdges([]);
      setStatus("idle");
      setError(null);
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError(null);

    loadGraph(view.key, expandedIds)
      .then(async (data) => {
        if (cancelled) return;
        const flow = await toFlow(
          data,
          view,
          views,
          workspace,
          handleToggleExpand,
          saveCurrentLayout,
        );
        if (cancelled) return;
        const sameView =
          shownViewRef.current === view.key && nodesRef.current.length > 0;
        shownViewRef.current = view.key;
        if (sameView) {
          animateToNodes(flow.nodes);
        } else {
          setNodes(flow.nodes);
        }
        setEdges(flow.edges);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Failed to load graph";
        setError(message);
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [
    view,
    views,
    workspace,
    expandedIds,
    layoutEpoch,
    handleToggleExpand,
    saveCurrentLayout,
    animateToNodes,
    setNodes,
    setEdges,
    loadGraph,
  ]);

  const handleNodeDoubleClick = useCallback(
    (_event: unknown, node: Node) => {
      const key = (node.data as ElementNodeData | undefined)?.drillKey;
      if (!key) return;
      const target = views.find((v) => v.key === key);
      if (target) onNavigate(target);
    },
    [views, onNavigate],
  );

  const selectedCount = useMemo(
    () => nodes.filter((node) => node.selected).length,
    [nodes],
  );

  const trail = useMemo(
    () => (view ? buildTrail(view, views, workspace) : []),
    [view, views, workspace],
  );

  const isEmpty = status === "ready" && nodes.length === 0;

  // Re-fit the viewport when switching views, but not on expand/collapse.
  const fitKey = useMemo(() => view?.key ?? "none", [view]);

  if (!view) {
    return (
      <div className="notice">
        <div className="notice__title">No view selected</div>
        <p>Choose a renderable view from the sidebar to see its diagram.</p>
      </div>
    );
  }

  if (!view.supported) {
    return (
      <div className="notice">
        <div className="notice__title">This view is not renderable yet</div>
        <p>
          <code>{view.type}</code> views are not supported. Try a system
          context, container, component, or deployment view.
        </p>
      </div>
    );
  }

  if (status === "loading" && nodes.length === 0) {
    return (
      <div className="notice">
        <div className="notice__title">Loading diagram…</div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="notice">
        <div className="notice__title">Could not load this diagram</div>
        <p>{error}</p>
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="notice">
        <div className="notice__title">Nothing to show</div>
        <p>This view has no elements to display.</p>
      </div>
    );
  }

  return (
    <div className="graph">
      <ReactFlow
        key={fitKey}
        nodes={styledNodes}
        edges={styledEdges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDoubleClick={handleNodeDoubleClick}
        onNodeDragStop={() => saveCurrentLayout()}
        onInit={(instance) => {
          rfRef.current = instance;
        }}
        onEdgeContextMenu={handleEdgeContextMenu}
        onEdgeMouseEnter={(_, edge) => setHoveredEdgeId(edge.id)}
        onEdgeMouseLeave={() => setHoveredEdgeId(null)}
        snapToGrid={snapToGrid}
        snapGrid={SNAP_GRID}
        selectionOnDrag={interaction === "select"}
        // Full (reactflow's default) rather than Partial: a node must be
        // wholly inside the box. Partial would catch any node the box
        // merely touches, which means every boundary containing the
        // gesture — dragging a box around two containers inside a
        // container would take the container too. Boundaries are still
        // selectable by clicking their border or label, or by enclosing
        // them completely.
        selectionMode={SelectionMode.Full}
        panOnDrag={interaction === "select" ? PAN_BUTTONS : true}
        panOnScroll={interaction === "select"}
        // Views are derived from the model, so removing a node from the
        // canvas means nothing — without this, Backspace silently deletes
        // the selection until the next reload.
        deleteKeyCode={null}
        fitView
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
      >
        {trail.length > 1 ? (
          <Panel position="top-left" className="breadcrumb">
            {trail.map((crumb, index) => (
              <span key={crumb.key} className="breadcrumb__item">
                {index > 0 ? <span className="breadcrumb__sep">›</span> : null}
                {crumb.key === view.key ? (
                  <span className="breadcrumb__crumb breadcrumb__crumb--current">
                    {crumbLabel(crumb, workspace)}
                  </span>
                ) : (
                  <button
                    className="breadcrumb__crumb"
                    onClick={() => onNavigate(crumb)}
                  >
                    {crumbLabel(crumb, workspace)}
                  </button>
                )}
              </span>
            ))}
          </Panel>
        ) : null}
        <SelectionTools
          count={selectedCount}
          onAlign={handleAlign}
          onDistribute={handleDistribute}
        />
        <Panel position="top-right" className="edge-style">
          <span className="edge-style__title">Mouse</span>
          {INTERACTIONS.map((mode) => (
            <button
              key={mode.value}
              className={
                "edge-style__option" +
                (mode.value === interaction ? " edge-style__option--active" : "")
              }
              title={
                mode.value === "pan"
                  ? "Drag pans the diagram; Shift+drag selects"
                  : "Drag draws a selection box; scroll or middle-drag pans"
              }
              onClick={() => handleInteraction(mode.value)}
            >
              {mode.label}
            </button>
          ))}
          <span className="edge-style__divider" />
          <span className="edge-style__title">Edges</span>
          {EDGE_STYLES.map((style) => (
            <button
              key={style.value}
              className={
                "edge-style__option" +
                (style.value === edgeStyle ? " edge-style__option--active" : "")
              }
              onClick={() => handleEdgeStyle(style.value)}
            >
              {style.label}
            </button>
          ))}
          <ExportButtons viewKey={view.key} />
          <span className="edge-style__divider" />
          <button
            className="edge-style__option"
            title="Discard saved positions and re-run auto-layout"
            onClick={handleResetLayout}
          >
            Reset layout
          </button>
          <span className="edge-style__divider" />
          <button
            className={
              "edge-style__option" +
              (hoverEmphasis ? " edge-style__option--active" : "")
            }
            title="Highlight the hovered relationship and dim the rest"
            onClick={handleHoverToggle}
          >
            Hover
          </button>
          <button
            className={
              "edge-style__option" +
              (snapToGrid ? " edge-style__option--active" : "")
            }
            title={`Snap dragged nodes to a ${SNAP_GRID[0]}px grid`}
            onClick={handleSnapToggle}
          >
            Snap
          </button>
          {layoutState !== "idle" ? (
            <span
              className={
                "layout-status" +
                (layoutState === "failed" ? " layout-status--failed" : "")
              }
            >
              {layoutState === "saved" ? "Saved ✓" : "Save failed"}
            </span>
          ) : null}
        </Panel>
        {isDynamic && maxStep > 0 ? (
          <Panel position="bottom-center" className="anim-controls">
            <button
              className="anim-controls__button"
              onClick={() => {
                setPlaying(false);
                setAnimStep(null);
              }}
              disabled={animStep === null}
            >
              All
            </button>
            <button
              className="anim-controls__button"
              onClick={() => {
                setPlaying(false);
                setAnimStep((step) => Math.max(1, (step ?? 1) - 1));
              }}
              disabled={animStep === null || animStep <= 1}
            >
              ◀
            </button>
            <span className="anim-controls__step">
              {animStep === null ? "All steps" : `Step ${animStep}/${maxStep}`}
            </span>
            <button
              className="anim-controls__button"
              onClick={() => {
                setPlaying(false);
                setAnimStep((step) => Math.min(maxStep, (step ?? 0) + 1));
              }}
              disabled={animStep !== null && animStep >= maxStep}
            >
              ▶
            </button>
            <button
              className="anim-controls__button"
              onClick={() => {
                if (playing) {
                  setPlaying(false);
                } else {
                  setAnimStep((step) =>
                    step === null || step >= maxStep ? 1 : step,
                  );
                  setPlaying(true);
                }
              }}
            >
              {playing ? "Pause" : "Play"}
            </button>
          </Panel>
        ) : null}
        <KeyboardShortcuts
          viewKey={view.key}
          onHoverToggle={handleHoverToggle}
          onSnapToggle={handleSnapToggle}
          onInteractionToggle={handleInteractionToggle}
        />
        {edgeMenu && edgeMenuActions.length > 0 ? (
          <EdgeContextMenu
            state={edgeMenu}
            actions={edgeMenuActions}
            onClose={() => setEdgeMenu(null)}
          />
        ) : null}
        <Background gap={16} />
        <Controls />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => {
            const data = n.data as ElementNodeData | undefined;
            if (data?.kind === "boundary") return "rgba(144, 164, 174, 0.25)";
            return data?.color ?? "#78909c";
          }}
        />
      </ReactFlow>
    </div>
  );
}
