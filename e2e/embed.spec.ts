import { expect, test, type Page } from "@playwright/test";

/**
 * Embed mode (`?embed=1`): the diagram and a view picker, nothing else.
 *
 * What the VS Code preview loads. The app chrome it removes — a 41px
 * topbar and a 26px rail — was never the expensive part. The canvas's own
 * floating panels were: measured at 400px, `.edge-style` is 725px wide and
 * clipped to x = −340 by `overflow: hidden` (so Mouse/Pan/Select cannot be
 * clicked at all), and the minimap is 200×150 thumbnailing a diagram
 * `fitView` has already fitted entirely on screen.
 *
 * Full mode: 49,322px² of the canvas sits under a panel. Embed: 2,106.
 */

/**
 * Land on a diagram, with a workspace loaded server-side.
 *
 * Embed mode can only show what the server already holds — it has no file
 * tree to load one with. That is not a limitation of the test: the
 * extension spawns `c4 webapp <file>`, so a workspace is always loaded by
 * the time the webview opens. Loading one here through the ordinary UI
 * reproduces that, and is why every embed assertion below has to go
 * through the full app once first.
 */
async function openDiagram(page: Page, embed: boolean) {
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("internet_banking");
  await page
    .getByRole("button", { name: "internet_banking.dsl", exact: true })
    .click();
  await expect(page.locator(".react-flow__node").first()).toBeVisible({
    timeout: 15_000,
  });
  if (embed) {
    await page.goto("/?embed=1");
    await expect(page.locator(".react-flow__node").first()).toBeVisible({
      timeout: 15_000,
    });
  }
}

test.describe("embed mode", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 400, height: 900 });
  });

  test("a view opens by itself, with no sidebar to choose from", async ({
    page,
  }) => {
    // The blocker. Without this the app shows "No view selected — Choose a
    // renderable view from the sidebar", and embed mode has no sidebar, so
    // it was a dead end rather than a poor first impression. The server has
    // sorted the DSL's `default` first since PP-119; nothing read it.
    await openDiagram(page, true);

    await expect(page.locator(".graph")).toBeVisible();
    await expect(page.locator("text=No view selected")).toHaveCount(0);
  });

  test("the app frame is gone and the canvas takes the window", async ({
    page,
  }) => {
    await openDiagram(page, true);

    await expect(page.locator(".topbar")).toHaveCount(0);
    await expect(page.locator(".rail--left")).toHaveCount(0);
    const graph = await page.locator(".graph").boundingBox();
    expect(graph!.width).toBe(400);
    expect(graph!.height).toBe(900);
  });

  test("the panels that overlay the canvas are gone", async ({ page }) => {
    await openDiagram(page, true);

    await expect(page.locator(".edge-style")).toHaveCount(0);
    await expect(page.locator(".react-flow__minimap")).toHaveCount(0);
    // Zoom stays — it earns its 26px. The padlock does not: there is
    // nothing to lock on a glance surface, and it is a quarter of the
    // cluster's height (108 → 81).
    const controls = await page.locator(".react-flow__controls").boundingBox();
    expect(controls!.height).toBeLessThan(100);
  });

  test("the view picker is present and persistent", async ({ page }) => {
    await openDiagram(page, true);

    const picker = page.locator(".breadcrumb__picker");
    await expect(picker).toBeVisible();
    // Only renderable views: offering an `image` view opens an empty panel.
    const options = await picker.locator("option").allTextContents();
    expect(options.length).toBeGreaterThan(1);

    // Switching redraws, rather than needing the sidebar that is not there.
    const before = await page.locator(".react-flow__node").count();
    await picker.selectOption({ index: 1 });
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
    expect(await page.locator(".react-flow__node").count()).toBeGreaterThan(0);
    expect(before).toBeGreaterThan(0);
  });

  test("full mode is untouched", async ({ page }) => {
    // Embed is opt-in. Everything above must be false without the param,
    // or this is not a mode, it is a regression.
    await openDiagram(page, false);

    await expect(page.locator(".topbar")).toBeVisible();
    await expect(page.locator(".edge-style")).toHaveCount(1);
    await expect(page.locator(".react-flow__minimap")).toHaveCount(1);
    await expect(page.locator(".breadcrumb__picker")).toHaveCount(0);
  });
});
