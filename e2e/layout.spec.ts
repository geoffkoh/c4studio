import { expect, test, type Page } from "@playwright/test";

/**
 * The Studio's layout, at the widths it is actually used at.
 *
 * Every assertion here exists because something in PP-146…PP-150 was
 * changed without anyone seeing it. They are deliberately about *layout*
 * rather than appearance: a pane having height, chrome not eating the
 * window, a breakpoint firing where the arithmetic said it would. Those
 * are the failures that are invisible to a type checker and obvious to a
 * person, which is exactly the gap this file closes.
 */

/**
 * Load hedge_fund and land on the Source page.
 *
 * Via the search box rather than by expanding folders, because **these
 * tests are not independent of each other**: the backend holds the loaded
 * workspace in `AppState`, so a later `goto("/")` hydrates with that file
 * already current and its folders already expanded. A helper that clicks
 * `▸ hedge_fund` works exactly once per server.
 *
 * Searching sidesteps the whole question — it force-expands ancestors and
 * narrows to one row whatever the tree was doing before — and it exercises
 * the search and the windowing on the way past.
 */
async function openSource(page: Page) {
  await page.goto("/");
  // At narrow widths the sidebar starts collapsed, so the tree is behind
  // the rail. Reveal it before reaching for the search box.
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("hedge_fund/workspace.dsl");
  await page.getByRole("button", { name: "workspace.dsl", exact: true }).click();
  // The Source tab only exists once something is loaded.
  await page.getByRole("button", { name: "Source" }).click();
  await expect(page.locator(".editor__surface .cm-editor")).toBeVisible();
  // Leave the tree as a user would find it, not filtered by the helper.
  await page.getByRole("searchbox", { name: "Search files" }).fill("");
}

/** Wait for the debounced /api/check to settle, so the status bar is not
    screenshotted mid-flight — it reads "Checking…" for ~400ms. */
async function settled(page: Page) {
  await expect(page.locator(".editor__status")).not.toContainText("Checking");
}

/** The rendered width of a selector, or 0 when it is not on the page. */
async function widthOf(page: Page, selector: string): Promise<number> {
  const box = await page.locator(selector).first().boundingBox();
  return box?.width ?? 0;
}

test.describe("Source page", () => {
  test("both panes have height — the failure every flex change risks", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSource(page);

    const editor = await page.locator(".editor__surface").boundingBox();
    const diagram = await page.locator(".split__pane--right").boundingBox();

    // A zero-height pane is the specific way a percentage-inside-flex
    // mistake shows up, and it type-checks perfectly.
    expect(editor?.height ?? 0).toBeGreaterThan(200);
    expect(diagram?.height ?? 0).toBeGreaterThan(200);
    expect(editor?.width ?? 0).toBeGreaterThan(300);
    expect(diagram?.width ?? 0).toBeGreaterThan(300);
  });

  test("three columns, not four — the duplicate file list is gone", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSource(page);

    // The 200px list that used to sit between the sidebar and the editor.
    await expect(page.locator(".docs__toc--compact")).toHaveCount(0);
    await expect(page.locator(".tabs")).toBeVisible();

    const chrome = await widthOf(page, ".sidebar");
    expect(chrome).toBeLessThanOrEqual(300);
    // Chrome must be a minority of the window at laptop width.
    expect(chrome / 1440).toBeLessThan(0.25);
  });

  test("only the root opens as a tab, not every fragment", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSource(page);
    // hedge_fund is a root plus 8 !include fragments. Progressive
    // disclosure is the whole reason tabs were viable here.
    await expect(page.getByRole("tab")).toHaveCount(1);
  });

  test("a dirty buffer survives leaving the page", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSource(page);

    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.type("// PP-147 was here\n");
    await expect(page.locator(".editor__badge", { hasText: "Unsaved" })).toBeVisible();

    await page.getByRole("button", { name: "Diagrams" }).click();
    await expect(page.locator(".editor__surface")).toHaveCount(0);
    await page.getByRole("button", { name: "Source" }).click();

    // The bug this whole series started from: the edit used to be gone.
    await expect(page.locator(".cm-content")).toContainText("PP-147 was here");
    await expect(page.locator(".editor__badge", { hasText: "Unsaved" })).toBeVisible();
  });
});

