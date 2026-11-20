import { expect, test } from "@playwright/test";

/**
 * A click on the diagram's title is not a drag (PP-242). React Flow's
 * default drag threshold of 0 turned every click into a zero-length drag:
 * the title was written to the sidecar as moved, after which it stopped
 * following the layout, and the selection was cleared.
 */
test("clicking the title neither pins it nor clears the selection", async ({ page }) => {
  // Saves are answered here, so nothing reaches a sample's sidecar.
  const saved: { chrome?: Record<string, unknown> }[] = [];
  const titleSaves = () => saved.filter((body) => body.chrome?.title !== undefined).length;
  await page.route("**/api/views/*/layout", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    saved.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true } });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform in its neighbourhood/ }).click();

  const node = page.locator(".react-flow__node-element").first();
  await node.click();
  await expect(page.locator(".react-flow__node.selected")).toHaveCount(1);

  // Fitted, the title sits under the toolbar; zooming out about the
  // centre draws it clear.
  await page.getByRole("button", { name: "zoom out" }).click();
  await page.getByRole("button", { name: "zoom out" }).click();
  const title = page.locator(".diagram-title");
  await expect(title).toBeInViewport();
  await page.waitForTimeout(300);
  const before = (await title.boundingBox())!;
  const grip = { x: before.width / 2, y: before.height / 2 };
  await title.click({ position: grip });

  await expect(page.locator(".react-flow__node.selected")).toHaveCount(1);
  expect(await title.boundingBox()).toEqual(before);
  expect(titleSaves()).toBe(0);

  // A real drag still moves it, and is saved.
  await page.mouse.move(before.x + grip.x, before.y + grip.y);
  await page.mouse.down();
  await page.mouse.move(before.x + grip.x + 40, before.y + grip.y + 40, { steps: 5 });
  await page.mouse.up();
  await expect.poll(titleSaves).toBeGreaterThan(0);
});
