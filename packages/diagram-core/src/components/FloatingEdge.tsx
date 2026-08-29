import { useCallback, useRef } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  Position,
  getBezierPath,
  getSmoothStepPath,
  getStraightPath,
  useStore,
  type EdgeProps,
  type Node,
} from "reactflow";

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
  /** Lets the label participate in hover tracking. */
  onHoverChange?: (edgeId: string | null) => void;
  /**
   * Manual bend points in flow coordinates. When present the edge is
   * routed as straight segments through them and `pathStyle`/`curveOffset`
   * are ignored: the bends are an explicit instruction, so an automatic
   * curve fighting them would be worse than useless.
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
  onHoverChange?: (edgeId: string | null) => void;
  onDrag?: (edgeId: string, dx: number, dy: number) => void;
  onDragEnd?: () => void;
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
  onHoverChange,
  onDrag,
  onDragEnd,
}: EdgeLabelProps) {
  const zoom = useStore((store) => store.transform[2]);
  const origin = useRef<{ px: number; py: number; dx: number; dy: number } | null>(
    null,
  );
  const draggable = Boolean(onDrag);

  return (
    <div
      className={
        "edge-label nodrag nopan" +
        (animState === "active" ? " edge-label--active" : "") +
        (animState === "future" ? " edge-label--future" : "") +
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
      title={draggable ? "Drag to move; double-click to reset" : undefined}
    >
      {text}
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
  let path: string;
  let labelX: number;
  let labelY: number;
  if (bends.length > 0) {
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
  } else if (pathStyle === "step" || pathStyle === "smoothstep") {
    [path, labelX, labelY] = getSmoothStepPath({
      ...params,
      borderRadius: pathStyle === "step" ? 0 : 8,
      ...(control ? { centerX: control.x, centerY: control.y } : {}),
    });
  } else {
    [path, labelX, labelY] = getBezierPath(params);
  }

  const animState = data?.animState;
  const hovered = data?.hoverState === "hovered";
  // The hovered edge pops (colour, weight, glow); nothing else changes.
  // Dynamic-view animation still dims future steps.
  const emphasis = hovered
    ? {
        stroke: "#1976d2",
        strokeWidth: 2.6,
        filter: "drop-shadow(0 0 3px rgba(25, 118, 210, 0.55))",
      }
    : animState === "active"
      ? { stroke: "#1976d2", strokeWidth: 2.4 }
      : animState === "future"
        ? { opacity: 0.08 }
        : {};
  const edgeStyle = { ...style, ...emphasis };

  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={edgeStyle} />
      {data?.onWaypointDrag
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
            onHoverChange={data.onHoverChange}
            onDrag={data.onLabelDrag}
            onDragEnd={data.onLabelDragEnd}
          />
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
