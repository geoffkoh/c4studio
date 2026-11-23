import { expect, test, type Page } from "@playwright/test";

/**
 * Choosing an icon from the details card (PP-233), over the sample icons
 * in `samples/icons/basic/`.
 *
 * As for colours, the server plans each edit for real and the save that
 * would follow is intercepted, so the test reads the text the Studio
 * would have written without touching the sample.
 */
async function open(page: Page, width = 1440): Promise<string[]> {
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
  await page.setViewportSize({ width, height: 900 });
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
  // Something to browse before typing (PP-244): what the workspace uses
  // (the Message Bus style's tinted glyph, PP-234), then suggestions.
  await expect(picker.getByText("Used in this workspace")).toBeVisible();
  await expect(picker.getByText("Suggested · Data")).toBeVisible();
  await expect(picker.getByRole("option", { name: "database", exact: true })).toBeVisible();
  await expect(editor).toBeHidden();

  await picker.getByRole("searchbox", { name: "Search icons" }).fill("data");
  // The workspace's own icon first, then the built-in pack's (PP-239).
  await expect(picker.getByRole("option").first()).toHaveAttribute("title", "icons/basic/Database_48.svg");
  await expect(picker.getByRole("option", { name: "database", exact: true })).toBeVisible();
  await picker.getByRole("searchbox", { name: "Search icons" }).press("ArrowDown");
  await expect(picker.getByLabel("Preview")).toContainText("basic/Database_48.svg");
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

test("a new search lets go of the icon focused in the old one (PP-245)", async ({ page }) => {
  const saved = await open(page);
  const editor = page.getByLabel("Edit style", { exact: true });
  await editor.getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  const search = picker.getByRole("searchbox", { name: "Search icons" });
  await search.fill("func");
  await expect(picker.getByRole("option", { name: "Function", exact: true })).toBeVisible();
  await search.press("ArrowDown");
  await expect(picker.getByLabel("Preview")).toContainText("Function_48.svg");

  // Function is not among these: nothing is focused, nothing previewed.
  await search.fill("server");
  await expect(picker.getByRole("option").first()).toHaveAttribute("title", "icons/basic/Server_48.svg");
  await expect(picker.getByLabel("Preview")).toHaveCount(0);
  await expect(picker.getByRole("button", { name: "Use", exact: true })).toBeDisabled();
  await expect(database(page).locator("img.node__icon")).toHaveCount(0);

  // Enter takes the top of what is shown, not the icon left behind.
  await search.press("Enter");
  await expect(editor.getByRole("status")).toHaveText("Saved to logistics_network.dsl");
  expect(saved[0]).toMatch(/icon "icons\/basic\/Server_48\.svg"/);
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
  await expect(picker.getByRole("navigation", { name: "Sections" })).toContainText(/tabler \(built in\)\s*\d{4}/);

  await picker.getByRole("searchbox", { name: "Search icons" }).fill("cloud computing");
  const tile = picker.getByRole("option", { name: "cloud-computing", exact: true });
  await tile.focus();
  await expect(picker.getByLabel("Preview")).toContainText(
    "Built in: Use copies it to icons/tabler/cloud-computing.svg with its LICENSE",
  );
  // Drawn in currentColor, so previewed in the text colour, not black.
  const preview = database(page).locator(".node__icon--tint");
  await expect(preview).toHaveAttribute("style", /api\/icons\/bundled\/tabler\/cloud-computing\.svg/);

  await picker.getByRole("button", { name: "Copy & use" }).click();
  await expect(picker).toBeHidden();
  expect(copies).toEqual([{ pack: "tabler", name: "cloud-computing" }]);
  await expect.poll(() => styles.length).toBe(1);
  expect(styles[0]).toMatchObject({ property: "icon", value: "icons/tabler/cloud-computing.svg" });
});

test("a workspace icon previews tinted when the server says the diagram will tint it (PP-246)", async ({
  page,
}) => {
  // The server reads each SVG; here it says outline/ paints in currentColor,
  // a folder no built-in pack is named after.
  await page.route("**/api/icons", async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { icons: { path: string; tint: boolean }[] };
    for (const icon of body.icons) icon.tint = icon.path.endsWith("outline/Queue.svg");
    return route.fulfill({ response, json: body });
  });
  await open(page);
  await page.getByLabel("Edit style", { exact: true }).getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  await picker.getByRole("searchbox", { name: "Search icons" }).fill("queue");

  await picker.getByRole("option").and(picker.locator('[title="icons/outline/Queue.svg"]')).focus();
  await expect(database(page).locator(".node__icon--tint")).toHaveAttribute("style", /outline%2FQueue\.svg/);
  await picker.getByRole("option").and(picker.locator('[title="icons/basic/Queue_48.svg"]')).focus();
  await expect(database(page).locator("img.node__icon")).toHaveAttribute("src", /basic%2FQueue_48\.svg/);
  await expect(database(page).locator(".node__icon--tint")).toHaveCount(0);
});

