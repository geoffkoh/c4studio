import { expect, test, type Page } from "@playwright/test";

/**
 * Choosing an icon from the details card (PP-233), over the sample icons
 * in `samples/icons/basic/`.
 *
 * As for colours, the server plans each edit for real and the save that
 * would follow is intercepted, so the test reads the text the Studio
 * would have written without touching the sample.
 */
async function open(page: Page): Promise<string[]> {
  const saved: string[] = [];
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/source", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    const body = route.request().postDataJSON() as { path: string; content: string };
    saved.push(body.content);
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        path: body.path,
        fingerprint: "test",
        generation: 0,
        reloaded: false,
        error: null,
        diagnostics: [],
        views: [],
      }),
    });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  await expect(
    page.locator(".react-flow__node", { hasText: /^Delivery Platform – Containers$/ }),
  ).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Details" }).click();
  await database(page).click();
  await page.getByRole("button", { name: "Edit style" }).click();
  return saved;
}

const database = (page: Page) =>
  page.locator(".react-flow__node-element", { hasText: "Shipment Database" });

test("searching previews on the canvas, and Escape puts it back", async ({ page }) => {
  await open(page);
  const editor = page.getByLabel("Edit style", { exact: true });
  // The last row is the icon's; the border has none either.
  await expect(editor.locator(".style-editor__origin").last()).toHaveText("none · default");
  await editor.getByRole("button", { name: "Icon", exact: true }).click();

  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  await expect(picker.getByText("Icon · All “Database” (1)")).toBeVisible();
  // Not every icon on open: only those the workspace already uses (the
  // Message Bus style's tinted glyph, PP-234).
  await expect(picker.getByText("In this workspace")).toBeVisible();
  await expect(picker.getByRole("option")).toHaveCount(1);
  await expect(editor).toBeHidden();

  await picker.getByRole("searchbox", { name: "Search icons" }).fill("data");
  // The workspace's own icon first, then the built-in pack's (PP-239).
  await expect(picker.getByRole("option").first()).toHaveAttribute("title", "icons/basic/Database_48.svg");
  await expect(picker.getByRole("option", { name: "database", exact: true })).toBeVisible();
  await picker.getByRole("searchbox", { name: "Search icons" }).press("ArrowDown");
  await expect(picker.getByText("Database — basic/Database_48.svg")).toBeVisible();
  await expect(database(page).locator("img.node__icon")).toHaveAttribute(
    "src",
    /\/api\/icons\/file\?path=icons%2Fbasic%2FDatabase_48\.svg/,
  );

  // Escape steps back to the rows; the card stays open.
  await page.keyboard.press("Escape");
  await expect(picker).toBeHidden();
  await expect(editor).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Details" })).toBeVisible();
  await expect(database(page).locator("img.node__icon")).toHaveCount(0);
});

test("Enter uses an icon for every element with the tag", async ({ page }) => {
  const saved = await open(page);
  const editor = page.getByLabel("Edit style", { exact: true });
  await editor.getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  await picker.getByRole("searchbox", { name: "Search icons" }).fill("func");
  // The library arrives after the picker opens; Enter needs a result.
  await expect(picker.getByRole("option", { name: "Function", exact: true })).toBeVisible();
  await picker.getByRole("searchbox", { name: "Search icons" }).press("Enter");

  await expect(editor.getByRole("status")).toHaveText("Saved to logistics_network.dsl");
  expect(saved).toHaveLength(1);
  // The 48 px drawing, not the 16 px one beside it.
  expect(saved[0]).toMatch(
    /element "Database" \{\s+shape Cylinder\s+icon "icons\/basic\/Function_48\.svg"\s+\}/,
  );
});

test("only this element gets the icon, through a tag of its own", async ({ page }) => {
  const saved = await open(page);
  const editor = page.getByLabel("Edit style", { exact: true });
  await editor.getByRole("radio", { name: "Only this" }).click();
  await editor.getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  await expect(picker.getByText("Icon · Only this")).toBeVisible();
  await picker.getByRole("searchbox", { name: "Search icons" }).fill("server");
  await picker.getByRole("option", { name: "Server", exact: true }).click();
  await picker.getByRole("button", { name: "Use" }).click();

  await expect(editor.getByRole("status")).toHaveText("Saved to logistics_network.dsl");
  expect(saved[0]).toContain('tags "Shipment Database"');
  expect(saved[0]).toMatch(/element "Shipment Database" \{\s+icon "icons\/basic\/Server_48\.svg"\s+\}/);
});

test("a built-in icon previews tinted, and is copied into the workspace when used", async ({
  page,
}) => {
  await open(page);
  // The copy and the edit are answered here: nothing reaches samples/.
  const copies: unknown[] = [];
  const styles: unknown[] = [];
  await page.route("**/api/icons/bundled/copy", async (route) => {
    copies.push(route.request().postDataJSON());
    return route.fulfill({ json: { path: "icons/tabler/cloud-computing.svg", written: true } });
  });
  await page.route("**/api/style", async (route) => {
    styles.push(route.request().postDataJSON());
    return route.fulfill({ json: { files: [], tag: "Database", newTag: false } });
  });
  const editor = page.getByLabel("Edit style", { exact: true });
  await editor.getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  // The pack is offered beside the workspace's own.
  await expect(picker.getByRole("group", { name: "Packs" })).toContainText(/tabler \d{4}/);

  await picker.getByRole("searchbox", { name: "Search icons" }).fill("cloud computing");
  const tile = picker.getByRole("option", { name: "cloud-computing", exact: true });
  await tile.focus();
  await expect(picker.getByText(/cloud-computing — built in, copied to icons\/tabler\//)).toBeVisible();
  // Drawn in currentColor, so previewed in the text colour, not black.
  const preview = database(page).locator(".node__icon--tint");
  await expect(preview).toHaveAttribute("style", /api\/icons\/bundled\/tabler\/cloud-computing\.svg/);

  await picker.getByRole("button", { name: "Use" }).click();
  await expect(picker).toBeHidden();
  expect(copies).toEqual([{ pack: "tabler", name: "cloud-computing" }]);
  await expect.poll(() => styles.length).toBe(1);
  expect(styles[0]).toMatchObject({ property: "icon", value: "icons/tabler/cloud-computing.svg" });
});
