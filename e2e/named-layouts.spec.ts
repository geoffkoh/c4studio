import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * The toolbar's Layouts menu (PP-197): save the current arrangement under
 * a name, load one back, delete one.
 *
 * What the server does with a snapshot is pinned by
 * `tests/test_webapp/test_named_layouts.py`. What only a browser shows is
 * the client's half: the working layout is flushed *before* the snapshot
 * is taken (or the snapshot copies a stale arrangement), loading asks
 * first and then redraws from the server, and the list follows each
 * change.
 *
 * Every write is answered here — the server serves `samples/`, the
 * developer's working copy — so the layouts endpoints are a small fake.
 */
type Saved = { name: string; savedAt: string };

async function open(page: Page) {
  const calls: string[] = [];
  let layouts: Saved[] = [];
  const reply = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    calls.push(route.request().url().endsWith("/layout") ? "layout" : "expansion");
    return reply(route, {});
  });
  await page.route(/\/api\/views\/[^/]+\/layouts(\/apply|\/delete)?$/, async (route) => {
    const request = route.request();
    const url = request.url();
    if (request.method() === "GET") return reply(route, { layouts });
    const { name } = request.postDataJSON() as { name: string };
    if (url.endsWith("/apply")) {
      calls.push(`apply:${name}`);
      return reply(route, { applied: name });
    }
    if (url.endsWith("/delete")) {
      calls.push(`delete:${name}`);
      layouts = layouts.filter((l) => l.name !== name);
      return reply(route, { layouts });
    }
    calls.push(`save:${name}`);
    layouts = [...layouts.filter((l) => l.name !== name), { name, savedAt: "2026-10-24T09:00:00+00:00" }];
    return reply(route, { layouts });
  });

  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  await expect(
    page.locator(".react-flow__node", { hasText: /^Delivery Platform – Containers$/ }),
  ).toBeVisible({ timeout: 20_000 });
  return calls;
}

const menuButton = (page: Page) => page.getByRole("button", { name: /^Layouts/ });
const dialog = (page: Page) => page.getByRole("dialog", { name: "Layouts" });

async function saveAs(page: Page, name: string) {
  await dialog(page).getByRole("textbox", { name: "Layout name" }).fill(name);
  await dialog(page).getByRole("button", { name: "Save", exact: true }).click();
}

test.describe("named layouts", () => {
  test("save flushes the working layout first, then lists the name", async ({ page }) => {
    const calls = await open(page);
    await menuButton(page).click();
    await expect(dialog(page)).toContainText("No saved layouts");
    calls.length = 0;

    await saveAs(page, "Review");
    await expect(dialog(page).getByRole("button", { name: "Review", exact: true })).toBeVisible();
    expect(calls).toEqual(["layout", "save:Review"]);
  });

  test("an existing name asks before replacing it", async ({ page }) => {
    const calls = await open(page);
    await menuButton(page).click();
    await saveAs(page, "Review");
    await expect(dialog(page).getByRole("button", { name: "Review", exact: true })).toBeVisible();

    page.once("dialog", (d) => void d.dismiss());
    calls.length = 0;
    await saveAs(page, "Review");
    await expect.poll(() => calls).toEqual([]);
  });

  test("loading asks, then redraws the view from the server", async ({ page }) => {
    const calls = await open(page);
    await menuButton(page).click();
    await saveAs(page, "Review");

    // What the server serves after the load, marked so the redraw shows.
    // The mark is a label, not a moved position: CI has no sidecar for
    // this view, so its nodes have no positions to move — it auto-lays
    // out, and a moved node would land exactly where it was. That the
    // payload holds the snapshot's positions is the server's half, and
    // `test_named_layouts.py` pins it.
    const node = page.locator(".react-flow__node-element").first();
    const markedId = (await node.getAttribute("data-id")) ?? "";
    const MARK = "Loaded from the server";
    await page.route(/\/api\/views\/[^/]+\/graph(\?.*)?$/, async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      for (const n of data.nodes) {
        if (n.id === markedId) n.data.label = MARK;
      }
      return route.fulfill({ response, json: data });
    });

    page.once("dialog", (d) => void d.dismiss());
    await dialog(page).getByRole("button", { name: "Review", exact: true }).click();
    await expect(dialog(page)).toBeVisible();
    expect(calls).not.toContain("apply:Review");

    page.once("dialog", (d) => void d.accept());
    const refetch = page.waitForResponse(/\/api\/views\/[^/]+\/graph/);
    await dialog(page).getByRole("button", { name: "Review", exact: true }).click();
    await refetch;
    expect(calls).toContain("apply:Review");
    await expect(dialog(page)).toBeHidden();

    await expect(
      page.locator(`.react-flow__node[data-id="${markedId}"]`),
    ).toContainText(MARK);
  });

  test("delete asks, then removes the name only", async ({ page }) => {
    const calls = await open(page);
    await menuButton(page).click();
    await saveAs(page, "Alpha");
    await expect(dialog(page).getByRole("button", { name: "Alpha", exact: true })).toBeVisible();
    await saveAs(page, "Beta");
    await expect(dialog(page).getByRole("button", { name: "Beta", exact: true })).toBeVisible();

    page.once("dialog", (d) => void d.accept());
    calls.length = 0;
    await dialog(page).getByRole("button", { name: "Delete Alpha" }).click();
    await expect(dialog(page).getByRole("button", { name: "Alpha", exact: true })).toHaveCount(0);
    await expect(dialog(page).getByRole("button", { name: "Beta", exact: true })).toBeVisible();
    expect(calls).toEqual(["delete:Alpha"]);
  });

  test("typing a name does not trigger the diagram's shortcuts", async ({ page }) => {
    await open(page);
    // `a` toggles Animate, which is remembered.
    const animate = () => page.evaluate(() => localStorage.getItem("c4studio.animateEdges"));
    const before = await animate();
    await menuButton(page).click();
    await dialog(page).getByRole("textbox", { name: "Layout name" }).pressSequentially("a plan");
    await expect(dialog(page).getByRole("textbox", { name: "Layout name" })).toHaveValue("a plan");
    expect(await animate()).toBe(before);
  });

  test("Escape closes the menu", async ({ page }) => {
    await open(page);
    await menuButton(page).click();
    await expect(dialog(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toBeHidden();
  });
});
