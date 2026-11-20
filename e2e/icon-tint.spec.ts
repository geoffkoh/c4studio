import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

/**
 * `c4studio.iconTint` (PP-234): `logistics_network.dsl`'s Message Bus style
 * draws a one-colour outline glyph in the box's text colour, as a mask
 * over a fill, rather than as an image that would stay black.
 */
test("a tinted icon is its image as a mask over the text colour", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();

  const node = page.locator(".react-flow__node-element", { hasText: "Event Bus" });
  const icon = node.locator(".node__icon--tint");
  await expect(icon).toBeVisible();
  await expect(node.locator("img.node__icon")).toHaveCount(0);

  const style = await icon.evaluate((el) => {
    const css = getComputedStyle(el);
    return { fill: css.backgroundColor, mask: css.maskImage || css.webkitMaskImage };
  });
  expect(style.fill).toBe("rgb(255, 255, 255)");
  expect(style.mask).toMatch(/^url\("data:image\/svg\+xml/);
  const box = (await icon.boundingBox())!;
  expect(box.width).toBeGreaterThan(0);

  // An untinted icon is still a plain image.
  const plain = page.locator(".react-flow__node-element img.node__icon");
  for (const handle of await plain.all()) {
    await expect(handle).not.toHaveClass(/node__icon--tint/);
  }
});

test("the Studio's SVG export keeps the tint", async ({ page }) => {
  // Saves are answered here, so nothing reaches a sample's sidecar.
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  // Laid out, as the export test waits: an export taken mid-layout
  // copies nodes React Flow has not yet shown.
  await expect(
    page.locator(".react-flow__node", { hasText: /^Delivery Platform – Containers$/ }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".node__icon--tint")).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export ▾" }).click();
  await page.getByRole("button", { name: "SVG", exact: true }).click();
  const svg = readFileSync((await (await download).path())!).toString("utf-8");
  // html-to-image inlines computed styles: the tinted span keeps its mask.
  const span = svg.match(/<span[^>]*node__icon--tint[^>]*>/)?.[0] ?? "";
  expect(span).toMatch(/\bmask(-image)?: url\(&quot;data:image\/svg\+xml/);
  expect(span).toMatch(/\bvisibility: visible\b/);
});
