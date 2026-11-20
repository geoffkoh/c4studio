import { expect, test } from "@playwright/test";

/**
 * The workspace logo (PP-237): `logistics_network.dsl`'s `Workspace:Icon`
 * style, a 132 × 36 SVG, drawn before the diagram's title and the
 * workspace's name in the top bar.
 */
test("the logo sits before the title and the workspace's name", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform in its neighbourhood/ }).click();

  const logo = page.locator(".diagram-title img.diagram-title__logo");
  await expect(logo).toHaveAttribute("src", /^data:image\/svg\+xml;base64,/);
  // 28 px tall, as wide as the image's own proportions say.
  const box = await logo.boundingBox();
  const zoom = await page
    .locator(".react-flow__viewport")
    .evaluate((el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).a);
  expect(box).not.toBeNull();
  expect(box!.height / zoom).toBeCloseTo(28, 0);
  expect(box!.width / box!.height).toBeCloseTo(132 / 36, 1);

  // Before the title text, on one row.
  const title = page.locator(".diagram-title");
  await expect(title).toHaveText("Delivery Platform in its neighbourhood");
  const titleBox = await title.boundingBox();
  expect(box!.x).toBeLessThan(titleBox!.x + 4);

  await expect(page.locator(".topbar__logo")).toBeVisible();
});
