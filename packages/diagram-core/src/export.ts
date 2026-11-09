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
    // Controls drawn on the canvas for the person using it — a node's
    // properties badge (PP-207), the connection handles edges attach to
    // (PP-219) — are not part of the diagram.
    filter: (node: HTMLElement) =>
      !node.classList?.contains("export-hidden") &&
      !node.classList?.contains("react-flow__handle") &&
      !node.classList?.contains("react-flow__resize-control"),
    width,
    height,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      transform: `translate(${x}px, ${y}px) scale(${zoom})`,
    },
  };

  // The filter never sees inside an <svg>: html-to-image copies one whole,
  // without the stylesheet. So a line's bend, end and run handles (PP-221)
  // — drawn in the edges' <svg>, and hidden on screen only by CSS — came
  // out as black circles. An inline style is copied with the element, so
  // hide them that way for the length of the export.
  const hidden = [...viewport.querySelectorAll<SVGElement | HTMLElement>(".export-hidden")];
  const previous = hidden.map((element) => element.style.display);
  for (const element of hidden) element.style.display = "none";
  let dataUrl: string;
  try {
    dataUrl =
      format === "png"
        ? await toPng(viewport, { ...options, pixelRatio: PNG_SCALE })
        : await toSvg(viewport, options);
  } finally {
    hidden.forEach((element, index) => {
      element.style.display = previous[index];
    });
  }
  download(dataUrl, `${viewKey}.${format}`);
}
