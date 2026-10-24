import { expect, test } from "@playwright/test";

/**
 * Switching views while a layout tween is running (PP-200).
 *
 * Expanding an element in place re-fetches the same view and tweens the
 * nodes to their new places, one `setNodes` per animation frame. A view
 * switch replaced the nodes without cancelling that tween, so its
 * remaining frames painted the *old* view over the new one: the
 * breadcrumb named the view you clicked and the canvas showed the one you
 * left. CI found it twice, as specs whose opener clicked a view while the
 * default view was still settling.
 */
test("a view switch mid-tween shows the view that was chosen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1500, height: 950 });
  // Expanding persists to the sample's layout sidecar, and this suite
  // serves `samples/` — the developer's own working copy. Answer the
  // writes here so the test leaves no arrangement behind (an early run of
  // this spec did, and every later run then found nothing to expand).
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, (route) =>
    route.request().method() === "GET"
      ? route.fallback()
      : route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("logistics_network.dsl");
  await page
    .getByRole("button", { name: "logistics_network.dsl", exact: true })
    .click();

  const title = (text: RegExp) =>
    page.locator(".react-flow__node", { hasText: text });
  const landscape = title(/^NorthWind – System Landscape$/);
  const containers = title(/^Delivery Platform – Containers$/);
  await expect(landscape).toBeVisible({ timeout: 20_000 });

  // Expand the platform in place: a same-view re-fetch, so a tween. Its
  // children enter with `node-enter`, which is the sign it is running.
  await page
    .locator(".react-flow__node", { hasText: "Delivery Platform" })
    .getByRole("button", { name: "＋" })
    .click();
  await expect(page.locator(".react-flow__node.node-enter").first()).toBeAttached();

  // Switch inside the tween's window.
  await page
    .getByRole("button", { name: /Delivery Platform – Containers/ })
    .click();

  await expect(containers).toBeVisible();
  // Long enough for any tween left running to have finished painting.
  await page.waitForTimeout(800);
  await expect(containers).toBeVisible();
  await expect(landscape).toHaveCount(0);
});
