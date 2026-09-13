// What an unstyled relationship line looks like.
//
// Its own module because the two renderers that need these values cannot
// share a file: `edgePaint.ts` imports `MarkerType` from reactflow, and
// `svg.ts` is the headless exporter, which must not pull reactflow into a
// Node process. They used to keep separate copies with a comment asking
// future editors to change them together — which is a drift waiting to
// happen, and the drift would be invisible: exports would simply stop
// matching the screen.
//
// Nothing here may import reactflow.

export type EdgeLineStyle = "solid" | "dashed" | "dotted";

/**
 * Relationship line colour.
 *
 * **A deliberate divergence from upstream**, which is worth knowing before
 * anyone "corrects" it. Structurizr's light-mode default is `#444444`
 * (`structurizr-ui.js`, `LIGHT_MODE_DEFAULTS.color`), and this used to
 * match it — but at 9.7:1 against white it reads as heavy ink, and
 * relationships are supporting detail rather than the subject of a C4
 * diagram.
 *
 * `#707070` is 4.95:1 on white: clearly lighter, still well above the 3:1
 * WCAG 1.4.11 floor for non-text. Going further washes out fast — `#999999`
 * is 2.85:1 and fails it. A workspace that wants upstream's weight back can
 * say so in its own `styles`, which override this.
 */
export const EDGE_COLOUR = "#707070";

/** Thickness in px. Upstream's default, and unchanged. */
export const EDGE_WIDTH = 2;

/** Upstream's default, and unchanged. */
export const EDGE_LINE_STYLE: EdgeLineStyle = "dashed";

/**
 * Dash pattern for a line style, scaled to the stroke width — the same
 * ratios `svg.ts` uses for element borders, so dashes look alike
 * everywhere. `undefined` means a solid line.
 */
export function edgeDashArray(
  width: number,
  lineStyle: EdgeLineStyle,
): string | undefined {
  if (lineStyle === "dashed") return `${width * 5} ${width * 3}`;
  if (lineStyle === "dotted") return `${width} ${width * 2.5}`;
  return undefined;
}
