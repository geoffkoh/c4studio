import { Panel } from "reactflow";

import type { AlignMode, DistributeMode } from "@c4studio/diagram-core";

/**
 * Align and distribute controls, shown only while several nodes are
 * selected.
 *
 * React Flow gives multi-selection (Shift+drag, Cmd/Ctrl+click) and moves a
 * selection together, but offers nothing for tidying one up — which is the
 * main reason to select several nodes on a diagram.
 *
 * It sits directly below the mouse/edge toolbar, right-aligned to stack
 * with it: those two plus the breadcrumb already fill the top row on a
 * narrow window. Being contextual, this second row exists only while
 * something is selected. Grouped with titles and dividers to match the
 * toolbar above it.
 */

interface SelectionToolsProps {
  count: number;
  onAlign: (mode: AlignMode) => void;
  onDistribute: (mode: DistributeMode) => void;
}

const ALIGNMENTS: { mode: AlignMode; glyph: string; label: string }[] = [
  { mode: "left", glyph: "⇤", label: "Align left edges" },
  { mode: "center", glyph: "↔", label: "Align horizontal centres" },
  { mode: "right", glyph: "⇥", label: "Align right edges" },
  { mode: "top", glyph: "⤒", label: "Align top edges" },
  { mode: "middle", glyph: "↕", label: "Align vertical centres" },
  { mode: "bottom", glyph: "⤓", label: "Align bottom edges" },
];

const DISTRIBUTIONS: {
  mode: DistributeMode;
  glyph: string;
  label: string;
}[] = [
  { mode: "horizontal", glyph: "⇹", label: "Space evenly across" },
  { mode: "vertical", glyph: "⇳", label: "Space evenly down" },
];

export function SelectionTools({
  count,
  onAlign,
  onDistribute,
}: SelectionToolsProps) {
  if (count < 2) return null;
  return (
    <Panel position="top-right" className="selection-tools">
      <span className="selection-tools__count">{count} selected</span>
      <span className="selection-tools__sep" />
      <span className="selection-tools__title">Align</span>
      {ALIGNMENTS.map((item) => (
        <button
          key={item.mode}
          className="selection-tools__button"
          title={item.label}
          aria-label={item.label}
          onClick={() => onAlign(item.mode)}
        >
          {item.glyph}
        </button>
      ))}
      <span className="selection-tools__sep" />
      <span className="selection-tools__title">Space</span>
      {DISTRIBUTIONS.map((item) => (
        <button
          key={item.mode}
          className="selection-tools__button"
          // Distributing two boxes is meaningless: the outermost stay put.
          disabled={count < 3}
          title={count < 3 ? `${item.label} (needs three)` : item.label}
          aria-label={item.label}
          onClick={() => onDistribute(item.mode)}
        >
          {item.glyph}
        </button>
      ))}
    </Panel>
  );
}
