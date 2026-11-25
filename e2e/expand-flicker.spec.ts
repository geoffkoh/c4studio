import { expect, test, type Page } from "@playwright/test";

/**
 * Expanding in place tweens the diagram to its new shape. Each frame must
 * keep what React Flow has measured: a node handed over without its size
 * is hidden until measured again, with its lines, and the canvas blinked
 * on every other frame of the tween.
 */
type Frame = { hidden: number; edges: number; nodes: number };

async function openContainers(page: Page) {
  // Expansion state is per-user UI state on disk; answered here.
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, (route) =>
    route.request().method() === "GET"
      ? route.fallback()
      : route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  await expect(page.locator('[title="Expand components in place"]').first()).toBeVisible({ timeout: 20_000 });
}

/**
 * Settled: a diagram still arriving is not the point. The toggle shows
 * before the first load has finished (13 nodes, then 23), and a freshly
 * loaded diagram is hidden for the one frame it takes to measure.
 */
async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  const state = () =>
    page.evaluate(() => {
      const nodes = [...document.querySelectorAll(".react-flow__node")];
      const hidden = nodes.filter((n) => getComputedStyle(n).visibility === "hidden").length;
      const edges = document.querySelectorAll(".react-flow__edge").length;
      return `${nodes.length}/${hidden}/${edges > 0}`;
    });
  // The same count, nothing hidden and lines drawn, twice running.
  let last = "";
  await expect
    .poll(async () => {
      const now = await state();
      const steady = now === last && now.endsWith("/0/true");
      last = now;
      return steady;
    }, { intervals: [200] })
    .toBe(true);
  return page.locator(".react-flow__node").count();
}

/** Click `toggle` and read every frame for a second after. */
async function framesAfter(page: Page, toggle: string): Promise<Frame[]> {
  await page.evaluate(() => {
    const frames: Frame[] = [];
    (window as unknown as { frames_: Frame[] }).frames_ = frames;
    const start = performance.now();
    const sample = () => {
      const nodes = [...document.querySelectorAll(".react-flow__node")];
      frames.push({
        nodes: nodes.length,
        hidden: nodes.filter((n) => getComputedStyle(n).visibility === "hidden").length,
        edges: document.querySelectorAll(".react-flow__edge").length,
      });
      if (performance.now() - start < 1_000) requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  });
  await page.locator(`[title="${toggle}"]`).first().click();
  await page.waitForTimeout(1_200);
  return page.evaluate(() => (window as unknown as { frames_: Frame[] }).frames_);
}

/**
 * No node that was already on the canvas goes hidden (one entering may
 * wait a frame to be measured), and once the new graph is in, the lines
 * never all vanish.
 */
function expectNoBlink(frames: Frame[], before: number) {
  const changed = frames.findIndex((f) => f.nodes !== before);
  expect(changed, "the graph changed").toBeGreaterThan(-1);
  const entering = (f: Frame) => Math.max(0, f.nodes - before);
  const blinks = frames.filter((f) => f.hidden > entering(f));
  expect(blinks, JSON.stringify(frames)).toEqual([]);
  expect(frames.slice(changed + 2).filter((f) => f.edges === 0), JSON.stringify(frames)).toEqual([]);
}

test("nothing on the canvas blinks while a container expands", async ({ page }) => {
  await openContainers(page);
  const before = await settle(page);
  expectNoBlink(await framesAfter(page, "Expand components in place"), before);
});

test("nothing on the canvas blinks while it collapses again", async ({ page }) => {
  await openContainers(page);
  await page.locator('[title="Expand components in place"]').first().click();
  await expect(page.locator('[title="Collapse back in place"]').first()).toBeVisible();
  const before = await settle(page);
  expectNoBlink(await framesAfter(page, "Collapse back in place"), before);
});
