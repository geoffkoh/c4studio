import { expect, test, type Page } from "@playwright/test";

/**
 * Recolouring from the details card (PP-231).
 *
 * The real server plans each edit (`POST /api/style` writes nothing), and
 * the save that would follow is intercepted: the test reads the text the
 * Studio would have written instead of letting it touch the sample.
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
        // Not reloaded, so the canvas keeps the preview to be asserted on.
        reloaded: false,
        error: null,
        diagnostics: [],
        views: [],
      }),
    });
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
  await page.getByRole("button", { name: "Details" }).click();
  return saved;
}

async function editDatabase(page: Page) {
  await page.locator(".react-flow__node-element", { hasText: "Shipment Database" }).click();
  await page.getByRole("button", { name: "Edit style" }).click();
  return page.getByLabel("Edit style", { exact: true });
}

test("a colour for every element with the tag edits the tag's style", async ({ page }) => {
  const saved = await open(page);
  const editor = await editDatabase(page);
  await expect(editor.getByRole("radio", { name: "All “Database” (1)" })).toBeChecked();
  await expect(editor.getByText("Edits the “Database” style")).toBeVisible();

  await editor.getByLabel("Background", { exact: true }).fill("#ff0000");
  await expect(editor.getByRole("status")).toHaveText("Saved to logistics_network.dsl");
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatch(/element "Database" \{\s+shape Cylinder\s+background #ff0000\s+\}/);

  // Painted at once, before any reload.
  await expect(
    page.locator(".react-flow__node-element", { hasText: "Shipment Database" }).locator(".node"),
  ).toHaveCSS("background-color", "rgb(255, 0, 0)");

  // A second edit saves too. The editor's copy of the file must take what
  // was written; left with the old text it reads as unsaved changes, and
  // every later edit lands there instead of on disk.
  await editor.getByLabel("Border", { exact: true }).fill("#00ff00");
  await expect.poll(() => saved.length).toBe(2);
  await expect(editor.getByRole("status")).toHaveText("Saved to logistics_network.dsl");
});

test("only this element gets a tag and a style of its own", async ({ page }) => {
  const saved = await open(page);
  const editor = await editDatabase(page);
  await editor.getByRole("radio", { name: "Only this" }).click();
  await expect(
    editor.getByText("Adds the tag “Shipment Database” to this element, and a style for it"),
  ).toBeVisible();

  await editor.getByLabel("Text", { exact: true }).fill("#000000");
  await expect(editor.getByRole("status")).toHaveText("Saved to logistics_network.dsl");
  expect(saved[0]).toContain('"PostgreSQL" {\n                tags "Shipment Database"\n');
  expect(saved[0]).toMatch(/element "Shipment Database" \{\s+color #000000\s+\}/);
});

test("a line's dash pattern edits its relationship style", async ({ page }) => {
  const saved = await open(page);
  await page.getByText("Streams scan events to").click();
  await page.getByRole("button", { name: "Edit style" }).click();
  const editor = page.getByLabel("Edit style", { exact: true });
  await expect(editor.getByText(/^All “Async” lines/)).toBeVisible();
  // The `Async` rule sets both the colour and the dash pattern.
  await expect(editor.getByText(/set here$/)).toHaveCount(2);

  await editor.getByLabel("Dash", { exact: true }).selectOption("solid");
  await expect(editor.getByRole("status")).toHaveText("Saved to logistics_network.dsl");
  expect(saved[0]).toMatch(/relationship "Async" \{[^}]*style Solid/);
});
