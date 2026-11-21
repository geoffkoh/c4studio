import { expect, test, type Page } from "@playwright/test";

/**
 * The logo picker (PP-238). `logistics_network.dsl` draws
 * `brand/northwind-logo.svg` as its `Workspace:Icon`; the card's Workspace
 * row, shown with nothing selected, opens the picker, as a click on the
 * title's logo does. Focusing a row paints it on the title; Esc puts the
 * title back. Writes are answered here and recorded, so nothing reaches
 * the sample: `POST /api/style` and `POST /api/logos/copy`.
 */
interface Recorded {
  styles: Record<string, unknown>[];
  copies: Record<string, unknown>[];
  layouts: string[];
}

async function open(page: Page, details: "open" | "closed"): Promise<Recorded> {
  const recorded: Recorded = { styles: [], copies: [], layouts: [] };
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    recorded.layouts.push(route.request().postData() ?? "");
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/style", async (route) => {
    recorded.styles.push(route.request().postDataJSON());
    return route.fulfill({ json: { files: [], tag: "Workspace:Icon", newTag: false } });
  });
  await page.route("**/api/logos/copy", async (route) => {
    const body = route.request().postDataJSON();
    recorded.copies.push(body);
    return route.fulfill({
      json: { path: `brand/${body.name}`, existing: false, written: !body.dry_run },
    });
  });
  await page.addInitScript((state) => {
    window.localStorage.setItem("c4studio.details", state);
    window.localStorage.removeItem("c4studio.detailsHint");
  }, details);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform in its neighbourhood/ }).click();
  await expect(titleLogo(page)).toHaveAttribute("src", /^data:image\/svg\+xml/, { timeout: 20_000 });
  return recorded;
}

const card = (page: Page) => page.getByRole("complementary", { name: "Details" });
const picker = (page: Page) => page.getByRole("dialog", { name: "Choose the workspace logo" });
const titleLogo = (page: Page) => page.locator(".diagram-title img.diagram-title__logo");

/** Open the picker from the card's row, and wait for its list. */
async function openPicker(page: Page) {
  await card(page).getByRole("group", { name: "Logo" }).getByRole("button").first().click();
  await expect(picker(page).getByRole("listbox", { name: "Images" })).toBeVisible();
}

test("the card's workspace row opens the picker, which previews on the title", async ({ page }) => {
  const recorded = await open(page, "open");
  const row = card(page).getByRole("group", { name: "Logo" });
  await expect(row).toContainText("northwind-logo.svg");

  await row.getByRole("button", { name: /northwind-logo\.svg/ }).click();
  await expect(picker(page)).toBeVisible();
  // Suggested on open: the brand folder, the current logo marked.
  const images = picker(page).getByRole("listbox", { name: "Images" });
  await expect(images.getByRole("option")).toHaveCount(1);
  await expect(images.getByRole("option", { name: "northwind-logo.svg" })).toContainText("current");

  // Search reaches every other image; focusing one paints it on the title.
  await picker(page).getByRole("searchbox", { name: "Search images" }).fill("queue");
  const queue = images.getByRole("option", { name: "Queue.svg" }).first();
  await queue.focus();
  await expect(titleLogo(page)).toHaveAttribute("src", /\/api\/icons\/file\?path=icons%2F/);
  await expect(picker(page).getByLabel("Preview").locator("img")).toHaveAttribute(
    "src",
    /\/api\/icons\/file/,
  );

  // Esc goes back to the card, with the title as the payload drew it.
  await page.keyboard.press("Escape");
  await expect(picker(page)).toHaveCount(0);
  await expect(card(page)).toBeVisible();
  await expect(titleLogo(page)).toHaveAttribute("src", /^data:image\/svg\+xml/);
  expect(recorded.styles).toEqual([]);

  // Enter on a row writes the Workspace:Icon rule.
  await row.getByRole("button", { name: /northwind-logo\.svg/ }).click();
  await picker(page).getByRole("searchbox", { name: "Search images" }).fill("queue");
  await images.getByRole("option", { name: "Queue.svg" }).first().focus();
  await page.keyboard.press("Enter");
  await expect(picker(page)).toHaveCount(0);
  await expect.poll(() => recorded.styles.length).toBe(1);
  expect(recorded.styles[0]).toMatchObject({
    kind: "element",
    property: "icon",
    tag: "Workspace:Icon",
    value: expect.stringMatching(/^icons\/.*Queue.*\.svg$/),
  });
});

test("a click on the title's logo opens the picker, and a closed card closes after", async ({
  page,
}) => {
  const recorded = await open(page, "closed");
  await expect(card(page)).toHaveCount(0);
  // Out from under the toolbar, as in title-click.spec.ts.
  await page.getByRole("button", { name: "zoom out" }).click();
  await page.getByRole("button", { name: "zoom out" }).click();
  await titleLogo(page).click();
  await expect(picker(page)).toBeVisible();
  // A click, not a drag: no move of the title is saved.
  expect(recorded.layouts.filter((body) => body.includes('"title"'))).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(picker(page)).toHaveCount(0);
  await expect(card(page)).toHaveCount(0);
});

test("a file from the machine is copied into brand/ after a confirmation", async ({ page }) => {
  const recorded = await open(page, "open");
  await openPicker(page);
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 1"><rect width="4" height="1"/></svg>';
  await picker(page)
    .getByLabel("Logo file")
    .setInputFiles({ name: "acme.svg", mimeType: "image/svg+xml", buffer: Buffer.from(svg) });

  const confirm = picker(page).getByRole("group", { name: "Copy into the workspace" });
  await expect(confirm).toContainText("Copy acme.svg → brand/acme.svg");
  // Asked, not yet written.
  expect(recorded.copies.map((c) => c.dry_run)).toEqual([true]);
  expect(recorded.styles).toEqual([]);

  await confirm.getByRole("button", { name: "Copy and use" }).click();
  await expect.poll(() => recorded.styles.length).toBe(1);
  expect(recorded.copies.map((c) => c.dry_run)).toEqual([true, false]);
  expect(recorded.styles[0]).toMatchObject({ tag: "Workspace:Icon", value: "brand/acme.svg" });
});

test("a file too large to embed is refused before it is sent", async ({ page }) => {
  const recorded = await open(page, "open");
  await openPicker(page);
  await picker(page).getByLabel("Logo file").setInputFiles({
    name: "poster.png",
    mimeType: "image/png",
    buffer: Buffer.alloc(300 * 1024),
  });
  await expect(picker(page).getByRole("status")).toContainText("at most 256 KB");
  expect(recorded.copies).toEqual([]);
});
