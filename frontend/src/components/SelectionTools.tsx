import { Panel } from "reactflow";

import type { AlignMode, DistributeMode } from "@pystructurizr/diagram-core";

/**
 * Align and distribute controls, shown only while several nodes are
 * selected.
 *
 * React Flow gives multi-selection (Shift+drag, Cmd/Ctrl+click) and moves a
 * selection together, but offers nothing for tidying one up — which is the
 * main reason to select several nodes on a diagram.
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
    <Panel position="top-center" className="selection-tools">
      <span className="selection-tools__count">{count} selected</span>
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
