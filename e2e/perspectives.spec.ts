import { expect, test, type Page } from "@playwright/test";

/**
 * The perspective overlay and the legend under it (PP-173, PP-176).
 *
 * Driven through the real UI because the interesting part is the join
 * between three things a type checker cannot see together: the picker's
 * selection, the fading of everything that lacks the perspective, and the
 * legend being rebuilt from what the diagram now shows rather than from
 * the element styles it no longer uses.
 *
 * `logistics_network.dsl` is the sample that carries perspectives —
 * `security` and `capacity` on the Booking API, `reliability` on a
 * relationship — so it is the one workspace here where the picker appears
 * at all.
 */
async function openContainers(page: Page) {
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  // Searching rather than expanding folders: the backend keeps the loaded
  // workspace in AppState, so these specs are not independent of each
  // other — see the note in layout.spec.ts.
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("logistics_network.dsl");
  await page
    .getByRole("button", { name: "logistics_network.dsl", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Delivery Platform – Containers/ })
    .click();
  await expect(page.locator(".legend")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("searchbox", { name: "Search files" }).fill("");
}

const picker = (page: Page) => page.locator("#perspective-picker");

test.describe("perspectives", () => {
  test("the picker offers every perspective name in the model", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1500, height: 950 });
    await openContainers(page);
    await expect(picker(page)).toBeVisible();
    await expect(picker(page).locator("option")).toHaveText([
      "None",
      "capacity",
      "reliability",
      "security",
    ]);
  });

  test("choosing one fades what does not carry it", async ({ page }) => {
    await page.setViewportSize({ width: 1500, height: 950 });
    await openContainers(page);
    await expect(page.locator(".react-flow__node.perspective-faded")).toHaveCount(
      0,
    );
    await picker(page).selectOption("security");
    // Only the Booking API carries `security` in this sample, so the rest
    // of the diagram — and its boundary — recede.
    await expect(
      page.locator(".react-flow__node.perspective-faded").first(),
    ).toBeVisible();
    await expect(page.locator(".node__perspective")).toHaveCount(1);
  });

  test("the legend explains the perspective, not the element styles", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1500, height: 950 });
    await openContainers(page);
    // The style rows the workspace's own `styles` block produces.
    await expect(page.locator(".legend__row")).toContainText(["Person"]);

    await picker(page).selectOption("security");
    // Replaced wholesale: a style row here would be explaining a colour
    // the diagram is no longer painted with.
    await expect(page.locator(".legend__row")).toHaveText([
      "security",
      "Not in security",
    ]);

    await picker(page).selectOption("");
    await expect(page.locator(".legend__row").first()).toHaveText("Person");
  });
});
