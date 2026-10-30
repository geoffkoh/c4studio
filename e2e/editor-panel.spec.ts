import { expect, test, type Page } from "@playwright/test";

/**
 * The source editor as a panel beside the diagram (PP-214), where it was
 * once a page of its own holding a second copy of the diagram.
 *
 * What is pinned is what the merge could break without a type error: the
 * diagram surviving the editor opening (one position in the tree, so no
 * remount), an outside request reaching the editor at a width with room
 * for one pane (the split is controlled for exactly that), and unsaved
 * work staying visible behind a closed editor.
 *
 * Layout writes are answered here because the server serves `samples/`.
 */
async function open(page: Page, width = 1440) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("hedge_fund/workspace.dsl");
  // An earlier spec may have left a workspace loaded on the shared
  // server, and the page hydrates with it — its diagram on screen before
  // this load replaces it. Wait for the load and the graph after it, or a
  // test can tag the canvas that is about to go.
  let loadDone = false;
  const loaded = page
    .waitForResponse((r) => r.url().endsWith("/api/load"))
    .then(() => (loadDone = true));
  const graphed = page.waitForResponse(
    (r) => loadDone && /\/api\/views\/[^/]+\/graph/.test(r.url()),
  );
  await page.getByRole("button", { name: "workspace.dsl", exact: true }).click();
  await loaded;
  await graphed;
  await expect(page.locator(".react-flow__node").first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("searchbox", { name: "Search files" }).fill("");
}

const editor = (page: Page) => page.locator(".editor__surface .cm-editor");
const sourceRail = (page: Page) => page.locator(".rail--right");
const sourceButton = (page: Page) => page.locator(".topbar__source");

test.describe("source editor panel", () => {
  test("closed at first; the rail opens it beside the diagram, which survives", async ({
    page,
  }) => {
    await open(page);
    await expect(sourceRail(page)).toBeVisible();
    await expect(sourceButton(page)).toHaveAttribute("aria-pressed", "false");
    await expect(editor(page)).toHaveCount(0);
    // No Source page any more: the tab is gone.
    await expect(page.locator(".topbar__tab", { hasText: "Source" })).toHaveCount(0);

    // Tag the diagram's DOM: a remount would replace the element.
    await page.locator(".react-flow").evaluate((el) => el.setAttribute("data-mark", "kept"));
    const before = (await page.locator(".graph").boundingBox())!;

    await sourceRail(page).click();
    await expect(editor(page)).toBeVisible();
    await expect(page.locator('.react-flow[data-mark="kept"]')).toHaveCount(1);

    // Editor on the right: the diagram keeps its left edge, so the
    // controls in its top-left corner do not jump.
    const graph = (await page.locator(".graph").boundingBox())!;
    const surface = (await page.locator(".editor__surface").boundingBox())!;
    expect(graph.x).toBeCloseTo(before.x, 0);
    expect(surface.x).toBeGreaterThan(graph.x + graph.width - 1);
    // The diagram's default share keeps it wide enough for the card to
    // sit beside the controls at this width.
    expect(graph.width).toBeGreaterThanOrEqual(640);

    await page.getByRole("button", { name: "Hide the Source" }).click();
    await expect(editor(page)).toHaveCount(0);
    await expect(page.locator('.react-flow[data-mark="kept"]')).toHaveCount(1);
  });

  test("e toggles it, and the choice is remembered", async ({ page }) => {
    await open(page);
    await page.locator(".react-flow__pane").click({ position: { x: 20, y: 300 } });
    await page.keyboard.press("e");
    await expect(editor(page)).toBeVisible();
    await page.reload();
    await expect(editor(page)).toBeVisible({ timeout: 20_000 });
    // Typing in the editor is typing, not a shortcut.
    await page.locator(".cm-content").click();
    await page.keyboard.type("e");
    await expect(editor(page)).toBeVisible();
  });

  test("show definition opens it, even where only one pane fits", async ({ page }) => {
    await open(page, 560);
    // The tree is in the sidebar, which open() revealed.
    await page
      .locator(".tree__toggle", { hasText: "Execution Management System" })
      .first()
      .dblclick();
    await expect(editor(page)).toBeVisible();
    // The diagram is the rail it can be swapped back to.
    await page.getByRole("button", { name: "diagram", exact: true }).click();
    await expect(editor(page)).toHaveCount(0);
    await expect(page.locator(".react-flow")).toBeVisible();
  });

  test("unsaved work is marked on the rail of a closed editor", async ({ page }) => {
    await open(page);
    await sourceRail(page).click();
    await page.locator(".cm-content").click();
    await page.keyboard.type("// PP-214 was here\n");
    await page.getByRole("button", { name: "Hide the Source" }).click();
    // On the rail and on the top bar's button alike.
    await expect(sourceRail(page).getByLabel("Unsaved changes")).toBeVisible();
    await expect(sourceButton(page).getByLabel("Unsaved changes")).toBeVisible();
    await sourceRail(page).click();
    await expect(page.locator(".cm-content")).toContainText("PP-214 was here");
  });

  test("the top bar's Source button toggles it, from any page (PP-215)", async ({
    page,
  }) => {
    await open(page);
    await sourceButton(page).click();
    await expect(editor(page)).toBeVisible();
    await expect(sourceButton(page)).toHaveAttribute("aria-pressed", "true");
    await sourceButton(page).click();
    await expect(editor(page)).toHaveCount(0);
    await expect(sourceButton(page)).toHaveAttribute("aria-pressed", "false");

    // From another page it brings the editor into view, not closes it.
    await page.getByRole("button", { name: "Explorer" }).click();
    await expect(sourceButton(page)).toHaveAttribute("aria-pressed", "false");
    await sourceButton(page).click();
    await expect(editor(page)).toBeVisible();
    await expect(page.locator(".topbar__tab--active")).toHaveText("Diagrams");
  });
});
