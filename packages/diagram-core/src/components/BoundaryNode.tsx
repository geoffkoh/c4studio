import { memo, useCallback, type MouseEvent } from "react";
import { NodeResizer, useStore, useStoreApi, type NodeProps } from "reactflow";

// A resized boundary must always enclose its children (plus breathing room
// and label space) and never collapse below a sensible floor.
const MIN_WIDTH = 220;
const MIN_HEIGHT = 140;
const CHILD_PAD_X = 28;
const CHILD_PAD_BOTTOM = 56;

// The boundary's interior is pointer-transparent (edges behind it must
// stay hoverable), so its interactive surface is the border: four thin
// strips that select on click and act as drag handles.
const HIT_STRIPS: React.CSSProperties[] = [
  { top: 0, left: 0, right: 0, height: 12 },
  { bottom: 0, left: 0, right: 0, height: 12 },
  { top: 0, bottom: 0, left: 0, width: 12 },
  { top: 0, bottom: 0, right: 0, width: 12 },
];

export interface BoundaryNodeData {
  label: string;
  kind: string;
  technology: string;
  /** What the boundary is: "Software System", "Container", "Deployment Node". */
  boundaryLabel?: string;
  /** Fallback used when the backend sends no boundaryLabel. */
  boundaryType: string;
  /** Set when this boundary is an in-place-expanded element. */
  expanded?: boolean;
  /** Key of the parent view to navigate to on double-click, if any. */
  drillKey?: string;
  drillLabel?: string;
  onToggleExpand?: (id: string, expand: boolean) => void;
  /** Called after the user finishes resizing, so the layout can be saved. */
  onGeometryChange?: () => void;
}

/**
 * The dashed C4 boundary that groups the scoped element's children (also
 * used for deployment nodes, the enterprise, and in-place-expanded
 * elements). Sized by the layout (via node style); the label sits
 * bottom-left per Structurizr convention.
 *
 * The interior is pointer-transparent so relationships routed behind the
 * box stay hoverable; the border strips and the label are the interactive
 * surface — click to select (showing resize handles that always enclose
 * the children), drag to move. The view's own boundary drills up a level
 * on double-click; expanded elements show a − control to collapse.
 */
function BoundaryNodeComponent({ id, data, selected }: NodeProps<BoundaryNodeData>) {
  const typeLabel = data.boundaryLabel ?? data.boundaryType;
  const meta = data.technology ? `${typeLabel}: ${data.technology}` : typeLabel;
  const collapsible = Boolean(data.expanded && data.onToggleExpand);
  const store = useStoreApi();

  // Selecting must not depend on React Flow's wrapper hit-testing (the
  // wrapper is pointer-transparent), so the border/label select explicitly.
  const select = useCallback(() => {
    const { addSelectedNodes } = store.getState();
    addSelectedNodes([id]);
  }, [store, id]);

  // Minimum size that keeps every (possibly dragged) child inside.
  const minSize = useStore(
    useCallback(
      (state) => {
        let width = MIN_WIDTH;
        let height = MIN_HEIGHT;
        state.nodeInternals.forEach((node) => {
          if (node.parentNode !== id) return;
          width = Math.max(
            width,
            node.position.x + (node.width ?? 0) + CHILD_PAD_X,
          );
          height = Math.max(
            height,
            node.position.y + (node.height ?? 0) + CHILD_PAD_BOTTOM,
          );
        });
        return { width, height };
      },
      [id],
    ),
    (a, b) => a.width === b.width && a.height === b.height,
  );

  const handleCollapse = (event: MouseEvent) => {
    event.stopPropagation();
    data.onToggleExpand?.(id, false);
  };

  const hint = data.drillKey
    ? `Double-click to go up to ${data.drillLabel ?? "the parent view"}`
    : "Click the border to select and resize";

  return (
    <div className="boundary" title={hint}>
      <NodeResizer
        isVisible={selected}
        minWidth={minSize.width}
        minHeight={minSize.height}
        lineClassName="boundary__resize-line"
        handleClassName="boundary__resize-handle"
        onResizeEnd={() => data.onGeometryChange?.()}
      />
      {HIT_STRIPS.map((style, index) => (
        <div
          key={index}
          className="boundary__hit"
          style={style}
          onClick={select}
        />
      ))}
      <div className="boundary__label" onClick={select}>
        {data.label}
        <span className="boundary__type">[{meta}]</span>
      </div>
      {collapsible ? (
        <button
          className="boundary__collapse"
          title="Collapse back in place"
          onClick={handleCollapse}
          onDoubleClick={(event) => event.stopPropagation()}
        >
          −
        </button>
      ) : null}
    </div>
  );
}

export const BoundaryNode = memo(BoundaryNodeComponent);
