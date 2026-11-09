import { expect, test, type Page } from "@playwright/test";

/**
 * Find in the source editor (PP-225).
 *
 * ⌘/Ctrl-F used to fall through to the browser's own find, which cannot
 * see the editor's text: CodeMirror puts only the lines on screen into the
 * page, so anything further down the file was never found. The editor now
 * has its own find bar. The searched text here is well below the first
 * screenful, where the browser's find would have missed it.
 */
const FILE = "logistics_network.dsl";
const FAR_DOWN = "ProductionDeployment";

async function open(page: Page) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill(FILE);
  await page.getByRole("button", { name: FILE, exact: true }).click();
  await expect(page.locator(".react-flow__node").first()).toBeVisible({ timeout: 20_000 });
  await page.locator(".topbar__source").click();
  const content = page.locator(".editor__surface .cm-content");
  await expect(content).toContainText("workspace");
  await content.click({ position: { x: 40, y: 10 } });
}

/** The editor's selected text. */
const selection = (page: Page) =>
  page
    .locator(".editor__surface .cm-content")
    .evaluate(() => window.getSelection()?.toString() ?? "");

test("⌘/Ctrl-F opens the editor's find bar, not the browser's", async ({ page }) => {
  await open(page);
  // Not in the page yet: off-screen lines are not rendered.
  await expect(page.locator(".cm-line", { hasText: FAR_DOWN })).toHaveCount(0);

  await page.keyboard.press("ControlOrMeta+f");
  const field = page.locator(".cm-search input[name=search]");
  await expect(field).toBeFocused();
  // Typed, not filled: the bar reads its query on key events.
  await field.pressSequentially(FAR_DOWN);
  await field.press("Enter");

  // The editor scrolled to the match and selected it.
  const line = page.locator(".cm-line", { hasText: FAR_DOWN }).first();
  await expect(line).toBeInViewport();
  await expect.poll(() => selection(page)).toBe(FAR_DOWN);
  await expect(page.locator(".cm-searchMatch-selected")).toHaveText(FAR_DOWN);
});

test("Enter steps to the next match, and Escape closes the bar", async ({ page }) => {
  await open(page);
  await page.keyboard.press("ControlOrMeta+f");
  const field = page.locator(".cm-search input[name=search]");
  await field.pressSequentially("Routing Engine");
  await field.press("Enter");
  const first = await page.locator(".cm-searchMatch-selected").boundingBox();
  await field.press("Enter");
  const second = await page.locator(".cm-searchMatch-selected").boundingBox();
  expect(second!.y).not.toBe(first!.y);

  await field.press("Escape");
  await expect(page.locator(".cm-search")).toHaveCount(0);
  // The source panel is still open behind it.
  await expect(page.locator(".editor__surface .cm-editor")).toBeVisible();
});
