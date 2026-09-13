// Relationship line paint, shared by every pane that builds React Flow edges.
//
// The values are applied *inline* rather than left to the vendor
// stylesheet: PNG/SVG export clones the DOM and re-inlines computed styles
// from a property list that html-to-image takes once off <html>, and
// Safari's enumeration for that element carries no SVG paint properties.
// Class-derived `stroke` therefore never reaches the clone and every
// relationship exports as an invisible line — while its HTML label still
// renders, which is worse than the line simply being missing.

import { MarkerType } from "reactflow";

// Defaults live in edgeDefaults.ts, which svg.ts (the headless exporter)
// also imports — one definition rather than two copies kept in step by
// hope. Re-exported here so existing importers are unaffected.
import {
  EDGE_COLOUR,
  EDGE_LINE_STYLE,
  EDGE_WIDTH,
  edgeDashArray,
  type EdgeLineStyle,
} from "./edgeDefaults";

export {
  EDGE_COLOUR,
  EDGE_LINE_STYLE,
  EDGE_WIDTH,
  edgeDashArray,
  type EdgeLineStyle,
};

// Hover emphasis, shared by the live edge component and the edge list so
// the path, the label and the arrowhead marker all pop together.
export const EDGE_HOVER_COLOUR = "#1976d2";
export const EDGE_HOVER_WIDTH = 3.2;

// Arrowhead size, in pixels. reactflow's marker defaults are 12.5 with
// `markerUnits: "strokeWidth"`, which makes the head a multiple of the line
// weight: heads sat at ~12.5px at rest but swelled to ~32px under the
// hover emphasis, so the arrow appeared to change size as the pointer
// moved. Pinning `userSpaceOnUse` decouples the two — the head is this
// size always — and hover stays legible through colour and line weight
// alone. One number to tune if it wants to be bigger.
export const EDGE_ARROW_SIZE = 20;

/** Per-edge overrides from a resolved workspace relationship style. */
export interface EdgePaintOverrides {
  color?: string;
  lineStyle?: string;
  thickness?: number;
  /** Percentage, as Structurizr spells it (0–100). */
  opacity?: number;
}

/**
 * Inline stroke + arrowhead paint for one edge: the workspace style where
 * one matched, the Structurizr-parity defaults everywhere else. The
 * arrowhead marker takes the line's colour, so a recoloured relationship
 * is recoloured whole.
 */
export function edgePaint(overrides: EdgePaintOverrides = {}) {
  const colour = overrides.color || EDGE_COLOUR;
  const width = overrides.thickness ?? EDGE_WIDTH;
  const lineStyle: EdgeLineStyle =
    overrides.lineStyle === "solid" ||
    overrides.lineStyle === "dashed" ||
    overrides.lineStyle === "dotted"
      ? overrides.lineStyle
      : EDGE_LINE_STYLE;
  const dash = edgeDashArray(width, lineStyle);
  return {
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: colour,
      width: EDGE_ARROW_SIZE,
      height: EDGE_ARROW_SIZE,
      markerUnits: "userSpaceOnUse",
    },
    style: {
      stroke: colour,
      strokeWidth: width,
      ...(dash ? { strokeDasharray: dash } : {}),
      ...(overrides.opacity !== undefined
        ? { opacity: overrides.opacity / 100 }
        : {}),
    },
  };
}

/** The default paint — what an unstyled relationship gets. */
export const EDGE_PAINT = edgePaint();

/**
 * `markerEnd` swap for the hovered edge. The arrowhead is an SVG marker
 * whose colour is baked in when the edge is defined, so emphasising the
 * path alone leaves a grey head on a blue line; giving the hovered edge
 * this marker makes React Flow generate (and reuse) the highlighted def.
 */
export const EDGE_HOVER_MARKER = {
  ...EDGE_PAINT.markerEnd,
  color: EDGE_HOVER_COLOUR,
} as const;
