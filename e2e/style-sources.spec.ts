import { expect, test, type Page } from "@playwright/test";

/**
 * The details card names the styles that paint a selection (PP-230).
 *
 * In the logistics container view, Shipment Database is matched by the
 * workspace's `element "Database"` rule. Its chip opens the source editor
 * on that rule, the way "Open in Source" opens an element's definition.
 */
async function open(page: Page) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.setViewportSize({ width: 1600, height: 950 });
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

test("a style chip opens the editor at the rule that paints the element", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Details" }).click();
  await page.locator(".react-flow__node-element", { hasText: "Shipment Database" }).click();

  const styles = page.getByLabel("Styles that paint this");
  await expect(styles).toBeVisible();
  const chip = styles.getByRole("button", { name: /^Database/ });
  await expect(chip).toBeVisible();
  await chip.click();

  // The editor opens beside the diagram, flashing the rule's own line.
  const flashed = page.locator(".cm-flash-line");
  await expect(flashed).toBeVisible();
  await expect(flashed).toContainText('element "Database"');
});

test("a line names its relationship style", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Details" }).click();
  // Courier App streams scan events to the Event Bus: an `Async` line.
  // Clicking its label selects it.
  await page.getByText("Streams scan events to").click();
  await expect(
    page.getByLabel("Styles that paint this").getByRole("button", { name: /^Async/ }),
  ).toBeVisible();
});
