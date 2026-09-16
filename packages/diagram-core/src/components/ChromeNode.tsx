import { memo } from "react";
import type { NodeProps } from "reactflow";

import {
  EDGE_COLOUR,
  EDGE_LINE_STYLE,
  EDGE_WIDTH,
  type EdgeLineStyle,
} from "../edgeDefaults";

/**
 * The diagram's own title and legend, rendered *inside* the React Flow
 * viewport rather than as Panels.
 *
 * That placement is the whole point. `exportDiagram` rasterises
 * `.react-flow__viewport` and crops to the node bounds, so anything drawn
 * as a Panel — the breadcrumb, the mouse-mode switch — is deliberately
 * excluded from PNG/SVG export. A legend exists for people who did not
 * build the diagram, which is mostly people looking at an export, so it
 * has to be a node.
 *
 * These nodes carry no model element. `GraphPane` keeps them out of
 * auto-layout and out of saved layouts; see CHROME_PREFIX.
 */

/** Marks a node as chrome rather than a model element. */
export const CHROME_PREFIX = "__chrome__";

export const isChromeNode = (id: string): boolean => id.startsWith(CHROME_PREFIX);

export interface LegendEntryData {
  /** What the row explains; relationship rows draw a line, not a box. */
  kind?: "element" | "relationship";
  label: string;
  colour?: string;
  /** Element rows only. */
  shape?: string;
  /** Relationship rows only; absent fields fall back to the line defaults. */
  lineStyle?: string;
  thickness?: number;
}

export interface ChromeNodeData {
  kind: "title" | "legend";
  title?: string;
  entries?: LegendEntryData[];
}

/** Widest line a 14px swatch can show and still read as a line. */
const LEGEND_LINE_MAX_WIDTH = 3;

/**
 * Dash patterns at swatch scale, not the edge's width-scaled ones: an
 * 18px line at the real ratios fits a single dash and reads as solid,
 * which is the one thing the row exists to distinguish. Matches
 * `legendLineSwatch` in the headless renderer.
 */
const LEGEND_LINE_DASH: Record<EdgeLineStyle, string | undefined> = {
  dashed: "3 2",
  dotted: "1 2",
  solid: undefined,
};

/**
 * A miniature relationship: the line as styled, with an arrowhead.
 *
 * Only what a style set arrives on the entry, so the defaults come from
 * `edgeDefaults` — the same values the edges themselves are drawn with,
 * which is what makes the row explain the diagram rather than approximate
 * it.
 */
function LineSwatch({ entry }: { entry: LegendEntryData }) {
  const colour = entry.colour || EDGE_COLOUR;
  const width = Math.min(entry.thickness ?? EDGE_WIDTH, LEGEND_LINE_MAX_WIDTH);
  const lineStyle: EdgeLineStyle =
    entry.lineStyle === "solid" ||
    entry.lineStyle === "dashed" ||
    entry.lineStyle === "dotted"
      ? entry.lineStyle
      : EDGE_LINE_STYLE;
  return (
    <svg
      className="legend__swatch legend__swatch--line"
      viewBox="0 0 18 12"
      width="18"
      height="12"
      aria-hidden="true"
    >
      <path
        d="M0 6 H11"
        fill="none"
        stroke={colour}
        strokeWidth={width}
        strokeDasharray={LEGEND_LINE_DASH[lineStyle]}
      />
      <path d="M10 2.5 L17 6 L10 9.5 Z" fill={colour} />
    </svg>
  );
}

/** A miniature of the node shape, so the swatch reads as what it explains. */
function Swatch({ entry }: { entry: LegendEntryData }) {
  const { colour, shape } = entry;
  if (entry.kind === "relationship") {
    return <LineSwatch entry={entry} />;
  }
  if (shape === "Boundary") {
    return <span className="legend__swatch legend__swatch--boundary" />;
  }
  const modifier =
    shape === "Person" || shape === "Robot"
      ? " legend__swatch--person"
      : shape === "Cylinder" || shape === "Bucket" || shape === "Pipe"
        ? " legend__swatch--cylinder"
        : shape === "Circle" || shape === "Ellipse"
          ? " legend__swatch--circle"
          : shape === "Hexagon"
            ? " legend__swatch--hexagon"
            : shape === "Box"
              ? " legend__swatch--box"
              : "";
  return (
    <span
      className={`legend__swatch${modifier}`}
      style={{ background: colour }}
    />
  );
}

// Chrome is draggable in the app (out of the way of a hand-arranged
// diagram) and inert on embedded/export surfaces; the hint is harmless
// where dragging is off.
const MOVE_HINT = "Drag to move; double-click to reset";

function ChromeNodeComponent({ data }: NodeProps<ChromeNodeData>) {
  if (data.kind === "title") {
    return (
      <div className="diagram-title" title={MOVE_HINT}>
        {data.title}
      </div>
    );
  }
  return (
    <div className="legend" title={MOVE_HINT}>
      {(data.entries ?? []).map((entry, index) => (
        // Rows can share a label and colour and differ only by shape,
        // border or kind, so the position is part of the identity.
        <div className="legend__row" key={`${entry.label}-${index}`}>
          <Swatch entry={entry} />
          <span className="legend__label">{entry.label}</span>
        </div>
      ))}
    </div>
  );
}

export const ChromeNode = memo(ChromeNodeComponent);
