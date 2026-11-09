import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

/**
 * A line's own handles stay out of an exported image (PP-221).
 *
 * The end and run handles of a Step line are hidden on screen by CSS
 * (`opacity: 0` until hover), and the export does not carry the
 * stylesheet: they came out as black circles. Bend-point handles are
 * always visible on screen and came out too. PP-219 had left out only
 * the node connection handles, checked on Bezier lines, which draw none
 * of these.
 */
const HANDLES = ["edge-end-handle", "edge-segment-handle", "edge-waypoint"];

async function open(page: Page, { bend = false } = {}) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  if (bend) {
    // One bend on the first line, as a saved layout would give it.
    await page.route(/\/api\/views\/EcommerceContainers\/graph/, async (route) => {
      const payload = await (await route.fetch()).json();
      for (const edge of payload.edges) delete edge.waypoints;
      payload.edges[0].waypoints = [[-400, -400]];
      await route.fulfill({ json: payload });
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("ecommerce_platform.dsl");
  await page.getByRole("button", { name: "ecommerce_platform.dsl", exact: true }).click();
  await page.getByRole("button", { name: /^E-Commerce – Containers container$/ }).click();
  await expect(page.locator(".react-flow__node-element").first()).toBeVisible({
    timeout: 20_000,
  });
}

/** Every handle the export holds is `display: none` — html-to-image copies
    an <svg> whole, so they are there, but none is drawn. Returns how many
    there were, so a caller can see the check had something to check. */
function hiddenHandles(svg: string): number {
  const found = [...svg.matchAll(/<(?:circle|rect)\b[^>]*>/g)]
    .map((match) => match[0])
    .filter((tag) => HANDLES.some((handle) => tag.includes(handle)));
  for (const tag of found) expect(tag, tag).toContain("display: none");
  return found.length;
}

async function exported(page: Page, format: "PNG" | "SVG"): Promise<Buffer> {
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export ▾" }).click();
  await page.getByRole("button", { name: format, exact: true }).click();
  return readFileSync((await (await download).path())!);
}

test("a Step line's end and run handles are not exported", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Step", exact: true }).click();
  // On screen they exist — so the export is leaving out something real.
  await expect(page.locator(".edge-end-handle").first()).toBeAttached();
  await expect(page.locator(".edge-segment-handle").first()).toBeAttached();
  const svg = (await exported(page, "SVG")).toString("utf-8");
  expect(svg).toContain("react-flow__edge");
  expect(hiddenHandles(svg)).toBeGreaterThan(0);
  // The canvas gets them back: hidden for the export, not for good.
  await expect(page.locator(".edge-end-handle").first()).not.toHaveCSS("display", "none");
  // PNG goes through the same path; check it still produces an image.
  expect((await exported(page, "PNG")).length).toBeGreaterThan(1000);
});

test("a bend point's handle is not exported", async ({ page }) => {
  await open(page, { bend: true });
  await expect(page.locator(".edge-waypoint")).toHaveCount(1);
  const svg = (await exported(page, "SVG")).toString("utf-8");
  expect(svg).toContain("react-flow__edge");
  expect(hiddenHandles(svg)).toBe(1);
  await expect(page.locator(".edge-waypoint")).not.toHaveCSS("display", "none");
});
