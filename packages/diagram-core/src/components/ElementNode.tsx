import { memo, type CSSProperties, type MouseEvent } from "react";
import { Handle, Position, type NodeProps } from "reactflow";

import { metaLine, nodeTooltip } from "../nodeMetrics";

/** The active perspective as it applies to one item (PP-173). */
export interface PerspectiveBadge {
  name: string;
  description: string;
  value: string;
}

/** Colour used when the backend supplies no palette colour for a kind. */
const FALLBACK_COLOR = "#78909c";

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
  /** Set while a perspective is shown and this element carries it. */
  perspective?: PerspectiveBadge;
  /** The element's own properties, without `c4studio.*` settings. */
  properties?: Record<string, string>;
  /** The badge's colour from a `c4studio.badge` style property (PP-208);
      otherwise it takes the element's text colour. */
  badgeColor?: string;
  /** Wired by a surface with a details card: the node then shows a
      properties badge that opens it (PP-207). Absent in exports and the
      headless renderer, which draw the diagram and nothing to click. */
  onShowDetails?: (id: string) => void;
}

/** Hover text for a perspective badge: its name, description and value. */
export function perspectiveHint(perspective: PerspectiveBadge): string {
  const head = perspective.value
    ? `${perspective.name}: ${perspective.value}`
    : perspective.name;
  return perspective.description ? `${head}\n${perspective.description}` : head;
}

/**
 * Black or white, whichever reads on `colour` — by relative luminance, so
 * yellow takes black and navy takes white. `null` for anything but a hex
 * colour, where the caller falls back to the box's own colour.
 */
export function readableOn(colour: string): string | null {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(colour.trim())?.[1];
  if (!hex) return null;
  const full = hex.length === 3 ? [...hex].map((c) => c + c).join("") : hex;
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = parseInt(full.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.179 ? "#1c2530" : "#ffffff";
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
  // Boxes size themselves to their text, so anything still clipped is long
  // prose; hovering is how you read the rest of it.
  const overflow = nodeTooltip(data);
  const drillHint = drillable
    ? `Double-click to open ${data.drillLabel ?? "view"}`
    : null;
  const perspectiveText = data.perspective ? perspectiveHint(data.perspective) : null;
  const hint =
    [perspectiveText, overflow, drillHint].filter(Boolean).join("\n\n") ||
    undefined;

  const handleExpand = (event: MouseEvent) => {
    event.stopPropagation();
    data.onToggleExpand?.(id, true);
  };

  const propertyCount = Object.keys(data.properties ?? {}).length;
  // A solid chip in the text colour, which already contrasts with the box,
  // unless a style chose one; the "i" in whichever of black or white reads
  // on the chip, so a chosen colour can never hide its own glyph (PP-208).
  const chip = data.badgeColor || data.textColor || "#ffffff";
  const showBadge = propertyCount > 0 && Boolean(data.onShowDetails);
  const handleDetails = (event: MouseEvent) => {
    event.stopPropagation();
    data.onShowDetails?.(id);
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
      title={hint}
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
      {data.perspective ? (
        // Absolutely placed on the border, so it never changes the size
        // the layout measured the box at.
        <div className="node__perspective">
          {data.perspective.value || data.perspective.name}
        </div>
      ) : null}
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
      {showBadge ? (
        // `nodrag` so a press here is a click, not the start of a drag;
        // `export-hidden` so a PNG or SVG export leaves it out.
        <button
          className="node__properties nodrag export-hidden"
          style={{ background: chip, color: readableOn(chip) ?? background }}
          title={`${propertyCount} ${propertyCount === 1 ? "property" : "properties"} — show details`}
          aria-label={`Show ${propertyCount} ${propertyCount === 1 ? "property" : "properties"} of ${data.label}`}
          onClick={handleDetails}
          onDoubleClick={(event) => event.stopPropagation()}
        >
          i
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
