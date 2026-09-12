// Relationship line paint, shared by every pane that builds React Flow edges.
//
// These values match reactflow's own `.react-flow__edge-path` defaults, so
// the diagram looks unchanged on screen. The point is that they are applied
// *inline* rather than left to the vendor stylesheet: PNG/SVG export clones
// the DOM and re-inlines computed styles from a property list that
// html-to-image takes once off <html>, and Safari's enumeration for that
// element carries no SVG paint properties. Class-derived `stroke` therefore
// never reaches the clone and every relationship exports as an invisible
// line — while its HTML label still renders, which is worse than the line
// simply being missing.

import { MarkerType } from "reactflow";

// Heavier than reactflow's 1px default on purpose: relationships are the
// content of a C4 diagram, not chrome, and at 1px they vanished next to
// the node fills. svg.ts (headless export) keeps its own copies of these
// two values — change them together or exports diverge from the screen.
export const EDGE_COLOUR = "#8f8f98";
export const EDGE_WIDTH = 1.8;

// Hover emphasis, shared by the live edge component and the edge list so
// the path, the label and the arrowhead marker all pop together.
export const EDGE_HOVER_COLOUR = "#1976d2";
export const EDGE_HOVER_WIDTH = 3.2;

// Arrowhead size, in pixels. reactflow's marker defaults are 12.5 with
// `markerUnits: "strokeWidth"`, which makes the head a multiple of the line
// weight: heads sat at ~12.5px at rest but swelled to ~32px under the
// hover emphasis (strokeWidth 2.6), so the arrow appeared to change size
// as the pointer moved. Pinning `userSpaceOnUse` decouples the two — the
// head is this size always — and hover stays legible through colour and
// line weight alone. One number to tune if it wants to be bigger.
export const EDGE_ARROW_SIZE = 20;

/** Inline stroke + arrowhead paint to spread onto every edge. */
export const EDGE_PAINT = {
  markerEnd: {
    type: MarkerType.ArrowClosed,
    color: EDGE_COLOUR,
    width: EDGE_ARROW_SIZE,
    height: EDGE_ARROW_SIZE,
    markerUnits: "userSpaceOnUse",
  },
  style: { stroke: EDGE_COLOUR, strokeWidth: EDGE_WIDTH },
} as const;

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
