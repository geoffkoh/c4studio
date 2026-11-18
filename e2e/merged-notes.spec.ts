import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

/**
 * The key to merged lines (PP-229).
 *
 * Collapsing a group merges every line between its members and one other
 * element into a single line. When their descriptions differ it reads
 * "N relationships [n]", and the legend lists what [n] stands for: an
 * exported image has no hover or details card to say it otherwise.
 *
 * Collapsing "Core Services" in the logistics container view merges two
 * such bundles.
 */
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

/** Collapse Core Services; the ids of the lines that came back numbered. */
async function collapse(page: Page): Promise<string[]> {
  const graph = page.waitForResponse(
    (response) => /\/graph\?.*collapse=/.test(response.url()) && response.ok(),
  );
  await page
    .locator(".react-flow__node", { hasText: "Core Services" })
    .getByTitle("Collapse group")
    .click();
  const payload = await (await graph).json();
  return payload.edges.filter((e: { note?: number }) => e.note).map((e: { id: string }) => e.id);
}

test("a collapsed group's merged lines are numbered and keyed in the legend", async ({
  page,
}) => {
  await open(page);
  await expect(page.locator(".legend__notes")).toHaveCount(0);
  const numbered = await collapse(page);
  expect(numbered.length).toBe(2);

  const notes = page.locator(".legend__note");
  await expect(notes).toHaveCount(2);
  await expect(notes.nth(0).locator(".legend__marker")).toHaveText("[1]");
  await expect(notes.nth(1).locator(".legend__marker")).toHaveText("[2]");
  // One line per relationship the marker stands for, source → target.
  await expect(notes.nth(0).locator(".legend__note-line").first()).toContainText(" → ");
  await expect(page.getByText(/relationships \[1\]$/)).toBeAttached();

  // What the export holds: the key is legend chrome, so it is in the image.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export ▾" }).click();
  await page.getByRole("button", { name: "SVG", exact: true }).click();
  const svg = readFileSync((await (await download).path())!).toString("utf-8");
  expect(svg).toContain("legend__note-line");
  expect(svg).toContain("[2]");
});

test("the details card lists what a merged line stands for", async ({ page }) => {
  await open(page);
  const numbered = await collapse(page);
  await page.getByRole("button", { name: "Details" }).click();

  const point = await page.evaluate((ids) => {
    for (const id of ids) {
      const path = document.getElementById(id) as SVGPathElement | null;
      const group = path?.closest(".react-flow__edge");
      const m = path?.getScreenCTM();
      if (!path || !group || !m) continue;
      const length = path.getTotalLength();
      for (let i = 1; i < 40; i++) {
        const p = path.getPointAtLength((length * i) / 40);
        const x = p.x * m.a + p.y * m.c + m.e;
        const y = p.x * m.b + p.y * m.d + m.f;
        const hit = document.elementFromPoint(x, y);
        if (hit && group.contains(hit) && !hit.closest("foreignObject")) return { x, y };
      }
    }
    return null;
  }, numbered);
  expect(point, "no merged line with an uncovered point").not.toBeNull();
  await page.mouse.click(point!.x, point!.y);

  const list = page.getByRole("list", { name: "Relationships this line stands for" });
  await expect(list).toBeVisible();
  expect(await list.getByRole("listitem").count()).toBeGreaterThan(1);
});
