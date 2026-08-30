import { memo, type CSSProperties, type MouseEvent } from "react";
import { Handle, Position, type NodeProps } from "reactflow";

/** Colour used when the backend supplies no palette colour for a kind. */
const FALLBACK_COLOR = "#78909c";

/** C4 metadata label per element kind, shown as `[Container: Java]`. */
const KIND_LABELS: Record<string, string> = {
  person: "Person",
  "person-external": "Person",
  system: "Software System",
  "system-external": "Software System",
  container: "Container",
  component: "Component",
  infrastructure: "Infrastructure Node",
  "container-instance": "Container",
  "system-instance": "Software System",
};

export interface ElementNodeData {
  label: string;
  kind: string;
  color: string | null;
  technology: string;
  description: string;
  tags: string[];
  /** Tag-based style overrides from the DSL styles block or a theme. */
  textColor?: string;
  shape?: string;
  /** False when an element style declares `metadata false`. */
  showMetadata?: boolean;
  /** Icon image URL (e.g. a cloud-provider service logo from a theme). */
  icon?: string;
  /** Outline from the element style: "Solid" | "Dashed" | "Dotted". */
  border?: string;
  stroke?: string;
  strokeWidth?: number;
  /** Percentage, as Structurizr spells it. */
  opacity?: number;
  /** Key of the view this node drills into on double-click, if any. */
  drillKey?: string;
  /** Label of the drill target, used for the hover hint. */
  drillLabel?: string;
  /** Whether this container can be expanded in place. */
  expandable?: boolean;
  /** Callback wired by the graph pane to expand/collapse this node. */
  onToggleExpand?: (id: string, expand: boolean) => void;
}

/**
 * The `[Kind: technology]` line, or null when an element style declares
 * `metadata false`. The backend blanks the technology in that case but the
 * kind is composed here, so the whole line has to be dropped explicitly.
 */
function metaLine(data: ElementNodeData): string | null {
  if (data.showMetadata === false) return null;
  const kindLabel = KIND_LABELS[data.kind] ?? data.kind;
  return data.technology ? `[${kindLabel}: ${data.technology}]` : `[${kindLabel}]`;
}

/** CSS modifier class per Structurizr shape; unlisted shapes use the default. */
const SHAPE_CLASSES: Record<string, string> = {
  Box: "node--box",
  Cylinder: "node--cylinder",
  Bucket: "node--cylinder",
  Circle: "node--circle",
  Ellipse: "node--circle",
  Pipe: "node--pipe",
  Hexagon: "node--hexagon",
  Folder: "node--folder",
  WebBrowser: "node--browser",
  Window: "node--browser",
  MobileDevicePortrait: "node--mobile-portrait",
  MobileDeviceLandscape: "node--mobile-landscape",
};

/**
 * Custom React Flow node coloured by its element kind (or the workspace's
 * tag-based styles when defined). People render with the conventional C4
 * silhouette (head circle above the box); styled shapes (cylinder for
 * datastores, box, circle, pipe) render via CSS modifiers. All elements
 * show their `[Kind: technology]` metadata and description. Nodes with a
 * drill target open it on double-click; expandable containers show a ＋
 * control that expands them in place.
 */
function ElementNodeComponent({ id, data }: NodeProps<ElementNodeData>) {
  const background = data.color ?? FALLBACK_COLOR;
  const isPerson =
    data.shape === "Person" ||
    data.shape === "Robot" ||
    (data.shape === undefined && data.kind.startsWith("person"));
  const shapeClass = (!isPerson && SHAPE_CLASSES[data.shape ?? ""]) || "";
  // Outline properties, matching what the SVG emitter draws so the viewer
  // and an exported diagram agree (PP-107). A border is only meaningful
  // with a width, so setting one implies a visible edge.
  const outline: CSSProperties =
    data.border || data.stroke || data.strokeWidth !== undefined
      ? {
          borderStyle: (data.border ?? "Solid").toLowerCase(),
          borderWidth: data.strokeWidth ?? 1,
          borderColor: data.stroke || "rgba(0,0,0,0.35)",
        }
      : {};
  const drillable = Boolean(data.drillKey);
  const expandable = Boolean(data.expandable && data.onToggleExpand);

  const handleExpand = (event: MouseEvent) => {
    event.stopPropagation();
    data.onToggleExpand?.(id, true);
  };

  const box = (
    <div
      className={
        "node" +
        (isPerson ? " node--person" : "") +
        (shapeClass ? ` ${shapeClass}` : "") +
        (drillable ? " node--drillable" : "")
      }
      style={{
        background,
        color: data.textColor || undefined,
        ...outline,
        ...(data.opacity !== undefined && data.opacity < 100
          ? { opacity: Math.max(0, data.opacity) / 100 }
          : {}),
      }}
      title={
        drillable ? `Double-click to open ${data.drillLabel ?? "view"}` : undefined
      }
    >
      <Handle type="target" position={Position.Top} />
      {data.icon ? (
        <img className="node__icon" src={data.icon} alt="" loading="lazy" />
      ) : null}
      <div className="node__label">{data.label}</div>
      {metaLine(data) ? <div className="node__kind">{metaLine(data)}</div> : null}
      {data.description ? (
        <div className="node__desc">{data.description}</div>
      ) : null}
      {drillable ? <div className="node__drill">⊕</div> : null}
      {expandable ? (
        <button
          className="node__expand"
          title="Expand components in place"
          onClick={handleExpand}
          onDoubleClick={(event) => event.stopPropagation()}
        >
          ＋
        </button>
      ) : null}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );

  if (!isPerson) return box;

  return (
    <div className="person">
      <div className="person__head" style={{ background }} />
      {box}
    </div>
  );
}

export const ElementNode = memo(ElementNodeComponent);
