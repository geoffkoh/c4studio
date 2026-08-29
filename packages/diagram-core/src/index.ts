/**
 * The renderer-agnostic half of a c4studio diagram.
 *
 * Everything here is driven by the graph JSON the Python side emits
 * (`c4studio.graph.view_graph`) and knows nothing about the web app:
 * no API calls, no app state, no view navigation. That is what lets the
 * same code back the Studio SPA, the headless SVG renderer and the
 * embedded surfaces (Confluence, github.dev).
 *
 * The layout entry point is deliberately **async** even though the dagre
 * implementation is synchronous inside — see the layout-engine decision in
 * `docs/roadmap.md`. Keeping the seam async is what makes swapping in an
 * asynchronous engine (elkjs) a swap rather than a refactor.
 */

export {
  layoutGraph,
  normalizeStoredPositions,
  chromePlacement,
  NODE_WIDTH,
  NODE_HEIGHT,
  ICON_ALLOWANCE,
  type RankDirection,
  type Spacing,
} from "./layout";
export {
  EDGE_PAINT,
  EDGE_COLOUR,
  EDGE_WIDTH,
  EDGE_ARROW_SIZE,
} from "./edgePaint";
export { insertionIndex } from "./waypoints";
export {
  align,
  distribute,
  nudge,
  type AlignMode,
  type Box,
  type DistributeMode,
  type Moves,
} from "./align";
export { exportDiagram, type ExportFormat } from "./export";
export {
  renderSvg,
  type GraphPayload,
  type GraphPayloadEdge,
  type GraphPayloadNode,
  type RenderOptions,
} from "./svg";
export { ElementNode, type ElementNodeData } from "./components/ElementNode";
export { BoundaryNode, type BoundaryNodeData } from "./components/BoundaryNode";
export { FloatingEdge, type FloatingEdgeData } from "./components/FloatingEdge";
export { ExportButtons } from "./components/ExportButtons";
export {
  ChromeNode,
  CHROME_PREFIX,
  isChromeNode,
  type ChromeNodeData,
  type LegendEntryData,
} from "./components/ChromeNode";
