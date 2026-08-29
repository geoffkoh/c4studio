import { memo } from "react";
import type { NodeProps } from "reactflow";

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
  label: string;
  colour: string;
  shape: string;
}

export interface ChromeNodeData {
  kind: "title" | "legend";
  title?: string;
  entries?: LegendEntryData[];
}

/** A miniature of the node shape, so the swatch reads as what it explains. */
function Swatch({ entry }: { entry: LegendEntryData }) {
  const { colour, shape } = entry;
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

function ChromeNodeComponent({ data }: NodeProps<ChromeNodeData>) {
  if (data.kind === "title") {
    return <div className="diagram-title">{data.title}</div>;
  }
  return (
    <div className="legend">
      {(data.entries ?? []).map((entry) => (
        <div className="legend__row" key={`${entry.label}-${entry.colour}`}>
          <Swatch entry={entry} />
          <span className="legend__label">{entry.label}</span>
        </div>
      ))}
    </div>
  );
}

export const ChromeNode = memo(ChromeNodeComponent);
