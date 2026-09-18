import { expect, test, type Page } from "@playwright/test";

/**
 * What the app does before anyone touches it (PP-182).
 *
 * Two bugs that only show on first contact, which is exactly where they
 * cost the most: the app opened on "No view selected" although the
 * server had been sorting the default view first since PP-119, and an
 * error from the live-reload poll rendered inside the sidebar — which
 * auto-collapses below 900px, so a failed reload left a stale diagram on
 * screen saying nothing about why.
 */

/** Load logistics_network, which marks a `default` view in its DSL. */
async function openWorkspace(page: Page) {
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("logistics_network.dsl");
  await page
    .getByRole("button", { name: "logistics_network.dsl", exact: true })
    .click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("");
}

test.describe("first contact", () => {
  test("a workspace opens on its default view", async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 });
    await openWorkspace(page);

    // Nothing clicked in the view list: the app chose.
    await expect(page.locator(".react-flow__node").first()).toBeVisible({
      timeout: 20_000,
    });
    // `default` in logistics_network.dsl marks the landscape, and the
    // server sorts it first.
    await expect(page.locator(".diagram-title")).toHaveText(
      "NorthWind – System Landscape",
    );
    await expect(page.getByText("No view selected")).toHaveCount(0);
  });

  test("a failed reload says so above the diagram", async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 });
    await openWorkspace(page);
    await expect(page.locator(".react-flow__node").first()).toBeVisible({
      timeout: 20_000,
    });

    // Fail the poll rather than editing a file: these specs share one
    // server and `samples/` is read-only to them.
    await page.route("**/api/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          generation: 1,
          error: "Failed to load workspace: unexpected '}'",
          diagnostics: [],
        }),
      }),
    );

    const alerts = page.locator(".alerts");
    await expect(alerts).toBeVisible({ timeout: 20_000 });
    await expect(alerts).toContainText("Live reload paused");

    // Above the body, not inside the sidebar — which is where it used to
    // be, and which is not on screen at all at narrow widths.
    const strip = await alerts.boundingBox();
    const sidebar = await page.locator(".sidebar").boundingBox();
    expect(strip).not.toBeNull();
    expect(strip!.y).toBeLessThan(sidebar!.y);
    expect(strip!.width).toBeGreaterThan(sidebar!.width);
  });

  test("the diagram is still readable while the strip is shown", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1400, height: 900 });
    await openWorkspace(page);
    await expect(page.locator(".react-flow__node").first()).toBeVisible({
      timeout: 20_000,
    });
    await page.route("**/api/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          generation: 1,
          error: "Failed to load workspace",
          diagnostics: [],
        }),
      }),
    );
    await expect(page.locator(".alerts")).toBeVisible({ timeout: 20_000 });
    // The strip explains the stale diagram; it must not replace it.
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
  });
});
