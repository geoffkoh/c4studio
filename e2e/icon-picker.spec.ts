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

test("names and sections are read whole, and shared names say their pack (PP-248)", async ({ page }) => {
  const picker = await browse(page, 1440);
  // One way back, not two.
  await expect(picker.getByRole("button", { name: "Back to the style" })).toBeVisible();
  await expect(picker.getByRole("button", { name: "Change scope" })).toHaveCount(0);
  // The built-in pack's entry carries the tiles' dot, as their key.
  const nav = picker.getByRole("navigation", { name: "Sections" });
  await expect(nav.getByRole("button", { name: /tabler \(built in\)/ }).locator(".icon-picker__builtin-dot")).toHaveCount(1);

  await picker.getByRole("searchbox", { name: "Search icons" }).fill("queue");
  await expect(nav.getByRole("button", { name: /Communication/ })).toBeVisible();
  const clipped = await nav
    .locator(".icon-picker__nav-label")
    .evaluateAll((els) => els.filter((e) => e.scrollWidth > e.clientWidth).map((e) => e.textContent));
  expect(clipped).toEqual([]);

  // A variant's name is shown whole: its suffix is what tells it apart.
  // Variants are folded under their base icon until asked for (PP-247).
  await picker.getByRole("option", { name: /^\d+ more like message$/ }).click();
  const label = picker.getByRole("option", { name: "message-2-x", exact: true }).locator(".icon-picker__label");
  await label.scrollIntoViewIfNeeded();
  expect(await label.evaluate((e) => e.scrollHeight <= e.clientHeight)).toBe(true);

  // Two tiles called Queue say which pack each is from.
  const queues = picker.getByRole("option", { name: "Queue", exact: true });
  await expect(queues).toHaveCount(2);
  await expect(queues.locator(".icon-picker__sublabel")).toHaveText(["basic", "outline"]);
  // A name nothing else shares has no second line.
  await expect(picker.getByRole("option", { name: "stack", exact: true }).locator(".icon-picker__sublabel")).toHaveCount(0);
});

test("the narrow card's menu shows its choice whole (PP-248)", async ({ page }) => {
  const picker = await browse(page, 1024);
  await picker.getByRole("searchbox", { name: "Search icons" }).fill("queue");
  const show = picker.getByRole("combobox", { name: "Show" });
  await expect(show).toHaveValue("home");
  // The chosen option's text against the room the menu gives it, arrow aside.
  const fits = await show.evaluate((select: HTMLSelectElement) => {
    const probe = document.createElement("span");
    probe.style.font = getComputedStyle(select).font;
    probe.style.whiteSpace = "pre";
    probe.textContent = select.selectedOptions[0].textContent;
    document.body.append(probe);
    const text = probe.getBoundingClientRect().width;
    probe.remove();
    return text <= select.clientWidth - 20;
  });
  expect(fits).toBe(true);
});

test("a search folds variants under their icon until asked for (PP-247)", async ({ page }) => {
  const picker = await browse(page, 1440);
  const search = picker.getByRole("searchbox", { name: "Search icons" });
  await search.fill("queue");
  const grid = picker.getByRole("listbox", { name: "Icons" });
  // The count is of every match; the grid draws one tile per icon.
  await expect(picker.getByText(/^\d+ matches$/)).toHaveText(/^1[0-9]{2} matches$/);
  const message = grid.getByRole("option", { name: "message", exact: true });
  await expect(message).toBeVisible();
  await expect(grid.getByRole("option", { name: "message-x", exact: true })).toHaveCount(0);
  const more = grid.getByRole("option", { name: /^\d+ more like message$/ });
  await expect(more).toBeVisible();
  const count = Number((await more.getAttribute("aria-label"))?.split(" ")[0]);

  // By keyboard: Enter on the tile shows them, focus on the first.
  await more.focus();
  await page.keyboard.press("Enter");
  await expect(more).toHaveCount(0);
  await expect(grid.getByRole("option", { name: "message-x", exact: true })).toBeVisible();
  const focused = picker.locator(".icon-picker__tile:focus");
  await expect(focused).toHaveAttribute("aria-label", /^message-/);
  await expect(picker.getByLabel("Preview")).toContainText("message-");
  // They open in the tile's place, straight after their icon (the grid is
  // windowed, so only the rows in view are there to read).
  const labels = await grid.getByRole("option").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
  const at = labels.indexOf("message");
  const after = labels.slice(at + 1, at + 1 + Math.min(count, 8));
  expect(after.length).toBeGreaterThan(0);
  for (const name of after) expect(name).toMatch(/^message-/);

  // A new search folds them again.
  await search.fill("queues");
  await search.fill("queue");
  await expect(grid.getByRole("option", { name: /^\d+ more like message$/ })).toBeVisible();
});

/** Pan the canvas by dragging an empty spot of it, in Pan mode. */
async function pan(page: Page, dx: number, dy: number) {
  const area = await page.locator(".react-flow").boundingBox();
  if (!area) throw new Error("no canvas");
  // An empty spot near the canvas's bottom-left, clear of the zoom buttons.
  const spot = await page.evaluate(
    ({ x0, y0, w, h }) => {
      for (let y = y0 + h - 60; y > y0 + h / 2; y -= 20) {
        for (let x = x0 + 80; x < x0 + w / 3; x += 20) {
          if (document.elementFromPoint(x, y)?.classList.contains("react-flow__pane")) return { x, y };
        }
      }
      return null;
    },
    { x0: area.x, y0: area.y, w: area.width, h: area.height },
  );
  if (!spot) throw new Error("no empty spot on the canvas");
  await page.mouse.move(spot.x, spot.y);
  await page.mouse.down();
  await page.mouse.move(spot.x + dx, spot.y + dy, { steps: 8 });
  await page.mouse.up();
}

const transform = (page: Page) => page.locator(".react-flow__viewport").getAttribute("style");

test("the box being given an icon is panned clear of the browser, and back (PP-249)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page, 1440);
  // Put the box where the widened card will be: right of the canvas.
  const area = (await page.locator(".react-flow").boundingBox())!;
  const at = (await database(page).boundingBox())!;
  await pan(page, area.x + area.width - 200 - (at.x + at.width / 2), 0);
  const was = await transform(page);

  await page.getByLabel("Edit style", { exact: true }).getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  await expect(picker).toBeVisible();
  const cover = (await card(page).boundingBox())!;
  await expect.poll(async () => (await database(page).boundingBox())!.x + (await database(page).boundingBox())!.width).toBeLessThan(cover.x);
  // Whole, give or take a sub-pixel of rounding.
  await expect(database(page)).toBeInViewport({ ratio: 0.99 });

  // Closed untouched, the canvas goes back to where it was.
  await page.keyboard.press("Escape");
  await expect(picker).toBeHidden();
  await expect.poll(() => transform(page)).toBe(was);
});

test("a canvas moved while browsing stays where it was moved (PP-249)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page, 1440);
  const area = (await page.locator(".react-flow").boundingBox())!;
  const at = (await database(page).boundingBox())!;
  await pan(page, area.x + area.width - 200 - (at.x + at.width / 2), 0);

  await page.getByLabel("Edit style", { exact: true }).getByRole("button", { name: "Icon", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Choose an icon" });
  await expect(picker).toBeVisible();
  await expect.poll(async () => (await database(page).boundingBox())!.x).toBeLessThan(area.x + area.width / 2);
  await pan(page, 0, -40);
  const moved = await transform(page);
  await picker.getByRole("button", { name: "Back to the style" }).click();
  await expect(picker).toBeHidden();
  await page.waitForTimeout(300);
  expect(await transform(page)).toBe(moved);
});
