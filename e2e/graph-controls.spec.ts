import { expect, test, type Page } from "@playwright/test";

/**
 * The canvas's top-left controls (PP-206): breadcrumb, then the toolbar,
 * then the selection's tools, as one column.
 *
 * They used to share a row — breadcrumb left, toolbar right — and the
 * toolbar, with no width limit of its own, covered the breadcrumb on a
 * drill-down deep enough to need one. A component view is the deepest
 * trail a sample has: landscape › context › containers › components.
 *
 * Layout writes are answered here because the server serves `samples/`.
 */
async function open(page: Page, { width = 1440, height = 900, details = "closed" } = {}) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.addInitScript((state) => {
    window.localStorage.setItem("c4studio.details", state);
  }, details);
  await page.setViewportSize({ width, height });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Routing Engine – Components/ }).click();
  await expect(page.locator(".react-flow__node-element").first()).toBeVisible({
    timeout: 20_000,
  });
}

type Box = { x: number; y: number; width: number; height: number };

const overlaps = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

test.describe("canvas controls", () => {
  for (const [width, height, details] of [
    [1440, 900, "closed"],
    [1440, 900, "open"],
    [1024, 768, "open"],
    [700, 800, "closed"],
  ] as const) {
    test(`at ${width}px, card ${details}: the breadcrumb is uncovered and the toolbar under it`, async ({
      page,
    }) => {
      await open(page, { width, height, details });
      const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
      await expect(crumbs).toBeVisible();
      // Every crumb is there; the current one is the view on screen.
      await expect(crumbs.locator(".breadcrumb__crumb")).toHaveCount(4);
      await expect(crumbs.locator(".breadcrumb__crumb--current")).toHaveText(/^Routing Engine/);

      const crumbBox = (await crumbs.boundingBox())!;
      const toolbar = (await page.locator(".edge-style").boundingBox())!;
      const canvas = (await page.locator(".graph").boundingBox())!;
      expect(overlaps(crumbBox, toolbar)).toBe(false);
      expect(toolbar.y).toBeGreaterThanOrEqual(crumbBox.y + crumbBox.height);
      // Both start at the canvas's left margin and stay inside it.
      expect(Math.abs(crumbBox.x - toolbar.x)).toBeLessThan(1);
      for (const box of [crumbBox, toolbar]) {
        expect(box.x).toBeGreaterThanOrEqual(canvas.x);
        expect(box.x + box.width).toBeLessThanOrEqual(canvas.x + canvas.width);
      }

      // What the breadcrumb covers is canvas no longer: the element under
      // the crumb's centre is the crumb itself.
      const hit = await page.evaluate(
        ({ x, y }) => !!document.elementFromPoint(x, y)?.closest(".breadcrumb"),
        { x: crumbBox.x + crumbBox.width / 2, y: crumbBox.y + crumbBox.height / 2 },
      );
      expect(hit).toBe(true);

      const card = page.getByRole("complementary", { name: "Details" });
      if (details === "open") {
        const cardBox = (await card.boundingBox())!;
        expect(overlaps(cardBox, crumbBox)).toBe(false);
        expect(overlaps(cardBox, toolbar)).toBe(false);
      }
    });
  }

  test("selection tools sit under the toolbar", async ({ page }) => {
    await open(page);
    // Shift+drag a selection box over the whole canvas, below the controls.
    const pane = (await page.locator(".react-flow__pane").boundingBox())!;
    await page.keyboard.down("Shift");
    await page.mouse.move(pane.x + 20, pane.y + 160);
    await page.mouse.down();
    await page.mouse.move(pane.x + pane.width - 20, pane.y + pane.height - 20, { steps: 10 });
    await page.mouse.up();
    await page.keyboard.up("Shift");
    const tools = page.locator(".selection-tools");
    await expect(tools).toBeVisible();
    const toolbar = (await page.locator(".edge-style").boundingBox())!;
    const box = (await tools.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(toolbar.y + toolbar.height);
    expect(Math.abs(box.x - toolbar.x)).toBeLessThan(1);
  });

  test("View ▾ holds the toggles, stays open for several, and Escape closes it", async ({
    page,
  }) => {
    await open(page);
    const menu = page.getByRole("group", { name: "View" });
    await expect(menu).toHaveCount(0);
    const button = page.getByRole("button", { name: "View ▾" });
    await button.click();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    for (const name of ["Hover", "Animate", "Snap"]) {
      await expect(menu.getByRole("button", { name })).toHaveAttribute("aria-pressed", /true|false/);
    }
    const snap = menu.getByRole("button", { name: "Snap" });
    const before = await snap.getAttribute("aria-pressed");
    await snap.click();
    await expect(snap).not.toHaveAttribute("aria-pressed", before!);
    // Still open: it is a set of toggles, not one action.
    await expect(menu).toBeVisible();
    await snap.click();

    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(button).toHaveAttribute("aria-expanded", "false");
  });

  test("Export ▾ closes once a format is chosen, and on an outside click", async ({ page }) => {
    await open(page);
    const menu = page.getByRole("group", { name: "Export" });
    await page.getByRole("button", { name: "Export ▾" }).click();
    await expect(menu.getByRole("button", { name: "PNG" })).toBeVisible();
    await page.locator(".react-flow__pane").click({ position: { x: 400, y: 500 } });
    await expect(menu).toHaveCount(0);

    await page.getByRole("button", { name: "Export ▾" }).click();
    const download = page.waitForEvent("download");
    await menu.getByRole("button", { name: "PNG" }).click();
    await expect(menu).toHaveCount(0);
    expect((await download).suggestedFilename()).toMatch(/\.png$/);
  });
});
