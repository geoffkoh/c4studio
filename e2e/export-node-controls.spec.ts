import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

/**
 * A node's canvas controls stay out of an exported image (PP-227).
 *
 * The ⊕ that marks a drillable element, the ＋ that expands a container
 * in place and the − that collapses a boundary are for the person using
 * the canvas, not part of the diagram. They are HTML, so the export's
 * filter drops them whole: the exported SVG must not mention them.
 */
const CONTROLS = ["node__drill", "node__expand", "boundary__collapse"];

async function open(page: Page) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  await expect(
    page.locator(".react-flow__node", { hasText: /^Delivery Platform – Containers$/ }),
  ).toBeVisible({ timeout: 20_000 });
}

async function exportedSvg(page: Page): Promise<string> {
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export ▾" }).click();
  await page.getByRole("button", { name: "SVG", exact: true }).click();
  return readFileSync((await (await download).path())!).toString("utf-8");
}

function expectNoControls(svg: string) {
  expect(svg).toContain("react-flow__node");
  for (const control of CONTROLS) expect(svg, control).not.toContain(control);
}

test("the drill and expand marks are not exported", async ({ page }) => {
  await open(page);
  // On screen they exist, so the export is leaving out something real.
  await expect(page.locator(".node__drill").first()).toBeVisible();
  await expect(page.locator(".node__expand").first()).toBeAttached();
  expectNoControls(await exportedSvg(page));
  await expect(page.locator(".node__drill").first()).toBeVisible();
});

test("a boundary's collapse button is not exported", async ({ page }) => {
  await open(page);
  await page.locator(".node__expand").first().click();
  await expect(page.locator(".boundary__collapse").first()).toBeAttached();
  expectNoControls(await exportedSvg(page));
});
