import { expect, test, type Page } from "@playwright/test";

import {
  DESC_MAX_LINES,
  LABEL_MAX_LINES,
  LABEL_SIZE,
  SMALL_SIZE,
  textWidth,
  wrap,
} from "../packages/diagram-core/src/nodeMetrics";

/**
 * `c4 render` breaks a box's text where the canvas does (PP-223).
 *
 * The headless renderer has no DOM, so it wraps from a table of glyph
 * widths measured in this browser. It used to guess a flat 0.55em per
 * character, which broke lines well before the canvas and gave rendered
 * boxes an extra line of description.
 *
 * The table is macOS's system font, so this runs only there — like the
 * screenshot baselines. Elsewhere the stack resolves to another font, and
 * the comparison would be measuring the fonts, not the code.
 */
test.skip(process.platform !== "darwin", "the glyph table is the macOS system font");

type Broken = { text: string; lines: string[]; column: number; plain: boolean };

/** The lines the browser broke each element's text into, the width of the
    column it broke them in, and whether the box is a plain one. */
async function brokenLines(page: Page, selector: string): Promise<Broken[]> {
  return page.locator(selector).evaluateAll((els) =>
    els.map((el) => {
      const node = el.closest(".node");
      const plain =
        !!node && ![...node.classList].some((c) => c.startsWith("node--")) &&
        (node as HTMLElement).offsetWidth === 200;
      const column = (el as HTMLElement).clientWidth;
      const text = el.firstChild;
      if (!text || text.nodeType !== Node.TEXT_NODE) return { text: "", lines: [], column, plain };
      const content = text.textContent ?? "";
      const lines: string[] = [];
      let top: number | null = null;
      let line = "";
      const range = document.createRange();
      for (let i = 0; i < content.length; i += 1) {
        range.setStart(text, i);
        range.setEnd(text, i + 1);
        const rect = range.getClientRects()[0];
        if (rect && top !== null && rect.top > top + 2) {
          lines.push(line.trim());
          line = "";
        }
        if (rect) top = rect.top;
        line += content[i];
      }
      lines.push(line.trim());
      return { text: content, lines: lines.filter(Boolean), column, plain };
    }),
  );
}

async function open(page: Page, file: string, view: RegExp) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill(file);
  await page.getByRole("button", { name: file, exact: true }).click();
  await page.getByRole("button", { name: view }).click();
  await expect(page.locator(".react-flow__node-element").first()).toBeVisible({
    timeout: 20_000,
  });
}

for (const [file, view] of [
  ["logistics_network.dsl", /^NorthWind – System Landscape systemLandscape$/],
  ["logistics_network.dsl", /^Delivery Platform – Containers container$/],
  ["internet_banking.dsl", /Containers container$/],
] as const) {
  test(`${file} ${view.source}: every box breaks where the canvas does`, async ({ page }) => {
    await open(page, file, view);
    // At zoom 1, so the browser lays the text out at its real size.
    const labels = await brokenLines(page, ".react-flow__node-element .node__label");
    const descs = await brokenLines(page, ".react-flow__node-element .node__desc");
    expect(labels.length).toBeGreaterThan(2);
    expect(descs.length).toBeGreaterThan(2);

    // The renderer's column is the canvas's, on a plain 200px box.
    const plain = [...labels, ...descs].filter((b) => b.plain);
    expect(plain.length).toBeGreaterThan(0);
    for (const { column } of plain) expect(column).toBe(textWidth({}));

    let multiLine = 0;
    for (const { text, lines, column } of labels) {
      expect(wrap(text, column, LABEL_SIZE, LABEL_MAX_LINES, true)).toEqual(lines);
    }
    for (const { text, lines, column } of descs) {
      expect(wrap(text, column, SMALL_SIZE, DESC_MAX_LINES)).toEqual(lines);
      if (lines.length > 1) multiLine += 1;
    }
    // Wrapping is what is being compared, so some text must have wrapped.
    expect(multiLine).toBeGreaterThan(0);
  });
}