const card = (page: Page) => page.getByRole("complementary", { name: "Details" });

async function browse(page: Page, width: number) {
  await open(page, width);
  await page.getByLabel("Edit style", { exact: true }).getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  await expect(picker.getByRole("listbox", { name: "Icons" }).getByRole("option").first()).toBeVisible();
  return picker;
}

test("the card widens into a browser, with sections beside the grid", async ({ page }) => {
  const picker = await browse(page, 1440);
  // Half the canvas, capped: 560 px of a 1140 px canvas.
  const box = await card(page).boundingBox();
  expect(box?.width).toBeGreaterThan(550);
  expect(box?.width).toBeLessThanOrEqual(562);
  await expect(picker.getByRole("navigation", { name: "Sections" })).toBeVisible();
  await expect(picker.getByRole("combobox", { name: "Show" })).toHaveCount(0);
  // Tiles are labelled, at least four to a row.
  await picker.getByRole("searchbox", { name: "Search icons" }).fill("user");
  const tiles = picker.getByRole("option");
  await expect(tiles.first().locator(".icon-picker__label")).toBeVisible();
  const first = await tiles.nth(0).boundingBox();
  const fourth = await tiles.nth(3).boundingBox();
  expect(fourth?.y).toBe(first?.y);
});

test("a whole pack scrolls, drawing only the rows in view", async ({ page }) => {
  const picker = await browse(page, 1440);
  await picker.getByRole("navigation", { name: "Sections" }).getByRole("button", { name: /tabler \(built in\)/ }).click();
  await expect(picker.getByText("Arrows", { exact: true }).first()).toBeVisible();
  // Thousands of icons, a screenful of tiles in the DOM.
  expect(await picker.getByRole("option").count()).toBeLessThan(200);
  await picker.getByRole("option").first().focus();
  await page.keyboard.press("End");
  // Zodiac is the last category: the end of the pack, hundreds of rows down.
  const last = picker.locator(".icon-picker__tile:focus");
  await expect(last).toHaveAttribute("aria-label", /^zodiac-/);
  await expect(last).toBeInViewport();
  const name = await last.getAttribute("aria-label");
  await expect(picker.getByLabel("Preview")).toContainText(name ?? "");
  // The canvas previews the tile reached.
  await expect(database(page).locator(".node__icon--tint")).toHaveAttribute(
    "style",
    new RegExp(`tabler/${name}\\.svg`),
  );
  expect(await picker.getByRole("option").count()).toBeLessThan(200);
});

test("search knows the words people use, and leaves letters out", async ({ page }) => {
  const picker = await browse(page, 1440);
  const search = picker.getByRole("searchbox", { name: "Search icons" });
  await search.fill("db");
  const names = async () => picker.getByRole("option").evaluateAll((els) => els.slice(0, 4).map((e) => e.getAttribute("aria-label")));
  await expect.poll(names).toContain("database");
  await search.fill("api");
  await expect(picker.getByRole("option").first()).toHaveAttribute("aria-label", "api");
  await expect(picker.getByRole("option", { name: "hexagon-letter-a", exact: true })).toHaveCount(0);
});

test("a narrow card swaps the sections for a dropdown", async ({ page }) => {
  const picker = await browse(page, 1024);
  await expect(picker.getByRole("navigation", { name: "Sections" })).toHaveCount(0);
  const show = picker.getByRole("combobox", { name: "Show" });
  await expect(show).toBeVisible();
  await show.selectOption("pack:tabler");
  await expect(picker.getByText("Arrows", { exact: true }).first()).toBeVisible();
});
