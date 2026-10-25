import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  Position,
  getBezierPath,
  getStraightPath,
  useStore,
  type EdgeProps,
  type Node,
} from "reactflow";

import { EDGE_HOVER_COLOUR, EDGE_HOVER_WIDTH } from "../edgePaint";
import {
  dragRun,
  handlePoint,
  nearestSide,
  orthogonalPath,
  orthogonalRoute,
  routeLabelPoint,
  runIsDraggable,
  segmentRuns,
  type Pins,
  type Pt,
  type Rect,
  type Run,
  type Side,
} from "../orthogonal";
import { perspectiveHint, type PerspectiveBadge } from "./ElementNode";

export interface FloatingEdgeData {
  /** Dragged offset from the label's computed place, in flow units. */
  labelOffset?: [number, number];
  /** Live drag updates; absent when labels are not draggable. */
  onLabelDrag?: (edgeId: string, dx: number, dy: number) => void;
  /** End of gesture, for persisting to the layout sidecar. */
  onLabelDragEnd?: () => void;
  label?: string;
  /** Which path renderer to use; anchoring is floating in all cases. */
  pathStyle?: "default" | "straight" | "step" | "smoothstep";
  /** Dynamic-view animation state for this edge's step. */
  animState?: "past" | "active" | "future";
  /** Set on the hovered edge so it pops; other edges are unaffected. */
  hoverState?: "hovered";
  /** Faded because a perspective is shown that this relationship lacks. */
  dimmed?: boolean;
  /** Set while a perspective is shown and this relationship carries it. */
  perspective?: PerspectiveBadge;
  /** Lets the label participate in hover tracking. */
  onHoverChange?: (edgeId: string | null) => void;
  /**
   * Manual bend points in flow coordinates. When present the edge is
   * routed as straight segments through them and `curveOffset` is
   * ignored: the bends are an explicit instruction, so an automatic curve
   * fighting them would be worse than useless. In the step styles (or
   * once re-routed) they are the corners of an orthogonal route instead,
   * which passes through each of them.
   */
  waypoints?: [number, number][];
  /** Drag feedback for a bend point; index identifies which. */
  onWaypointDrag?: (edgeId: string, index: number, x: number, y: number) => void;
  /** Fired once a bend-point drag finishes, so the layout can be saved. */
  onWaypointDragEnd?: () => void;
  /** Right-click on a bend point; opens the menu at screen coordinates. */
  onWaypointMenu?: (
    edgeId: string,
    index: number,
    clientX: number,
    clientY: number,
  ) => void;
  /**
   * Set when the edge has been re-routed by dragging its segments
   * (PP-196). It is then drawn orthogonally whatever `pathStyle` says, and
   * `waypoints` are its corners.
   */
  routing?: "orthogonal";
  /**
   * A relationship style's `routing Orthogonal` (PP-209): drawn as a
   * re-routed edge is, but kept apart from `routing` so it is never saved
   * to the sidecar or cleared by Reset route.
   */
  styleRouting?: "orthogonal";
  /**
   * Live segment-drag updates: the bends the dragged route now has.
   * Absent where routes are not editable (the Explorer).
   */
  onSegmentDrag?: (edgeId: string, bends: [number, number][]) => void;
  /** Fired once a segment drag finishes, so the layout can be saved. */
  onSegmentDragEnd?: () => void;
  /**
   * Sides the route's ends are pinned to (PP-201). Only an orthogonal
   * route honours them; an absent end attaches wherever the route meets
   * its node.
   */
  sides?: Pins;
  /**
   * Live end-handle drag: the end now snaps to `side`. Absent where
   * routes are not editable. Saved through `onSegmentDragEnd`.
   */
  onSideDrag?: (edgeId: string, end: keyof Pins, side: Side) => void;
  /** Grid step a dragged segment snaps to, when snapping is on. */
  snapGrid?: number;
  /**
   * Perpendicular offset (px) separating edges that share a node pair
   * (bidirectional flows, parallel relationships): the edge bows through
   * a control point this far from the centre line, and its label sits on
   * the curve's apex. Absent/0 keeps the straight centre line.
   */
  curveOffset?: number;
}

interface Point {
  x: number;
  y: number;
}

