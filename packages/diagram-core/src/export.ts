// Shared PNG/SVG export of the rendered diagram, used by the toolbar
// buttons and the keyboard shortcuts.

import { getRectOfNodes, getTransformForBounds, type Node } from "reactflow";
import { toPng, toSvg } from "html-to-image";

// Padding around the diagram bounds in the exported image, and a 2x pixel
// ratio for crisp PNGs on high-DPI screens.
const EXPORT_MARGIN = 40;
const PNG_SCALE = 2;
const BACKGROUND = "#f5f6f8";

export type ExportFormat = "png" | "svg";

function download(dataUrl: string, filename: string): void {
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  link.click();
}

/**
 * Render the React Flow viewport (nodes, edges, labels — not the
 * controls/minimap overlays) sized to the diagram's bounding box and
 * download it named after the view key.
 */
export async function exportDiagram(
  nodes: Node[],
  viewKey: string,
  format: ExportFormat,
): Promise<void> {
  const viewport = document.querySelector<HTMLElement>(".react-flow__viewport");
  if (!viewport || nodes.length === 0) return;

  const bounds = getRectOfNodes(nodes);
  const width = Math.ceil(bounds.width + 2 * EXPORT_MARGIN);
  const height = Math.ceil(bounds.height + 2 * EXPORT_MARGIN);
  const [x, y, zoom] = getTransformForBounds(bounds, width, height, 1, 1);

  const options = {
    backgroundColor: BACKGROUND,
    width,
    height,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      transform: `translate(${x}px, ${y}px) scale(${zoom})`,
    },
  };

  const dataUrl =
    format === "png"
      ? await toPng(viewport, { ...options, pixelRatio: PNG_SCALE })
      : await toSvg(viewport, options);
  download(dataUrl, `${viewKey}.${format}`);
}
