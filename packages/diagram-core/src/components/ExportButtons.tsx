import { useCallback, useState } from "react";
import { useReactFlow } from "reactflow";

import { exportDiagram, type ExportFormat } from "../export";

/**
 * PNG/SVG export buttons for the current diagram (see export.ts for the
 * shared rendering logic; the `p`/`s` keyboard shortcuts use it too).
 *
 * Must be rendered inside the ReactFlow component so `useReactFlow` can
 * read the node bounds.
 */
export function ExportButtons({ viewKey }: { viewKey: string }) {
  const { getNodes } = useReactFlow();
  const [busy, setBusy] = useState<ExportFormat | null>(null);

  const exportAs = useCallback(
    async (format: ExportFormat) => {
      if (busy) return;
      setBusy(format);
      try {
        await exportDiagram(getNodes(), viewKey, format);
      } finally {
        setBusy(null);
      }
    },
    [getNodes, viewKey, busy],
  );

  return (
    <>
      <span className="edge-style__divider" />
      {(["png", "svg"] as const).map((format) => (
        <button
          key={format}
          className="edge-style__option"
          title={`Download this diagram as ${format.toUpperCase()}`}
          disabled={busy !== null}
          onClick={() => void exportAs(format)}
        >
          {busy === format ? "…" : format.toUpperCase()}
        </button>
      ))}
    </>
  );
}