test.describe("sidebar", () => {
  test("collapses to a rail and gives the width back", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSource(page);

    const open = await widthOf(page, ".sidebar");
    expect(open).toBeGreaterThan(200);

    await page.getByRole("button", { name: /Hide the sidebar/ }).click();
    await expect(page.locator(".sidebar")).toBeHidden();

    const rail = await widthOf(page, ".rail--left");
    expect(rail).toBeGreaterThan(0);
    expect(rail).toBeLessThan(40);

    // And back, without losing the tree's state.
    await page.locator(".rail--left").click();
    await expect(page.locator(".sidebar")).toBeVisible();
    expect(await widthOf(page, ".sidebar")).toBe(open);
  });

  test("its sections are bounded rather than shoving each other", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSource(page);

    const views = await page.locator(".section__scroll--views").boundingBox();
    const elements = await page.locator(".section__scroll--elements").boundingBox();
    expect(views?.height ?? 0).toBeLessThanOrEqual(240);
    expect(elements?.height ?? 0).toBeLessThanOrEqual(900 * 0.4 + 1);

    // The file tree must still be reachable without scrolling past two
    // unbounded lists — it is the primary navigator.
    const tree = await page.locator(".tree__scroll").boundingBox();
    expect(tree?.y ?? Infinity).toBeLessThan(400);
  });
});

test.describe("narrow surfaces", () => {
  // The VS Code preview embeds the whole SPA in a panel about this wide.
  test("500px: no pane is negative, and only one is shown", async ({ page }) => {
    await page.setViewportSize({ width: 500, height: 800 });
    await openSource(page);

    // Below 320*2+6 there is no honest split to draw.
    await expect(page.locator(".split__divider")).toHaveCount(0);
    const editor = await page.locator(".editor__surface").boundingBox();
    expect(editor?.width ?? 0).toBeGreaterThan(100);
    expect(editor?.height ?? 0).toBeGreaterThan(100);

    // The other pane is reachable, which my first attempt at this got
    // wrong — the rail called setOpen on something already open.
    await page.locator(".rail--right").click();
    await expect(page.locator(".split__pane--right")).toBeVisible();
    await expect(page.locator(".rail--left")).toBeVisible();
  });

  test("the sidebar starts collapsed where there is no room", async ({
    page,
  }) => {
    // The screenshot at 500px is what caught this: the breakpoints shrank
    // the sidebar but never collapsed it, leaving the editor ~280px wide.
    await page.setViewportSize({ width: 500, height: 800 });
    await page.goto("/");
    await expect(page.locator(".sidebar")).toBeHidden();
    await expect(page.locator(".rail--left")).toBeVisible();
  });

  test("the page never scrolls sideways", async ({ page }) => {
    for (const width of [500, 700, 1024, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      await openSource(page);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(1);
    }
  });
});

test.describe("appearance", () => {
  // Baselines, so the next layout change fails here rather than being
  // discovered by someone opening the app weeks later.
  for (const [name, width] of [
    ["wide", 1440],
    ["narrow", 500],
  ] as const) {
    test(`source page looks right at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openSource(page);
      // openSource reveals the sidebar to reach the tree. At narrow widths
      // put it back, so the baseline is what a VS Code user actually sees
      // rather than a state only this helper produces.
      if (width < 900) {
        await page.getByRole("button", { name: /Hide the sidebar/ }).click();
        await expect(page.locator(".sidebar")).toBeHidden();
      }
      await settled(page);
      // The diagram lays out asynchronously and its node positions are not
      // what this test is about.
      await expect(page).toHaveScreenshot(`source-${name}.png`, {
        mask: [page.locator(".split__pane--right"), page.locator(".graph")],
      });
    });
  }
});