function rectOf(node: Node): Rect {
  return {
    x: node.positionAbsolute?.x ?? 0,
    y: node.positionAbsolute?.y ?? 0,
    width: node.width ?? 0,
    height: node.height ?? 0,
  };
}

/** How far along the line, from the node, an end handle sits. */
const END_HANDLE_INSET = 14;

/** Runs shorter than this get no handle: there is nothing to grab. */
const MIN_HANDLE_RUN = 16;

function center(node: Node): Point {
  const { positionAbsolute, width, height } = node;
  return {
    x: (positionAbsolute?.x ?? 0) + (width ?? 0) / 2,
    y: (positionAbsolute?.y ?? 0) + (height ?? 0) / 2,
  };
}

/**
 * Point where the line from `node`'s centre towards `aimAt` crosses
 * `node`'s rectangular border. This is what makes edges aim at node
 * centres (or a curve's control point) while arrowheads still start and
 * stop at the node edge.
 */
function borderIntersection(node: Node, aimAt: Point): Point {
  const w = (node.width ?? 0) / 2;
  const h = (node.height ?? 0) / 2;
  const nodeCenter = center(node);

  const dx = (aimAt.x - nodeCenter.x) / (2 * w) || 0;
  const dy = (aimAt.y - nodeCenter.y) / (2 * h) || 0;
  const scale = 1 / Math.max(Math.abs(dx), Math.abs(dy)) || 1;

  return {
    x: nodeCenter.x + dx * scale * w,
    y: nodeCenter.y + dy * scale * h,
  };
}

/** Which side of the node a border point sits on (for path curvature). */
function sideOf(node: Node, point: Point): Position {
  const x = node.positionAbsolute?.x ?? 0;
  const y = node.positionAbsolute?.y ?? 0;
  const width = node.width ?? 0;
  if (point.x <= x + 1) return Position.Left;
  if (point.x >= x + width - 1) return Position.Right;
  if (point.y <= y + 1) return Position.Top;
  return Position.Bottom;
}

interface WaypointHandleProps {
  edgeId: string;
  index: number;
  x: number;
  y: number;
  onDrag: (edgeId: string, index: number, x: number, y: number) => void;
  onDragEnd?: () => void;
  onMenu?: (
    edgeId: string,
    index: number,
    clientX: number,
    clientY: number,
  ) => void;
}

/**
 * A draggable bend point, drawn in the edge's own SVG group rather than in
 * the edge-label portal: the edges layer is where pointer hit-testing
 * already works for this app (it is how the line itself receives clicks),
 * and the label layer is pointer-transparent with its own stacking.
 *
 * Pointer capture keeps the gesture alive when the pointer leaves the
 * small circle, and screen deltas are divided by the viewport zoom so
 * dragging tracks the cursor at any scale. Right-click is handled here
 * rather than left to bubble, so "remove" is always reachable.
 */
function WaypointHandle({
  edgeId,
  index,
  x,
  y,
  onDrag,
  onDragEnd,
  onMenu,
}: WaypointHandleProps) {
  const zoom = useStore((store) => store.transform[2]);
  const origin = useRef<{ px: number; py: number; x: number; y: number } | null>(
    null,
  );

  return (
    <circle
      className="edge-waypoint nodrag nopan"
      cx={x}
      cy={y}
      r={5}
      pointerEvents="all"
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.stopPropagation();
        origin.current = { px: event.clientX, py: event.clientY, x, y };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const start = origin.current;
        if (!start) return;
        event.stopPropagation();
        const scale = zoom || 1;
        onDrag(
          edgeId,
          index,
          Math.round(start.x + (event.clientX - start.px) / scale),
          Math.round(start.y + (event.clientY - start.py) / scale),
        );
      }}
      onPointerUp={(event) => {
        if (!origin.current) return;
        origin.current = null;
        event.currentTarget.releasePointerCapture(event.pointerId);
        onDragEnd?.();
      }}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onMenu?.(edgeId, index, event.clientX, event.clientY);
      }}
    />
  );
}

/**
 * An edge that ignores fixed handles and anchors to node centres: the line
 * is aimed centre-to-centre and clipped to each node's border, so arrows
 * enter nodes head-on from any direction. The `pathStyle` in `data` picks
 * the renderer (bezier, straight, step, smooth step); a `curveOffset`
 * bows the edge sideways so overlapping relationships fan apart.
 */
