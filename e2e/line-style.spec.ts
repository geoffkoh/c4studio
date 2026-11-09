import { expect, test, type Page } from "@playwright/test";

/**
 * The toolbar's line style is saved per view (PP-222), so `c4 render`
 * draws what the screen shows.
 *
 * Writes are answered here: the server serves `samples/`. A view's saved
 * style is injected into its graph response, as a sidecar would give it.
 */
type Opened = { saves: { url: string; style: unknown }[] };

async function open(page: Page, { saved }: { saved?: string } = {}): Promise<Opened> {
  const opened: Opened = { saves: [] };
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    if (route.request().url().endsWith("/line-style")) {
      const body = route.request().postDataJSON() as { style: unknown };
      opened.saves.push({ url: route.request().url(), style: body.style });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route(/\/api\/views\/EcommerceContainers\/graph/, async (route) => {
    const payload = await (await route.fetch()).json();
    if (saved) payload.lineStyle = saved;
    else delete payload.lineStyle;
    await route.fulfill({ json: payload });
  });
  // This browser's own preference, which a saved style must outrank.
  await page.addInitScript(() => window.localStorage.setItem("c4studio.edgeStyle", "step"));
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
  return opened;
}

/** The highlighted line style; the toolbar's other groups share the class. */
const active = (page: Page) =>
  page
    .locator(".edge-style__option--active")
    .filter({ hasText: /^(Bezier|Straight|Step|Smooth step)$/ });

test("choosing a line style saves it for the view", async ({ page }) => {
  const { saves } = await open(page);
  await page.getByRole("button", { name: "Smooth step", exact: true }).click();
  await expect.poll(() => saves.length).toBe(1);
  expect(saves[0].url).toMatch(/\/api\/views\/EcommerceContainers\/line-style$/);
  expect(saves[0].style).toBe("smoothstep");
  await expect(active(page)).toHaveText("Smooth step");
});

test("a view's saved style outranks this browser's default", async ({ page }) => {
  await open(page, { saved: "straight" });
  await expect(active(page)).toHaveText("Straight");
  // Straight lines carry no curve and no corner.
  const paths = await page
    .locator(".react-flow__edge-path")
    .evaluateAll((els) => els.map((el) => el.getAttribute("d") ?? ""));
  expect(paths.length).toBeGreaterThan(0);
  expect(paths.some((d) => /[CQ]/.test(d))).toBe(false);
});

test("a view with no saved style uses this browser's default", async ({ page }) => {
  const { saves } = await open(page);
  await expect(active(page)).toHaveText("Step");
  // Opening a view saves nothing; only a choice does.
  expect(saves).toEqual([]);
});