interface EdgeLabelProps {
  id: string;
  text: string;
  x: number;
  y: number;
  offset?: [number, number];
  animState?: string;
  hovered: boolean;
  dimmed?: boolean;
  perspective?: PerspectiveBadge;
  onHoverChange?: (edgeId: string | null) => void;
  onDrag?: (edgeId: string, dx: number, dy: number) => void;
  onDragEnd?: () => void;
  /** Reports the label's rendered size, in canvas units. */
  onSize?: (width: number, height: number) => void;
}

/**
 * The relationship label, draggable away from the point on the line where
 * it would otherwise sit.
 *
 * The gesture mirrors WaypointHandle: pointer capture so it survives the
 * pointer leaving the small target, and screen deltas divided by the
 * viewport zoom so it tracks the cursor at any scale. The offset is stored
 * relative to the computed position, not absolutely, so a re-layout or a
 * dragged endpoint carries the label along with its line.
 *
 * Upstream Structurizr places labels with the `position` relationship
 * style (0-100 along the line); a free 2-D offset is ours, and lives in
 * the layout sidecar as per-user UI state.
 */
function EdgeLabel({
  id,
  text,
  x,
  y,
  offset,
  animState,
  hovered,
  dimmed,
  perspective,
  onHoverChange,
  onDrag,
  onDragEnd,
  onSize,
}: EdgeLabelProps) {
  const zoom = useStore((store) => store.transform[2]);
  const box = useRef<HTMLDivElement | null>(null);
  // The label layer is inside the viewport transform, so offsetWidth is
  // already in canvas units — what the edge needs to keep a handle clear.
  useLayoutEffect(() => {
    const element = box.current;
    if (!element || !onSize) return;
    const report = () => onSize(element.offsetWidth, element.offsetHeight);
    report();
    const observer = new ResizeObserver(report);
    observer.observe(element);
    return () => observer.disconnect();
  }, [onSize]);
  const origin = useRef<{ px: number; py: number; dx: number; dy: number } | null>(
    null,
  );
  const draggable = Boolean(onDrag);

  return (
    <div
      ref={box}
      className={
        "edge-label nodrag nopan" +
        (animState === "active" ? " edge-label--active" : "") +
        (animState === "future" || dimmed ? " edge-label--future" : "") +
        (hovered ? " edge-label--hovered" : "") +
        (draggable ? " edge-label--draggable" : "")
      }
      style={{
        transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
        pointerEvents: "all",
        zIndex: hovered ? 1000 : undefined,
      }}
      onMouseEnter={() => onHoverChange?.(id)}
      onMouseLeave={() => onHoverChange?.(null)}
      onPointerDown={(event) => {
        if (!onDrag || event.button !== 0) return;
        event.stopPropagation();
        origin.current = {
          px: event.clientX,
          py: event.clientY,
          dx: offset?.[0] ?? 0,
          dy: offset?.[1] ?? 0,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const start = origin.current;
        if (!start || !onDrag) return;
        onDrag(
          id,
          start.dx + (event.clientX - start.px) / zoom,
          start.dy + (event.clientY - start.py) / zoom,
        );
      }}
      onPointerUp={(event) => {
        if (!origin.current) return;
        origin.current = null;
        event.currentTarget.releasePointerCapture(event.pointerId);
        onDragEnd?.();
      }}
      onDoubleClick={(event) => {
        // Double-click returns the label to the line, the same affordance
        // the waypoint context menu offers for bend points.
        if (!onDrag) return;
        event.stopPropagation();
        onDrag(id, 0, 0);
        onDragEnd?.();
      }}
      title={
        [
          perspective ? perspectiveHint(perspective) : null,
          draggable ? "Drag to move; double-click to reset" : null,
        ]
          .filter(Boolean)
          .join("\n\n") || undefined
      }
    >
      {text}
      {perspective ? (
        <span className="edge-label__perspective">
          {perspective.value || perspective.name}
        </span>
      ) : null}
    </div>
  );
}

export function FloatingEdge({
  id,
  source,
  target,
  markerEnd,
  style,
  data,
}: EdgeProps<FloatingEdgeData>) {
  const sourceNode = useStore(
    useCallback((store) => store.nodeInternals.get(source), [source]),
  );
  const targetNode = useStore(
    useCallback((store) => store.nodeInternals.get(target), [target]),
  );
  const zoom = useStore((store) => store.transform[2]);
  // Window listeners of a segment drag in progress, rather than pointer
  // capture on the handle: the route's shape — and so its set of handles —
  // changes mid-drag (a new elbow at a node), which would unmount the very
  // handle being dragged.
  //
  // Deliberately *not* torn down when this component unmounts. With hover
  // emphasis on, leaving the line mid-drag changes the edge's z-index and
  // React Flow re-renders it in another layer — an unmount and remount.
  // Cleaning up there silently ended the drag after its first few pixels.
  // The listeners need nothing from the component (everything is captured
  // when the drag starts), and they always remove themselves on pointerup
  // or pointercancel.
  const endDrag = useRef<(() => void) | null>(null);
  // The label's size, so a segment handle can be kept out from under it.
  const [labelSize, setLabelSize] = useState<[number, number] | null>(null);
  const onLabelSize = useCallback(
    (width: number, height: number) =>
      setLabelSize((old) =>
        old && old[0] === width && old[1] === height ? old : [width, height],
      ),
    [],
  );

  if (!sourceNode || !targetNode || !sourceNode.width || !targetNode.width) {
    return null;
  }

  const sourceCenter = center(sourceNode);
  const targetCenter = center(targetNode);
  const bends = data?.waypoints ?? [];
  const curveOffset = bends.length > 0 ? 0 : (data?.curveOffset ?? 0);

  // With an offset, everything aims at a control point perpendicular to
  // the centre line's midpoint instead of the other node's centre.
  let control: Point | null = null;
  if (curveOffset !== 0) {
    const dx = targetCenter.x - sourceCenter.x;
    const dy = targetCenter.y - sourceCenter.y;
    const length = Math.hypot(dx, dy) || 1;
    control = {
      x: (sourceCenter.x + targetCenter.x) / 2 + (-dy / length) * curveOffset,
      y: (sourceCenter.y + targetCenter.y) / 2 + (dx / length) * curveOffset,
    };
  }

  const sourcePoint = borderIntersection(sourceNode, control ?? targetCenter);
  const targetPoint = borderIntersection(targetNode, control ?? sourceCenter);
  const params = {
    sourceX: sourcePoint.x,
    sourceY: sourcePoint.y,
    targetX: targetPoint.x,
    targetY: targetPoint.y,
    sourcePosition: sideOf(sourceNode, sourcePoint),
    targetPosition: sideOf(targetNode, targetPoint),
  };

  const pathStyle = data?.pathStyle ?? "default";
  // Step styles, or an edge re-routed by dragging, draw an orthogonal
  // route from orthogonal.ts — the same one `c4 render` draws — so its
  // segments can be grabbed and moved.
  const orthogonal =
    data?.routing === "orthogonal" ||
    data?.styleRouting === "orthogonal" ||
    pathStyle === "step" ||
    pathStyle === "smoothstep";
  const pins: Pins = data?.sides ?? {};
  let route: Pt[] = [];
  let path: string;
  let labelX: number;
  let labelY: number;
  if (orthogonal) {
    route = orthogonalRoute(
      rectOf(sourceNode),
      rectOf(targetNode),
      bends,
      data?.curveOffset ?? 0,
      pins,
    );
    path = orthogonalPath(route, pathStyle === "smoothstep" ? 8 : 0);
    ({ x: labelX, y: labelY } = routeLabelPoint(route));
  } else if (bends.length > 0) {
    // Straight segments through every bend, clipped to the node borders
    // at each end so arrowheads still land on the boundary.
    const first = { x: bends[0][0], y: bends[0][1] };
    const last = { x: bends[bends.length - 1][0], y: bends[bends.length - 1][1] };
    const from = borderIntersection(sourceNode, first);
    const to = borderIntersection(targetNode, last);
    const points = [from, ...bends.map(([x, y]) => ({ x, y })), to];
    path = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x},${p.y}`)
      .join(" ");
    // Label at the centre of the longest segment: always strictly between
    // two points, so it never sits on a bend handle and covers it, and the
    // longest run is where there is most room for the text.
    let longest = 0;
    let longestLength = -1;
    for (let i = 0; i < points.length - 1; i += 1) {
      const length = Math.hypot(
        points[i + 1].x - points[i].x,
        points[i + 1].y - points[i].y,
      );
      if (length > longestLength) {
        longestLength = length;
        longest = i;
      }
    }
    labelX = (points[longest].x + points[longest + 1].x) / 2;
    labelY = (points[longest].y + points[longest + 1].y) / 2;
  } else if (control && (pathStyle === "default" || pathStyle === "straight")) {
    // Quadratic bezier through the offset control point; the label sits
    // on the curve's apex, Q(0.5) = 0.25·S + 0.5·C + 0.25·T.
    path = `M ${sourcePoint.x},${sourcePoint.y} Q ${control.x},${control.y} ${targetPoint.x},${targetPoint.y}`;
    labelX = 0.25 * sourcePoint.x + 0.5 * control.x + 0.25 * targetPoint.x;
    labelY = 0.25 * sourcePoint.y + 0.5 * control.y + 0.25 * targetPoint.y;
  } else if (pathStyle === "straight") {
    [path, labelX, labelY] = getStraightPath({
      sourceX: params.sourceX,
      sourceY: params.sourceY,
      targetX: params.targetX,
      targetY: params.targetY,
    });
  } else {
    [path, labelX, labelY] = getBezierPath(params);
  }

  const animState = data?.animState;
  const hovered = data?.hoverState === "hovered";
  // The hovered edge pops (colour, weight, glow); nothing else changes.
  // Dynamic-view animation still dims future steps. Widths sit above the
  // resting EDGE_WIDTH so emphasis stays visible as that value is tuned.
  const emphasis = hovered
    ? {
        stroke: EDGE_HOVER_COLOUR,
        strokeWidth: EDGE_HOVER_WIDTH,
        filter: "drop-shadow(0 0 3px rgba(25, 118, 210, 0.55))",
      }
    : animState === "active"
      ? { stroke: EDGE_HOVER_COLOUR, strokeWidth: EDGE_HOVER_WIDTH - 0.4 }
      : animState === "future"
        ? { opacity: 0.08 }
        : data?.dimmed
          ? // Upstream fades what lacks the shown perspective to 0.1.
            { opacity: 0.1 }
          : {};
  const edgeStyle = { ...style, ...emphasis };

  /**
   * Start dragging one run of the route. Moves are measured from where
   * the pointer went down against the route as it was then, so the drag
   * is stable however the route reshapes along the way.
   */
  const startSegmentDrag = (
    event: ReactPointerEvent,
    run: Run,
    snapshot: Pt[],
  ) => {
    const onDrag = data?.onSegmentDrag;
    if (!onDrag || event.button !== 0) return;
    event.stopPropagation();
    event.preventDefault();
    const horizontal = run.axis === "h";
    const origin = horizontal ? snapshot[run.start].y : snapshot[run.start].x;
    const from = horizontal ? event.clientY : event.clientX;
    const scale = zoom || 1;
    const snap = data?.snapGrid;
    const onEnd = data?.onSegmentDragEnd;
    const move = (e: PointerEvent) => {
      const now = horizontal ? e.clientY : e.clientX;
      let value = origin + (now - from) / scale;
      if (snap) value = Math.round(value / snap) * snap;
      onDrag(id, dragRun(snapshot, run, value, pins));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      endDrag.current = null;
    };
    const up = () => {
      stop();
      onEnd?.();
    };
    endDrag.current?.();
    endDrag.current = stop;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  /**
   * Start dragging one end of the route onto a side of its node. The
   * pointer is tracked in flow units from the end's own position, and the
   * end snaps to whichever side of the node the pointer is nearest, so
   * the gesture reads as "drag the end where it should attach".
   */
  const startEndDrag = (event: ReactPointerEvent, end: keyof Pins, at: Pt) => {
    const onSide = data?.onSideDrag;
    const node = end === "source" ? sourceNode : targetNode;
    if (!onSide || !node || event.button !== 0) return;
    event.stopPropagation();
    event.preventDefault();
    const rect = rectOf(node);
    const from = { x: event.clientX, y: event.clientY };
    const scale = zoom || 1;
    const onEnd = data?.onSegmentDragEnd;
    let current = pins[end];
    const move = (e: PointerEvent) => {
      const side = nearestSide(rect, {
        x: at.x + (e.clientX - from.x) / scale,
        y: at.y + (e.clientY - from.y) / scale,
      });
      if (side === current) return;
      current = side;
      onSide(id, end, side);
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      endDrag.current = null;
    };
    const up = () => {
      stop();
      onEnd?.();
    };
    endDrag.current?.();
    endDrag.current = stop;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={edgeStyle} />
      {orthogonal && data?.onSegmentDrag
        ? segmentRuns(route).map((run, index) => {
            const a = route[run.start];
            const b = route[run.end];
            if (Math.hypot(b.x - a.x, b.y - a.y) < MIN_HANDLE_RUN) return null;
            if (!runIsDraggable(route, run, pins)) return null;
            const horizontal = run.axis === "h";
            const { x: cx, y: cy } = handlePoint(
              a,
              b,
              run,
              data.label && labelSize
                ? {
                    x: labelX + (data.labelOffset?.[0] ?? 0),
                    y: labelY + (data.labelOffset?.[1] ?? 0),
                    width: labelSize[0],
                    height: labelSize[1],
                  }
                : undefined,
            );
            return (
              <rect
                key={index}
                className={
                  "edge-segment-handle nodrag nopan" +
                  (horizontal ? " edge-segment-handle--h" : " edge-segment-handle--v")
                }
                data-run={index}
                x={cx - (horizontal ? 9 : 3)}
                y={cy - (horizontal ? 3 : 9)}
                width={horizontal ? 18 : 6}
                height={horizontal ? 6 : 18}
                rx={3}
                pointerEvents="all"
                onPointerDown={(event) => startSegmentDrag(event, run, route)}
              />
            );
          })
        : null}
      {orthogonal && data?.onSideDrag && route.length > 1
        ? (["source", "target"] as const).map((end) => {
            const at = end === "source" ? route[0] : route[route.length - 1];
            const next = end === "source" ? route[1] : route[route.length - 2];
            // A little way along the line rather than on the border: the
            // nodes layer is above the edges, so a handle centred on the
            // border would be half under its own node — and the target
            // end has the arrowhead there too.
            const length = Math.hypot(next.x - at.x, next.y - at.y) || 1;
            const inset = Math.min(END_HANDLE_INSET, length / 2);
            const cx = at.x + ((next.x - at.x) / length) * inset;
            const cy = at.y + ((next.y - at.y) / length) * inset;
            return (
              <circle
                key={end}
                className={
                  "edge-end-handle nodrag nopan" +
                  (pins[end] ? " edge-end-handle--pinned" : "")
                }
                data-end={end}
                cx={cx}
                cy={cy}
                r={5}
                pointerEvents="all"
                onPointerDown={(event) => startEndDrag(event, end, { x: cx, y: cy })}
              >
                <title>
                  {pins[end]
                    ? `Attached to the ${pins[end]} side — drag to another side`
                    : "Drag onto a side of the element to attach there"}
                </title>
              </circle>
            );
          })
        : null}
      {!orthogonal && data?.onWaypointDrag
        ? bends.map(([x, y], index) => (
            <WaypointHandle
              key={index}
              edgeId={id}
              index={index}
              x={x}
              y={y}
              onDrag={data.onWaypointDrag!}
              onDragEnd={data.onWaypointDragEnd}
              onMenu={data.onWaypointMenu}
            />
          ))
        : null}
      {data?.label ? (
        <EdgeLabelRenderer>
          <EdgeLabel
            id={id}
            text={data.label}
            x={labelX + (data.labelOffset?.[0] ?? 0)}
            y={labelY + (data.labelOffset?.[1] ?? 0)}
            offset={data.labelOffset}
            animState={animState}
            hovered={hovered}
            dimmed={data.dimmed}
            perspective={data.perspective}
            onHoverChange={data.onHoverChange}
            onDrag={data.onLabelDrag}
            onDragEnd={data.onLabelDragEnd}
            onSize={onLabelSize}
          />
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
